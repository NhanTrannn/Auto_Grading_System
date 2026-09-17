import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class GradingJob(Base):
    __tablename__ = "grading_jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    result_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # PID of the detached worker process, so a restart of THIS API process can
    # tell "the worker is still grading" from "the worker was killed" — see
    # app/services/job_recovery.py. Nullable: rows created before this column
    # existed have none, and ensure_columns() adds it to older databases.
    worker_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
