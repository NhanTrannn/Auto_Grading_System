import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PipelineJob(Base):
    """One end-to-end run: student page images -> OCR -> grading.

    Deliberately a separate table from `grading_jobs` rather than extra
    columns on it: this job type has a two-stage lifecycle with real progress
    (N students x M ROIs of OCR, then grading), and `Base.metadata.create_all`
    does not ALTER existing tables, so widening `grading_jobs` would silently
    break every already-created database.
    """

    __tablename__ = "pipeline_jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    # Which half of the run is active: "ocr" | "grading" (None until started).
    stage: Mapped[str | None] = mapped_column(String, nullable=True)
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[str | None] = mapped_column(String, nullable=True)
    student_count: Mapped[int] = mapped_column(Integer, default=0)
    roi_count: Mapped[int] = mapped_column(Integer, default=0)
    # Which exam-code folder of the students ZIP this run covers, and the
    # library barem it was graded against — both shown in the job header.
    ma_de: Mapped[str | None] = mapped_column(String, nullable=True)
    barem_name: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    result_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
