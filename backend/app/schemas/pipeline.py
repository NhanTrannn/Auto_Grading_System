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
    # Blank-exam pages that apply to this code. `template_shared` is true when
    # they came from a template archive with no per-code folders, i.e. the same
    # pages serve every code.
    template_pages: list[TemplatePage] = []
    template_shared: bool = True


class UploadInventory(BaseModel):
    """What the two ZIPs turned out to contain — shown before anything runs."""

    upload_id: str
    template_pages: list[TemplatePage]
    ma_de_list: list[UploadMaDe]


class PipelineJobGroup(BaseModel):
    """One exam code in a run: its own regions, on its own template pages."""

    ma_de: str
    roi_config: dict[str, Any]
    # Optional escape hatch from ma_de-based barem matching: normally the
    # rubric is looked up in the library by this group's `ma_de` (see
    # PipelineJobCreate docstring), which requires a barem in the library
    # declaring the exact same `ma_de` — fine when the teacher's zip already
    # follows the `Made_N` folder convention, but pointless busywork when they
    # just want "these images, this one rubric, don't bother checking codes."
    # When set, `/jobs` fetches this barem by id directly and skips the
    # ma_de lookup entirely — the picked barem does not need to declare a
    # matching (or any) `ma_de` of its own; see `create_pipeline_job`, which
    # rewrites the barem's own `ma_de` field to this group's `ma_de` before
    # writing it out, so pipeline.py's per-student ma_de match still succeeds
    # regardless of what code the library barem was originally tagged with.
    barem_id: str | None = None


class PipelineJobCreate(BaseModel):
    """A run covers one or more exam codes at once.

    Each code's rubric is looked up in the library by `ma_de` by default, the
    same way `/grading/jobs` does it — unless a group sets its own
    `barem_id` (see `PipelineJobGroup`), which picks a specific library barem
    directly and skips that lookup. Regions stay per code because two codes
    rarely place their answers in the same spot on the page.
    """

    upload_id: str
    groups: list[PipelineJobGroup]
    save_crops: bool = True


class PipelineJobCreated(BaseModel):
    job_id: str
    status: JobStatus
    student_count: int
    roi_count: int
    ma_de_list: list[str]
    # hs_key -> the student folder it came from, so the mapping is never
    # implicit. Keys are prefixed with the exam code when a run covers several,
    # because two codes can each have their own HS_1.
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
