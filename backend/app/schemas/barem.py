import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BaremSummary(BaseModel):
    """Listing shape — deliberately without `content` (a barem is tens of KB)."""

    model_config = ConfigDict(from_attributes=True)

    barem_id: str
    name: str
    ma_de: str | None = None
    subject: str | None = None
    total_score: float | None = None
    question_count: int = 0
    created_at: datetime.datetime
    updated_at: datetime.datetime


class BaremDetail(BaremSummary):
    content: dict[str, Any]


class BaremCreate(BaseModel):
    """Push from the barem builder: the whole rubric as a JSON object."""

    name: str
    content: dict[str, Any]


class BaremUpdate(BaseModel):
    name: str | None = None
    content: dict[str, Any] | None = None
