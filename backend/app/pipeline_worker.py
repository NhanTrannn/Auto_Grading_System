"""End-to-end pipeline worker, run as `python -m app.pipeline_worker <job_id> <job_dir>`.

Runs both halves of a job in this one process: OCR every declared region
(ocr_main.build_results_json) and grade the resulting Results JSON
(pipeline.run_batch), writing progress straight to the pipeline_jobs table as
it goes.

Still its own OS process (spawned detached by api/routes/pipeline.py) rather
than a FastAPI BackgroundTask, for the same reason as the grading worker: a run
must survive the API restarting under it, and `--reload` restarts on every
source edit. What it is *not* anymore is a chain of three processes
(app -> ocr/main.py -> pipeline.py) coordinating through a progress file on
disk. That existed only because backend/ocr/ used to be unimportable from here
(a package named `app` colliding with this one, see services/ocr_engine.py);
both halves are plain imports now, so progress goes to the DB directly and
there is no snapshot file to poll, no polling interval to lag behind, and no
exit code to translate back into an error message — a failure is just an
exception with its real traceback.

backend/ocr/main.py still drives the same two steps for CLI use; it is simply
no longer in the web path.
"""

import json
import sys
import traceback
from pathlib import Path

from app.db.session import SessionLocal
from app.models.pipeline_job import PipelineJob
from app.schemas.grading import JobStatus
from app.services import ocr_engine
from app.services.grading_engine import wrapper


def main() -> None:
    job_id, job_dir_arg = sys.argv[1:3]
    job_dir = Path(job_dir_arg)

    configs_path = job_dir / "roi_configs.json"
    results_path = job_dir / "results.json"
    barem_dir = job_dir / "barems"
    graded_dir = job_dir / "graded"

    db = SessionLocal()

    def set_progress(stage: str, done: int, total: int, message: str) -> None:
        job = db.get(PipelineJob, job_id)
        if job is None:
            return
        job.stage = stage
        job.progress_done = done
        job.progress_total = total or job.progress_total
        job.progress_message = message
        db.commit()

    try:
        job = db.get(PipelineJob, job_id)
        job.status = JobStatus.RUNNING
        db.commit()
        set_progress("ocr", 0, 0, "Đang khởi động OCR")

        with configs_path.open("r", encoding="utf-8") as f:
            configs = json.load(f)

        save_crops = (job_dir / "save_crops").exists()

        # One OCR pass per exam code, because each code has its own blank pages
        # and its own regions. The results merge into a single Results JSON:
        # every student carries their own `ma_de`, so pipeline.py can pick the
        # right rubric per student from the barems directory afterwards.
        #
        # Progress is accumulated across codes rather than restarting at each
        # one, so the bar reflects the whole run.
        merged: dict = {}
        done_before = 0
        grand_total = sum(len(c["students"]) * len(c["rois"]) for c in configs)

        for config in configs:
            ma_de = config.get("ma_de")
            print(f"[worker] OCR mã đề {ma_de}: {len(config['students'])} học sinh", flush=True)

            offset = done_before

            def report(done: int, total: int, message: str, _offset: int = offset) -> None:
                set_progress("ocr", _offset + done, grand_total, f"[mã đề {ma_de}] {message}")

            result = ocr_engine.ocr_main.build_results_json(
                config, save_crops=save_crops, on_progress=report
            )
            # No collision handling needed: the route already numbered every
            # student uniquely across codes (_claim_hs_key), precisely so the
            # merge, the crop filenames and `student_index` all stay distinct.
            merged.update(result)
            done_before += len(config["students"]) * len(config["rois"])

        with results_path.open("w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

        n_students = sum(1 for k in merged if k.startswith("HS_"))
        print(
            f"[worker] OCR xong: {results_path} ({n_students} học sinh, "
            f"{len(configs)} mã đề)",
            flush=True,
        )

        set_progress("grading", 0, 1, "Đang chấm điểm bằng pipeline.py")
        graded_dir.mkdir(parents=True, exist_ok=True)
        result_file = graded_dir / "grading_results.json"
        # `barem_dir` holds one rubric per exam code; run_batch resolves the
        # directory and matches each student by their own `ma_de`. Its third
        # argument, though, is the OUTPUT FILE path, not a directory — it opens
        # that path directly (see app/worker.py for the same note).
        wrapper.run_batch(str(results_path), str(barem_dir), str(result_file))

        if not result_file.exists():
            raise FileNotFoundError(f"Không thấy file kết quả chấm: {result_file}")

        set_progress("done", 1, 1, "Hoàn tất")
        job = db.get(PipelineJob, job_id)
        job.status = JobStatus.DONE
        job.result_path = str(result_file)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - reported via job status, not raised
        # The traceback goes to the job's log file (this process's stdout is
        # redirected there), which the UI's live log panel already tails — so
        # the short message on the job row stays readable while the full stack
        # remains one click away.
        traceback.print_exc()
        sys.stdout.flush()
        db.rollback()
        job = db.get(PipelineJob, job_id)
        if job is not None:
            job.status = JobStatus.FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
