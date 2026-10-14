"""Per-student results of a pipeline run, normalised out of the JSON files.

A run used to exist in the database only as one `pipeline_jobs` row whose
`result_path` pointed at `grading_results.json`; every score, every OCR line,
every crop and every LLM reason lived in files under `var/pipeline_jobs/<id>/`.
That made the questions a teacher actually asks — "which students got câu 5
wrong", "which answers did OCR fail to read", "what did this student's score
look like before I fixed it" — unanswerable without opening JSON by hand.

The files are still written exactly as before and remain what the UI reads
today; these tables are filled from them by `app.services.results_store` once a
run finishes (and back-filled for runs that predate the tables). Images stay
on disk — only their paths, relative to `var/`, are stored here.

Tree, each level `ON DELETE CASCADE` from its parent:

    pipeline_jobs
      ├─ job_exams              one per exam code in the run (+ barem snapshot)
      └─ student_submissions    one per student
           ├─ source_pages      the photographed pages
           ├─ answer_regions    one per cropped answer box: geometry, crop, OCR
           └─ question_results  one per question
                └─ criterion_results   one per graded criterion
                     └─ teacher_overrides   manual score changes, newest last
"""

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


class JobExam(Base):
    """Which barem graded which exam code in a run.

    `barem_id` is the live link (NULL once that barem is deleted from the
    library); `barem_name` and `barem_content` are what it was *at grading
    time*, so a later edit to the library never rewrites history. The job row
    itself only ever had a comma-joined name string.
    """

    __tablename__ = "job_exams"
    __table_args__ = (UniqueConstraint("job_id", "ma_de"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_jobs.job_id", ondelete="CASCADE"), index=True
    )
    ma_de: Mapped[str] = mapped_column(String)
    barem_id: Mapped[str | None] = mapped_column(
        ForeignKey("barem_docs.barem_id", ondelete="SET NULL"), nullable=True, index=True
    )
    barem_name: Mapped[str | None] = mapped_column(String, nullable=True)
    barem_content: Mapped[str | None] = mapped_column(Text, nullable=True)


class StudentSubmission(Base):
    """One student's paper within one run.

    `hs_key` is only unique inside its run (every run has an `HS_1`), so it is
    paired with `job_id`. `source_folder` is the student's folder name in the
    uploaded ZIP — the only real-world identifier the system receives, and
    previously returned to the browser once at job creation and then lost.
    """

    __tablename__ = "student_submissions"
    __table_args__ = (UniqueConstraint("job_id", "hs_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_jobs.job_id", ondelete="CASCADE"), index=True
    )
    hs_key: Mapped[str] = mapped_column(String)
    ma_de: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source_folder: Mapped[str | None] = mapped_column(String, nullable=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    pages: Mapped[list["SourcePage"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", passive_deletes=True
    )
    regions: Mapped[list["AnswerRegion"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", passive_deletes=True
    )
    questions: Mapped[list["QuestionResult"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", passive_deletes=True
    )


class SourcePage(Base):
    __tablename__ = "source_pages"
    __table_args__ = (UniqueConstraint("submission_id", "page_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("student_submissions.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    # Relative to var/, e.g. "pipeline_uploads/<upload_id>/students/made_49/HS_6/p1.jpg"
    image_path: Mapped[str] = mapped_column(String)

    submission: Mapped[StudentSubmission] = relationship(back_populates="pages")


class AnswerRegion(Base):
    """One cropped answer box: where it was cut from, the crop, and its OCR.

    `ocr_text` is what the OCR model returned and is never edited;
    `ocr_text_corrected` is a teacher's fix, kept separately so the original
    reading stays auditable and OCR accuracy can be measured against it.
    """

    __tablename__ = "answer_regions"
    __table_args__ = (UniqueConstraint("submission_id", "cau_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("student_submissions.id", ondelete="CASCADE"), index=True
    )
    cau_key: Mapped[str] = mapped_column(String)
    question_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    task_type: Mapped[str | None] = mapped_column(String, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Page-relative box, each in 0..1 — the same units the roi_config uses.
    x: Mapped[float | None] = mapped_column(Float, nullable=True)
    y: Mapped[float | None] = mapped_column(Float, nullable=True)
    w: Mapped[float | None] = mapped_column(Float, nullable=True)
    h: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_path: Mapped[str | None] = mapped_column(String, nullable=True)
    ocr_status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_text_corrected: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_by: Mapped[str | None] = mapped_column(String, nullable=True)
    corrected_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    submission: Mapped[StudentSubmission] = relationship(back_populates="regions")


class QuestionResult(Base):
    __tablename__ = "question_results"
    __table_args__ = (UniqueConstraint("submission_id", "question_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("student_submissions.id", ondelete="CASCADE"), index=True
    )
    question_number: Mapped[int] = mapped_column(Integer, index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    teacher_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    grading_method: Mapped[str | None] = mapped_column(String, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # all_or_nothing / LLM-decided groups (see pipeline.py) as JSON — rare,
    # and only ever displayed, so not worth their own table.
    group_overrides: Mapped[str | None] = mapped_column(Text, nullable=True)

    submission: Mapped[StudentSubmission] = relationship(back_populates="questions")
    criteria: Mapped[list["CriterionResult"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", passive_deletes=True
    )


class CriterionResult(Base):
    """One graded criterion. The columns are what the UI and report read;
    `raw` keeps the full pipeline.py dict so nothing it emits is lost."""

    __tablename__ = "criterion_results"
    __table_args__ = (UniqueConstraint("question_result_id", "criterion_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_result_id: Mapped[int] = mapped_column(
        ForeignKey("question_results.id", ondelete="CASCADE"), index=True
    )
    criterion_id: Mapped[str] = mapped_column(String, index=True)
    part_label: Mapped[str | None] = mapped_column(String, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    stage: Mapped[str | None] = mapped_column(String, nullable=True)
    grading_method: Mapped[str | None] = mapped_column(String, nullable=True)
    criterion_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    student_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    heuristic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    teacher_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    question: Mapped[QuestionResult] = relationship(back_populates="criteria")
    overrides: Mapped[list["TeacherOverride"]] = relationship(
        back_populates="criterion",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TeacherOverride.created_at",
    )


class TeacherOverride(Base):
    """A teacher's manual change to one criterion's score.

    Appended, never updated: the newest row is the effective score and the
    older ones are the audit trail. `created_by` is a free-text name until the
    app has user accounts.
    """

    __tablename__ = "teacher_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    criterion_result_id: Mapped[int] = mapped_column(
        ForeignKey("criterion_results.id", ondelete="CASCADE"), index=True
    )
    old_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_score: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    criterion: Mapped[CriterionResult] = relationship(back_populates="overrides")
