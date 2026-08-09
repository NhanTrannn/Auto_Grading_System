import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.grading_job import GradingJob
from app.schemas.grading import GradingJobCreated, GradingJobStatus, JobStatus

router = APIRouter()

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_JOBS_DIR = _BACKEND_ROOT / "var" / "jobs"


def _spawn_worker(job_id: str, input_path: Path, barem_path: Path, output_dir: Path, log_path: Path) -> None:
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

    with log_path.open("wb") as log_file:
        subprocess.Popen(
            [sys.executable, "-m", "app.worker", job_id, str(input_path), str(barem_path), str(output_dir)],
            cwd=str(_BACKEND_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **kwargs,
        )


@router.post("/jobs", response_model=GradingJobCreated)
async def create_grading_job(
    input_file: UploadFile,
    barem_file: UploadFile,
    db: Session = Depends(get_db),
) -> GradingJobCreated:
    job_id = uuid.uuid4().hex
    job_dir = _JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_dir / "input.json"
    barem_path = job_dir / "barem.json"
    with input_path.open("wb") as f:
        shutil.copyfileobj(input_file.file, f)
    with barem_path.open("wb") as f:
        shutil.copyfileobj(barem_file.file, f)

    job = GradingJob(job_id=job_id, status=JobStatus.PENDING)
    db.add(job)
    db.commit()

    _spawn_worker(job_id, input_path, barem_path, job_dir / "output", job_dir / "worker.log")

    return GradingJobCreated(job_id=job_id, status=JobStatus.PENDING)


@router.get("/jobs/{job_id}", response_model=GradingJobStatus)
async def get_grading_job(job_id: str, db: Session = Depends(get_db)) -> GradingJob:
    job = db.get(GradingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
