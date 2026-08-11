import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.grading import JobStatus


class TemplatePage(BaseModel):
    page: int
    filename: str


class UploadStudent(BaseModel):
    hs_key: str
    folder: str
    page_count: int


class UploadMaDe(BaseModel):
    ma_de: str
    student_count: int
    students: list[UploadStudent]


class UploadInventory(BaseModel):
    """What the two ZIPs turned out to contain — shown before anything runs."""

    upload_id: str
    template_pages: list[TemplatePage]
    ma_de_list: list[UploadMaDe]


class PipelineJobCreate(BaseModel):
    upload_id: str
    ma_de: str
    barem_id: str
    # The rubric's own ma_de, kept for the Results JSON. Falls back to the
    # barem's when omitted.
    roi_config: dict[str, Any]
    save_crops: bool = True


class PipelineJobCreated(BaseModel):
    job_id: str
    status: JobStatus
    student_count: int
    roi_count: int
    # hs_key -> the student folder it came from, so the mapping is never implicit.
    student_map: dict[str, str]


class PipelineJobStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: JobStatus
    stage: str | None = None
    progress_done: int = 0
    progress_total: int = 0
    progress_message: str | None = None
    student_count: int = 0
    roi_count: int = 0
    ma_de: str | None = None
    barem_name: str | None = None
    error: str | None = None
    created_at: datetime.datetime


class JobLog(BaseModel):
    """Incremental log tail: pass `next_offset` back as `offset` to continue."""

    text: str
    next_offset: int
    size: int
