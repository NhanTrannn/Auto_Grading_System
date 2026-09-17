"""Mark jobs whose worker process died as failed, at API startup.

Both workers (`app.worker`, `app.pipeline_worker`) wrap their whole run in
`except Exception` and set `status = failed`, so every *Python-level* failure
already reports itself. What they cannot report is being killed outright —
`docker stop`, a `compose up --build`, an OOM kill, a machine reboot. The row
then stays `running` forever and the UI polls a job that will never finish.
Observed live: a pipeline job frozen at "ocr 5/7" with a 0-byte crop file,
still `running` hours later, because a container rebuild cut the process
mid-write.

The catch is that "the API restarted" does NOT imply "the worker died".
Workers are deliberately spawned detached (DETACHED_PROCESS on Windows,
start_new_session on POSIX — see `app/api/routes/grading.py`) precisely so a
`uvicorn` restart leaves grading running. Blanket-failing every `running` row
at startup would therefore mark a perfectly healthy run as failed and throw
away a paid LLM batch. So each row records its worker's PID and we check that
PID before touching anything.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.grading_job import GradingJob
from app.models.pipeline_job import PipelineJob
from app.schemas.grading import JobStatus

_ORPHAN_ERROR = (
    "Tiến trình chấm bị dừng đột ngột (container restart / máy tắt / bị kill), "
    "không phải lỗi khi chấm. Kết quả đã chấm dở không được lưu — chạy lại phiên này."
)


def _alive_posix(pid: int, job_id: str) -> bool:
    """True only if PID `pid` is a live process whose command line names this job.

    Matching on the job_id, not just on "some process has this PID", is what
    makes this safe against PID reuse: after a reboot or a container restart
    the number is very likely handed to something unrelated, and treating that
    as a live worker would leave the zombie row in place forever.
    """
    cmdline = Path(f"/proc/{pid}/cmdline")
    try:
        # /proc separates argv entries with NULs.
        argv = cmdline.read_bytes().decode("utf-8", "replace")
    except OSError:
        # No /proc (macOS) or the process is gone. Fall back to a plain
        # existence probe; signal 0 never delivers anything on POSIX.
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    return job_id in argv


def _alive_windows(pid: int) -> bool:
    """True if PID `pid` is still running.

    Never use `os.kill` here: on Windows Python maps it to TerminateProcess
    for any signal that is not CTRL_C_EVENT/CTRL_BREAK_EVENT, so the usual
    POSIX "signal 0 to probe liveness" idiom would kill the worker it is
    supposed to be checking on.

    There is no cheap command-line check without psutil, so this cannot rule
    out PID reuse — a rebooted machine may hand the number to something else
    and the job stays `running`. That is the safe direction to be wrong in:
    a leftover row is visible and fixable, a wrongly-failed live run is a
    silently discarded paid batch.
    """
    import ctypes

    SYNCHRONIZE = 0x00100000
    WAIT_TIMEOUT = 0x00000102

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def worker_is_alive(pid: int | None, job_id: str) -> bool:
    """Is this job's worker still running?

    `pid is None` means the row predates PID tracking, or the process was
    never recorded — nothing to verify against, so the job is treated as dead.
    An unfinished job from an older release is dead by now anyway.
    """
    if not pid:
        return False
    if sys.platform == "win32":
        return _alive_windows(pid)
    return _alive_posix(pid, job_id)


def fail_orphaned_jobs(db: Session) -> int:
    """Fail every unfinished job whose worker is gone. Returns how many."""
    unfinished = (JobStatus.RUNNING.value, JobStatus.PENDING.value)
    orphaned = 0

    for model in (GradingJob, PipelineJob):
        for job in db.query(model).filter(model.status.in_(unfinished)).all():
            if worker_is_alive(job.worker_pid, job.job_id):
                continue
            job.status = JobStatus.FAILED.value
            job.error = _ORPHAN_ERROR
            orphaned += 1

    if orphaned:
        db.commit()
    return orphaned
