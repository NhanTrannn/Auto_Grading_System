import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BaremDoc(Base):
    """A saved barem, so a grading run can pick one instead of re-uploading a file.

    The rubric itself is kept verbatim as a JSON string in `content`: it is
    consumed by `pipeline.load_barem()`, whose schema lives in the barem JSON
    (see structure/structure_parem.txt) and evolves independently of this
    table. Only the few fields the library UI lists are mirrored into columns.
    """

    __tablename__ = "barem_docs"

    barem_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    ma_de: Mapped[str | None] = mapped_column(String, nullable=True)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
