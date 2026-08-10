"""Standalone grading worker, run as `python -m app.worker`.

Invoked as its own OS process (see app/api/routes/grading.py) rather than a
FastAPI BackgroundTask, so a grading run keeps going even if the `uvicorn`
process that started it is killed or restarted — the two no longer share a
process lifetime. It writes its own result directly to the grading_jobs
table via a fresh DB session; nothing about this needs to talk back to the
API process at all.
"""

import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.models.grading_job import GradingJob
from app.schemas.grading import JobStatus
from app.services.grading_engine import wrapper


def main() -> None:
    job_id, input_path, barem_path, output_dir = sys.argv[1:5]

    db = SessionLocal()
    try:
        job = db.get(GradingJob, job_id)
        job.status = JobStatus.RUNNING
        db.commit()

        # run_batch's third argument is a FILE path (it opens it directly
        # with open(..., "w")), not a directory — mirroring exactly what
        # pipeline.py's own CLI does before calling run_batch. Passing the
        # bare directory here previously created a plain file literally
        # named "output" (no extension) instead of a real output/ directory
        # containing grading_results.json, so downstream reads of
        # "<output_dir>/grading_results.json" all failed with FileNotFoundError.
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        result_file = out_dir / "grading_results.json"
        wrapper.run_batch(input_path, barem_path, str(result_file))

        job.status = JobStatus.DONE
        job.result_path = str(result_file)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - reported via job status, not raised
        job = db.get(GradingJob, job_id)
        job.status = JobStatus.FAILED
        job.error = str(exc)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
