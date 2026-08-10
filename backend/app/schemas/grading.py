import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class GradingJobCreated(BaseModel):
    job_id: str
    status: JobStatus


class GradingJobStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: JobStatus
    error: str | None = None
    result_path: str | None = None
    created_at: datetime.datetime


class GradingJobResult(BaseModel):
    # Passed through as-is from pipeline.run_batch's own output files
    # (grading_results.json / student_summary.json) — shape is whatever
    # pipeline.py produces, not re-validated field-by-field here.
    grading_results: list[dict[str, Any]]
    student_summary: list[dict[str, Any]]
