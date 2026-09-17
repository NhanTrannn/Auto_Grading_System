import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.barem_doc import BaremDoc
from app.models.grading_job import GradingJob
from app.schemas.grading import GradingJobCreated, GradingJobResult, GradingJobStatus, JobStatus

router = APIRouter()

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_JOBS_DIR = _BACKEND_ROOT / "var" / "jobs"


def _spawn_worker(job_id: str, input_path: Path, barem_source: Path, output_dir: Path, log_path: Path) -> int:
    # A real OS subprocess, not a FastAPI BackgroundTask: it must keep
    # grading even if this API process is killed/restarted mid-run, so it
    # cannot share a process (or an event loop) with uvicorn. On Windows,
    # CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS stop it from receiving the
    # parent's Ctrl+C/console-close signals; start_new_session does the
    # equivalent on POSIX (detaches from the parent's session).
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    # pipeline.py prints Vietnamese text throughout grading — without this,
    # the child inherits the parent's default stdout encoding, which on
    # Windows is the system codepage (cp1252), not UTF-8. That can't encode
    # Vietnamese diacritics, so the worker crashes with UnicodeEncodeError
    # partway through grading (same root cause as the `--test` CLI note in
    # the root CLAUDE.md, just hit here via a spawned subprocess instead of
    # an interactive terminal).
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    with log_path.open("wb") as log_file:
        # The PID goes onto the job row so a later API restart can tell a
        # still-detached worker from one that was killed — see
        # app/services/job_recovery.py.
        process = subprocess.Popen(
            [sys.executable, "-m", "app.worker", job_id, str(input_path), str(barem_source), str(output_dir)],
            cwd=str(_BACKEND_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            **kwargs,
        )
    return process.pid


def _materialise_barems(db: Session, input_path: Path, barem_dir: Path) -> list[str]:
    """Write out one barem per `ma_de` the input actually uses.

    Every student declares their own `ma_de`, so a single file can mix exam
    codes and the run needs a barem for each. Rather than making the teacher
    pick them, the library is indexed by `ma_de` and matched automatically —
    which is the whole point of storing rubrics server-side.

    Only the codes present in the input are written: dropping the rest keeps
    the worker's log readable and stops an unrelated draft rubric in the
    library from being loaded (and, if it duplicated a `ma_de`, from making
    `load_barems()` refuse the whole run).
    """
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"File bài làm không phải JSON hợp lệ: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="File bài làm phải là object {'HS_1': {...}}.")

    wanted: dict[str, list[str]] = {}
    missing_ma_de: list[str] = []
    for hs_key, entry in data.items():
        if not hs_key.startswith("HS_") or not isinstance(entry, dict):
            continue
        ma_de = entry.get("ma_de")
        if ma_de is None:
            missing_ma_de.append(hs_key)
            continue
        wanted.setdefault(str(ma_de), []).append(hs_key)

    if missing_ma_de:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{len(missing_ma_de)} học sinh thiếu 'ma_de' (vd {', '.join(missing_ma_de[:5])}). "
                "Mỗi học sinh phải khai mã đề của mình để hệ thống chọn đúng barem."
            ),
        )
    if not wanted:
        raise HTTPException(status_code=400, detail="File bài làm không có học sinh nào (khoá HS_1, HS_2, …).")

    by_ma_de: dict[str, BaremDoc] = {}
    for doc in db.query(BaremDoc).order_by(BaremDoc.updated_at.desc()).all():
        if doc.ma_de and str(doc.ma_de) in wanted and str(doc.ma_de) not in by_ma_de:
            # Newest wins when the library holds several for one code — the
            # alternative is refusing to grade over a stale duplicate.
            by_ma_de[str(doc.ma_de)] = doc

    unmatched = sorted(set(wanted) - set(by_ma_de))
    if unmatched:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Kho barem không có mã đề: {', '.join(unmatched)} "
                f"(bài làm có các mã đề {', '.join(sorted(wanted))}). "
                "Soạn hoặc tải barem cho những mã đề đó lên kho rồi chấm lại."
            ),
        )

    barem_dir.mkdir(parents=True, exist_ok=True)
    for ma_de, doc in sorted(by_ma_de.items()):
        (barem_dir / f"ma_de_{ma_de}.json").write_text(doc.content, encoding="utf-8")
    return sorted(by_ma_de)


@router.post("/jobs", response_model=GradingJobCreated)
async def create_grading_job(
    input_file: UploadFile,
    db: Session = Depends(get_db),
) -> GradingJobCreated:
    """Grade a Results-format JSON, picking a barem per student's `ma_de`.

    No barem is chosen by hand any more: the input says which exam code each
    student sat, and the library is searched for a rubric per code.
    """
    job_id = uuid.uuid4().hex
    job_dir = _JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_dir / "input.json"
    with input_path.open("wb") as f:
        shutil.copyfileobj(input_file.file, f)

    barem_dir = job_dir / "barems"
    ma_de_list = _materialise_barems(db, input_path, barem_dir)

    job = GradingJob(job_id=job_id, status=JobStatus.PENDING)
    db.add(job)
    db.commit()

    print(f"[grading] job {job_id}: mã đề {ma_de_list}", flush=True)
    job.worker_pid = _spawn_worker(
        job_id, input_path, barem_dir, job_dir / "output", job_dir / "worker.log"
    )
    db.commit()

    return GradingJobCreated(job_id=job_id, status=JobStatus.PENDING)


@router.get("/jobs", response_model=list[GradingJobStatus])
async def list_grading_jobs(db: Session = Depends(get_db)) -> list[GradingJob]:
    return list(
        db.query(GradingJob).order_by(GradingJob.created_at.desc()).limit(50).all()
    )


@router.get("/jobs/{job_id}", response_model=GradingJobStatus)
async def get_grading_job(job_id: str, db: Session = Depends(get_db)) -> GradingJob:
    job = db.get(GradingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.get("/jobs/{job_id}/result", response_model=GradingJobResult)
async def get_grading_job_result(job_id: str, db: Session = Depends(get_db)) -> GradingJobResult:
    job = db.get(GradingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=409, detail=f"job is not done yet (status: {job.status})")

    output_dir = _JOBS_DIR / job_id / "output"
    try:
        grading_results = json.loads((output_dir / "grading_results.json").read_text(encoding="utf-8"))
        student_summary = json.loads((output_dir / "student_summary.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"result files missing: {exc}") from exc

    return GradingJobResult(grading_results=grading_results, student_summary=student_summary)
