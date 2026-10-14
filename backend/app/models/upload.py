import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Upload(Base):
    """One `POST /pipeline/uploads`: the students ZIP (+ optional template ZIP).

    Its files live in `var/pipeline_uploads/<upload_id>/`; this row exists so
    the database knows the upload at all — before it did, an upload that never
    became a job was invisible to everything but a directory listing, and
    nothing could tell an abandoned upload from one a job still depends on.
    """

    __tablename__ = "uploads"

    upload_id: Mapped[str] = mapped_column(String, primary_key=True)
    has_template: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
