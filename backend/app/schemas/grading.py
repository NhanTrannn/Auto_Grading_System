from enum import Enum

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
