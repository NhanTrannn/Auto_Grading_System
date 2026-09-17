"""End-to-end run: a ZIP of exam pages + a ZIP of student work -> OCR -> grading.

Two steps on purpose:

1. `POST /uploads` takes the student ZIP, unpacks it and answers with an
    inventory (exam codes, students per code). The teacher's
   archive holds a whole semester, so the UI has to show what was found and
   let them pick which exam code to run — guessing would silently grade the
   wrong cohort.
2. `POST /jobs` runs exactly one exam code from a previous upload, against a
   barem from the library and an roi_config assembled in the browser.

The CLI equivalent of step 2 is `backend/ocr/main.py`; this module only does
the web part — materialising a `roi_config.json` that points at the unpacked
files, then handing off to `app.pipeline_worker`.
"""

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.barem_doc import BaremDoc
from app.models.pipeline_job import PipelineJob
from app.schemas.grading import GradingJobResult, JobStatus
from app.schemas.pipeline import (
    JobLog,
    PipelineJobCreate,
    PipelineJobCreated,
    PipelineJobStatus,
    UploadInventory,
    UploadMaDe,
    UploadStudent,
)
from app.services import zip_intake

router = APIRouter()

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_JOBS_DIR = _BACKEND_ROOT / "var" / "pipeline_jobs"
_UPLOADS_DIR = _BACKEND_ROOT / "var" / "pipeline_uploads"

_REQUIRED_ROI_FIELDS = ("cau_key", "x", "y", "w", "h", "task_type")
_VALID_TASK_TYPES = {"short_text", "long_text", "code", "table", "diagram"}


# ── Step 1: upload + inspect ────────────────────────────────────────────────


@router.post("/uploads", response_model=UploadInventory)
async def create_upload(
    template_zip: UploadFile | None = File(None),
    students_zip: UploadFile = File(...),
) -> UploadInventory:
    upload_id = uuid.uuid4().hex
    root = _UPLOADS_DIR / upload_id
    students_root = root / "students"
    root.mkdir(parents=True, exist_ok=True)

    uploads = [(students_zip, "students.zip")]
    if template_zip is not None:
        uploads.append((template_zip, "template.zip"))
    for upload, dest in uploads:
        with (root / dest).open("wb") as f:
            shutil.copyfileobj(upload.file, f)

    try:
        zip_intake.extract_zip(root / "students.zip", students_root)
        if template_zip is not None:
            zip_intake.extract_zip(root / "template.zip", root / "template")
    except Exception as exc:  # noqa: BLE001 - bad archive is user input, not a crash
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Không giải nén được file zip: {exc}") from exc

    groups = zip_intake.group_students(students_root)
    if not groups:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(
            status_code=400, detail="File zip bài làm không chứa ảnh .png/.jpg nào."
        )

    inventory_groups = []
    for group in groups:
        used_hs_keys: set[str] = set()
        inventory_students = []
        for index, student in enumerate(group.students, start=1):
            inventory_students.append(
                UploadStudent(
                    hs_key=zip_intake.normalise_hs_key(student.folder, index, used_hs_keys),
                    folder=student.folder,
                    page_count=len(student.pages),
                )
            )
        inventory_groups.append(
            UploadMaDe(
                ma_de=group.ma_de,
                student_count=len(group.students),
                students=inventory_students,
            )
        )

    return UploadInventory(upload_id=upload_id, ma_de_list=inventory_groups)


@router.get("/uploads/{upload_id}/sample/{ma_de}/{page}")
async def get_sample_student_page(upload_id: str, ma_de: str, page: int) -> FileResponse:
    """Serve a representative student page for direct ROI detection/editing."""
    students_root = _UPLOADS_DIR / upload_id / "students"
    groups = zip_intake.group_students(students_root) if students_root.is_dir() else []
    group = next((item for item in groups if item.ma_de == ma_de), None)
    if group is None or not group.students or page < 1:
        raise HTTPException(status_code=404, detail="Không tìm thấy trang bài làm mẫu.")
    pages = group.students[0].pages
    if page > len(pages):
        raise HTTPException(status_code=404, detail=f"Bài làm mẫu chỉ có {len(pages)} trang.")
    return FileResponse(pages[page - 1])


@router.get("/uploads/{upload_id}/template/{page}")
async def get_template_page(upload_id: str, page: int) -> FileResponse:
    """Serve one blank exam page — the ROI editor draws its boxes on top of this."""
    template_root = _UPLOADS_DIR / upload_id / "template"
    if not template_root.is_dir():
        raise HTTPException(status_code=404, detail="upload not found")

    pages = zip_intake.list_template_pages(template_root)
    if page < 1 or page > len(pages):
        raise HTTPException(status_code=404, detail=f"Đề mẫu chỉ có {len(pages)} trang.")
    return FileResponse(pages[page - 1])


# ── Step 2: run one exam code ───────────────────────────────────────────────


def _validate_rois(rois: object, page_count: int) -> list[dict]:
    """Reject a malformed roi_config up front rather than 10 minutes into OCR."""
    if not isinstance(rois, list) or not rois:
        raise HTTPException(status_code=400, detail="roi_config thiếu danh sách 'rois' (hoặc rỗng).")

    seen: set[str] = set()
    for index, roi in enumerate(rois):
        if not isinstance(roi, dict):
            raise HTTPException(status_code=400, detail=f"rois[{index}] không phải object.")
        label = f"rois[{index}] ({roi.get('cau_key', '?')})"

        missing = [f for f in _REQUIRED_ROI_FIELDS if roi.get(f) is None]
        if missing:
            raise HTTPException(status_code=400, detail=f"{label} thiếu trường: {', '.join(missing)}")
        if roi["task_type"] not in _VALID_TASK_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{label} có task_type không hợp lệ: '{roi['task_type']}'. "
                    f"Cho phép: {', '.join(sorted(_VALID_TASK_TYPES))}."
                ),
            )
        if roi["task_type"] == "table" and not (roi.get("n_rows") and roi.get("n_cols")):
            raise HTTPException(
                status_code=400, detail=f"{label} là bảng nên bắt buộc có n_rows và n_cols."
            )

        page = int(roi.get("page", 1) or 1)
        if page < 1 or page > page_count:
            raise HTTPException(
                status_code=400,
                detail=f"{label} trỏ tới trang {page} nhưng đề mẫu chỉ có {page_count} trang.",
            )

        if roi["cau_key"] in seen:
            raise HTTPException(status_code=400, detail=f"{label} trùng cau_key với ROI trước đó.")
        seen.add(roi["cau_key"])

    return rois


def _spawn_worker(job_id: str, job_dir: Path) -> None:
    # Same detached-subprocess rationale as app/api/routes/grading.py: the run
    # must survive a uvicorn restart, and PYTHONIOENCODING is required because
    # both the OCR connector and pipeline.py print Vietnamese. `-u` keeps that
    # output unbuffered so the live log panel sees lines as they happen rather
    # than in 8KB bursts.
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    with (job_dir / "worker.log").open("wb") as log_file:
        subprocess.Popen(
            [sys.executable, "-u", "-m", "app.pipeline_worker", job_id, str(job_dir)],
            cwd=str(_BACKEND_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            **kwargs,
        )


@router.post("/jobs", response_model=PipelineJobCreated)
async def create_pipeline_job(
    payload: PipelineJobCreate, db: Session = Depends(get_db)
) -> PipelineJobCreated:
    upload_root = _UPLOADS_DIR / payload.upload_id
    students_root = upload_root / "students"
    if not students_root.is_dir():
        raise HTTPException(status_code=404, detail="upload không tồn tại (hoặc đã bị dọn).")

    barem = db.get(BaremDoc, payload.barem_id)
    if barem is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy barem đã chọn.")

    group = next(
        (g for g in zip_intake.group_students(students_root) if g.ma_de == payload.ma_de), None
    )
    if group is None:
        raise HTTPException(status_code=404, detail=f"Không thấy mã đề '{payload.ma_de}' trong zip.")

    rois = _validate_rois(payload.roi_config.get("rois"), max((len(s.pages) for s in group.students), default=0))

    job_id = uuid.uuid4().hex
    job_dir = _JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "barem.json").write_text(barem.content, encoding="utf-8")

    students = []
    student_map: dict[str, str] = {}
    used_hs_keys: set[str] = set()
    for index, student in enumerate(group.students, start=1):
        hs_key = zip_intake.normalise_hs_key(student.folder, index, used_hs_keys)
        students.append({"hs_key": hs_key, "pages": [str(p) for p in student.pages]})
        student_map[hs_key] = student.folder

    resolved = {
        # The Results JSON's ma_de must match the barem's for load_barem() to
        # line up, so the barem wins over the folder name here.
        "ma_de": barem.ma_de or payload.ma_de,
        "crop_dir": str(job_dir / "crops"),
        "students": students,
        "rois": rois,
    }
    (job_dir / "roi_config.json").write_text(
        json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if payload.save_crops:
        (job_dir / "save_crops").touch()

    job = PipelineJob(
        job_id=job_id,
        status=JobStatus.PENDING,
        student_count=len(students),
        roi_count=len(rois),
        progress_total=len(students) * len(rois),
        ma_de=payload.ma_de,
        barem_name=barem.name,
    )
    db.add(job)
    db.commit()

    _spawn_worker(job_id, job_dir)

    return PipelineJobCreated(
        job_id=job_id,
        status=JobStatus.PENDING,
        student_count=len(students),
        roi_count=len(rois),
        student_map=student_map,
    )


# ── Job status / results ────────────────────────────────────────────────────


@router.get("/jobs", response_model=list[PipelineJobStatus])
async def list_pipeline_jobs(db: Session = Depends(get_db)) -> list[PipelineJob]:
    return list(db.query(PipelineJob).order_by(PipelineJob.created_at.desc()).limit(50).all())


@router.get("/jobs/{job_id}", response_model=PipelineJobStatus)
async def get_pipeline_job(job_id: str, db: Session = Depends(get_db)) -> PipelineJob:
    job = db.get(PipelineJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.get("/jobs/{job_id}/result", response_model=GradingJobResult)
async def get_pipeline_job_result(job_id: str, db: Session = Depends(get_db)) -> GradingJobResult:
    job = db.get(PipelineJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=409, detail=f"job is not done yet (status: {job.status})")

    output_dir = _JOBS_DIR / job_id / "graded"
    try:
        grading_results = json.loads((output_dir / "grading_results.json").read_text(encoding="utf-8"))
        student_summary = json.loads((output_dir / "student_summary.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"result files missing: {exc}") from exc

    return GradingJobResult(grading_results=grading_results, student_summary=student_summary)


@router.get("/jobs/{job_id}/ocr-result")
async def get_pipeline_ocr_result(job_id: str, db: Session = Depends(get_db)) -> dict:
    """The intermediate Results-format JSON, available as soon as OCR finishes.

    Useful on its own: a teacher can eyeball what the OCR actually read before
    trusting the grade, and can re-feed this file to the plain grading page.
    """
    job = db.get(PipelineJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    results_path = _JOBS_DIR / job_id / "results.json"
    if not results_path.exists():
        raise HTTPException(status_code=409, detail="OCR chưa hoàn tất cho job này.")
    return json.loads(results_path.read_text(encoding="utf-8"))


@router.get("/jobs/{job_id}/log", response_model=JobLog)
async def get_pipeline_job_log(job_id: str, offset: int = 0) -> JobLog:
    """Incremental tail of the run's stdout, for the live log panel.

    One file now: the worker runs OCR and grading in its own process, so both
    halves' output (and any traceback) lands in the same stdout redirect. It
    used to spawn a further child whose output went to a second file, and this
    endpoint read that one.
    """
    log_path = _JOBS_DIR / job_id / "worker.log"
    if not log_path.exists():
        return JobLog(text="", next_offset=0, size=0)

    size = log_path.stat().st_size
    # A truncated/rotated file would leave the client's offset past the end;
    # restart from the beginning instead of returning nothing forever.
    start = 0 if offset > size else offset
    with log_path.open("rb") as f:
        f.seek(start)
        chunk = f.read()

    return JobLog(text=chunk.decode("utf-8", errors="replace"), next_offset=size, size=size)


@router.get("/jobs/{job_id}/crops/{hs_key}/{cau_key}")
async def get_pipeline_crop(job_id: str, hs_key: str, cau_key: str) -> FileResponse:
    """The cropped answer region, so the review screen can show it beside the OCR text."""
    # Path components come straight from the URL — keep them to bare names so
    # a crafted hs_key/cau_key can't escape the job's crops directory.
    if any(c in f"{hs_key}{cau_key}" for c in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="invalid crop id")

    crop_path = _JOBS_DIR / job_id / "crops" / f"{hs_key}_{cau_key}.png"
    if not crop_path.exists():
        raise HTTPException(status_code=404, detail="crop not found")
    return FileResponse(crop_path)
