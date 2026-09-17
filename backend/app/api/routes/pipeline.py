"""End-to-end run: a ZIP of exam pages + a ZIP of student work -> OCR -> grading.

Two steps on purpose:

1. `POST /uploads` takes the two ZIPs, unpacks them and answers with an
   inventory (template pages, exam codes, students per code). The teacher's
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
    PipelineJobGroup,
    PipelineJobStatus,
    TemplatePage,
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
    template_zip: UploadFile = File(...),
    students_zip: UploadFile = File(...),
) -> UploadInventory:
    upload_id = uuid.uuid4().hex
    root = _UPLOADS_DIR / upload_id
    template_root = root / "template"
    students_root = root / "students"
    root.mkdir(parents=True, exist_ok=True)

    for upload, dest in ((template_zip, "template.zip"), (students_zip, "students.zip")):
        with (root / dest).open("wb") as f:
            shutil.copyfileobj(upload.file, f)

    try:
        zip_intake.extract_zip(root / "template.zip", template_root)
        zip_intake.extract_zip(root / "students.zip", students_root)
    except Exception as exc:  # noqa: BLE001 - bad archive is user input, not a crash
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Không giải nén được file zip: {exc}") from exc

    templates = zip_intake.group_template_pages(template_root)
    template_pages = zip_intake.list_template_pages(template_root)
    if not template_pages:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(
            status_code=400, detail="File zip đề mẫu không chứa ảnh .png/.jpg nào."
        )

    groups = zip_intake.group_students(students_root)
    if not groups:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(
            status_code=400, detail="File zip bài làm không chứa ảnh .png/.jpg nào."
        )

    return UploadInventory(
        upload_id=upload_id,
        template_pages=[
            TemplatePage(page=index, filename=path.relative_to(template_root).as_posix())
            for index, path in enumerate(template_pages, start=1)
        ],
        ma_de_list=[
            UploadMaDe(
                ma_de=group.ma_de,
                student_count=len(group.students),
                students=[
                    UploadStudent(
                        hs_key=zip_intake.normalise_hs_key(student.folder, index),
                        folder=student.folder,
                        page_count=len(student.pages),
                    )
                    for index, student in enumerate(group.students, start=1)
                ],
                template_pages=[
                    TemplatePage(page=index, filename=path.relative_to(template_root).as_posix())
                    for index, path in enumerate(
                        zip_intake.template_pages_for(templates, group.ma_de), start=1
                    )
                ],
                template_shared=group.ma_de not in templates,
            )
            for group in groups
        ],
    )


@router.get("/uploads/{upload_id}/template/{page}")
async def get_template_page(upload_id: str, page: int, ma_de: str | None = None) -> FileResponse:
    """Serve one blank exam page — the ROI editor draws its boxes on top of this.

    `ma_de` picks that code's own pages when the template archive is split by
    code; without it (or when the archive is flat) the whole set is used, which
    is also the shared-template case.
    """
    template_root = _UPLOADS_DIR / upload_id / "template"
    if not template_root.is_dir():
        raise HTTPException(status_code=404, detail="upload not found")

    if ma_de:
        pages = zip_intake.template_pages_for(zip_intake.group_template_pages(template_root), ma_de)
    else:
        pages = zip_intake.list_template_pages(template_root)

    if page < 1 or page > len(pages):
        where = f" của mã đề {ma_de}" if ma_de else ""
        raise HTTPException(status_code=404, detail=f"Đề mẫu{where} chỉ có {len(pages)} trang.")
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


def _spawn_worker(job_id: str, job_dir: Path) -> int:
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
        # The PID goes onto the job row so a later API restart can tell a
        # still-detached worker from one that was killed — see
        # app/services/job_recovery.py.
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", "app.pipeline_worker", job_id, str(job_dir)],
            cwd=str(_BACKEND_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            **kwargs,
        )
    return process.pid


def _claim_hs_key(preferred: str, used: set[int]) -> str:
    """Give every student in the run a distinct `HS_<n>`, across exam codes.

    Two codes routinely both contain an `HS_1` folder, and three separate
    things key off that string: the Results JSON's top-level key, the crop
    filename (`{hs_key}_{cau_key}.png`), and `student_index`, which pipeline.py
    reads as `int(hs_key.split("_")[-1])`. Letting them collide would overwrite
    one student's crops with another's and merge their rows.

    Renumbering rather than suffixing (`HS_1_2`) is deliberate: a suffix still
    parses, just wrongly — `int("2")` — quietly turning student 1 of code 2
    into student 2.
    """
    try:
        number = int(preferred.split("_")[-1])
    except ValueError:
        number = len(used) + 1
    while number in used:
        number += 1
    used.add(number)
    return f"HS_{number}"


def _find_barem_for(db: Session, ma_de: str) -> BaremDoc:
    """The library's rubric for one exam code, newest first.

    Matched automatically rather than picked in the UI: a run can now cover
    several codes, and making the teacher pair each one with a rubric by hand
    is both tedious and easy to get wrong. Skipped entirely when the group
    sets its own `barem_id` — see `_resolve_barem`.
    """
    doc = (
        db.query(BaremDoc)
        .filter(BaremDoc.ma_de == str(ma_de))
        .order_by(BaremDoc.updated_at.desc())
        .first()
    )
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Kho barem không có mã đề '{ma_de}'. Soạn hoặc tải barem cho mã đề đó "
                f"lên kho rồi tạo lại phiên chấm, hoặc chọn thẳng 1 barem có sẵn thay vì "
                f"khớp theo mã đề."
            ),
        )
    return doc


def _resolve_barem(db: Session, group: PipelineJobGroup) -> BaremDoc:
    """The rubric for one group: picked directly by `barem_id` when the
    teacher set one (bypassing ma_de matching entirely), else looked up by
    `ma_de` as before."""
    if group.barem_id:
        doc = db.get(BaremDoc, group.barem_id)
        if doc is None:
            raise HTTPException(
                status_code=404, detail=f"Không tìm thấy barem '{group.barem_id}' trong kho."
            )
        return doc
    return _find_barem_for(db, group.ma_de)


@router.post("/jobs", response_model=PipelineJobCreated)
async def create_pipeline_job(
    payload: PipelineJobCreate, db: Session = Depends(get_db)
) -> PipelineJobCreated:
    upload_root = _UPLOADS_DIR / payload.upload_id
    template_root = upload_root / "template"
    students_root = upload_root / "students"
    if not template_root.is_dir() or not students_root.is_dir():
        raise HTTPException(status_code=404, detail="upload không tồn tại (hoặc đã bị dọn).")

    if not payload.groups:
        raise HTTPException(status_code=400, detail="Chưa chọn mã đề nào để chấm.")

    seen_codes = [g.ma_de for g in payload.groups]
    duplicates = {code for code in seen_codes if seen_codes.count(code) > 1}
    if duplicates:
        raise HTTPException(
            status_code=400, detail=f"Mã đề bị khai trùng trong cùng một phiên: {', '.join(sorted(duplicates))}."
        )

    templates = zip_intake.group_template_pages(template_root)
    students_by_code = {g.ma_de: g for g in zip_intake.group_students(students_root)}

    job_id = uuid.uuid4().hex
    job_dir = _JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    barem_dir = job_dir / "barems"
    barem_dir.mkdir(parents=True, exist_ok=True)

    configs: list[dict] = []
    student_map: dict[str, str] = {}
    used_numbers: set[int] = set()
    barem_names: list[str] = []
    total_students = 0
    total_rois = 0
    total_steps = 0

    for group in payload.groups:
        ma_de = group.ma_de
        entry = students_by_code.get(ma_de)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Không thấy mã đề '{ma_de}' trong zip bài làm.")

        pages = zip_intake.template_pages_for(templates, ma_de)
        if not pages:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Mã đề '{ma_de}' không có ảnh đề mẫu. Zip đề mẫu cần thư mục "
                    f"'Made_{ma_de}' riêng, hoặc để ảnh phẳng ở gốc thì bộ ảnh đó dùng chung cho mọi mã đề."
                ),
            )

        rois = _validate_rois(group.roi_config.get("rois"), len(pages))

        barem = _resolve_barem(db, group)
        # Force the barem's OWN "ma_de" field to match this group's ma_de
        # before writing it out — pipeline.py's load_barems() indexes barems
        # by the code each one declares INSIDE its content, not by filename,
        # then matches each student to a barem by their own tagged ma_de
        # (see CLAUDE.md's "Input format" section). The auto-matched path
        # (_find_barem_for) already guarantees these agree by construction,
        # but a directly-picked barem_id can point at a barem written for a
        # totally different code (that's the point — bypass the ma_de check)
        # so it needs to be re-tagged here, or pipeline.py would silently
        # skip every student in this group with "thiếu ma_de/mã đề không có
        # barem" despite a barem file visibly sitting right next to them.
        barem_content = json.loads(barem.content)
        barem_content["ma_de"] = ma_de
        (barem_dir / f"ma_de_{ma_de}.json").write_text(
            json.dumps(barem_content, ensure_ascii=False), encoding="utf-8"
        )
        barem_names.append(barem.name)

        students = []
        for index, student in enumerate(entry.students, start=1):
            hs_key = _claim_hs_key(zip_intake.normalise_hs_key(student.folder, index), used_numbers)
            students.append({"hs_key": hs_key, "ma_de": ma_de, "pages": [str(p) for p in student.pages]})
            student_map[hs_key] = f"[{ma_de}] {student.folder}" if len(payload.groups) > 1 else student.folder

        configs.append(
            {
                "ma_de": ma_de,
                "template_pages": [str(p) for p in pages],
                "crop_dir": str(job_dir / "crops"),
                "students": students,
                "rois": rois,
            }
        )
        total_students += len(students)
        total_rois += len(rois)
        total_steps += len(students) * len(rois)

    # One file per exam code; the worker runs the OCR connector once per file
    # and merges the results, which works because every student now carries
    # their own ma_de.
    (job_dir / "roi_configs.json").write_text(
        json.dumps(configs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if payload.save_crops:
        (job_dir / "save_crops").touch()

    job = PipelineJob(
        job_id=job_id,
        status=JobStatus.PENDING,
        student_count=total_students,
        roi_count=total_rois,
        progress_total=total_steps,
        ma_de=", ".join(seen_codes),
        barem_name=", ".join(barem_names),
    )
    db.add(job)
    db.commit()

    job.worker_pid = _spawn_worker(job_id, job_dir)
    db.commit()

    return PipelineJobCreated(
        job_id=job_id,
        status=JobStatus.PENDING,
        student_count=total_students,
        roi_count=total_rois,
        ma_de_list=seen_codes,
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
