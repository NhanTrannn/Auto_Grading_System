"""Saved-barem library, so a grading run can pick a rubric instead of uploading one.

Barems arrive either from the in-browser builder (`POST /barems`, JSON body)
or as an existing `.json` file (`POST /barems/upload`). Either way the rubric
is stored verbatim — this module never rewrites its contents, it only reads a
few top-level fields to fill the listing columns.
"""

import datetime
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.barem_doc import BaremDoc
from app.schemas.barem import BaremCreate, BaremDetail, BaremSummary, BaremUpdate

router = APIRouter()


def _meta_of(content: dict[str, Any]) -> dict[str, Any]:
    questions = content.get("teacher_barem")
    return {
        "ma_de": str(content["ma_de"]) if content.get("ma_de") is not None else None,
        "subject": content.get("subject"),
        "total_score": content.get("total_score"),
        "question_count": len(questions) if isinstance(questions, list) else 0,
    }


def _require_rubric(content: Any) -> dict[str, Any]:
    """`load_barem()` raises without these two, so reject them at the door."""
    if not isinstance(content, dict):
        raise HTTPException(status_code=400, detail="Barem phải là một object JSON.")
    if content.get("ma_de") is None:
        raise HTTPException(status_code=400, detail="Barem thiếu trường 'ma_de'.")
    if not isinstance(content.get("teacher_barem"), list):
        raise HTTPException(status_code=400, detail="Barem thiếu danh sách 'teacher_barem'.")
    return content


def _to_detail(doc: BaremDoc) -> BaremDetail:
    return BaremDetail(
        barem_id=doc.barem_id,
        name=doc.name,
        ma_de=doc.ma_de,
        subject=doc.subject,
        total_score=doc.total_score,
        question_count=doc.question_count,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        content=json.loads(doc.content),
    )


@router.get("", response_model=list[BaremSummary])
async def list_barems(db: Session = Depends(get_db)) -> list[BaremDoc]:
    return list(db.query(BaremDoc).order_by(BaremDoc.updated_at.desc()).all())


@router.post("", response_model=BaremDetail)
async def create_barem(payload: BaremCreate, db: Session = Depends(get_db)) -> BaremDetail:
    content = _require_rubric(payload.content)
    doc = BaremDoc(
        barem_id=uuid.uuid4().hex,
        name=payload.name.strip() or "Barem chưa đặt tên",
        content=json.dumps(content, ensure_ascii=False),
        **_meta_of(content),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _to_detail(doc)


@router.post("/upload", response_model=BaremDetail)
async def upload_barem(file: UploadFile, db: Session = Depends(get_db)) -> BaremDetail:
    try:
        content = json.loads((await file.read()).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"File không phải JSON hợp lệ: {exc}") from exc

    content = _require_rubric(content)
    doc = BaremDoc(
        barem_id=uuid.uuid4().hex,
        name=(file.filename or "barem.json").rsplit(".", 1)[0],
        content=json.dumps(content, ensure_ascii=False),
        **_meta_of(content),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _to_detail(doc)


@router.get("/{barem_id}", response_model=BaremDetail)
async def get_barem(barem_id: str, db: Session = Depends(get_db)) -> BaremDetail:
    doc = db.get(BaremDoc, barem_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="barem not found")
    return _to_detail(doc)


@router.put("/{barem_id}", response_model=BaremDetail)
async def update_barem(
    barem_id: str, payload: BaremUpdate, db: Session = Depends(get_db)
) -> BaremDetail:
    doc = db.get(BaremDoc, barem_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="barem not found")

    if payload.name is not None:
        doc.name = payload.name.strip() or doc.name
    if payload.content is not None:
        content = _require_rubric(payload.content)
        doc.content = json.dumps(content, ensure_ascii=False)
        for key, value in _meta_of(content).items():
            setattr(doc, key, value)
    # onupdate only fires when a mapped column actually changed; a name-only
    # edit would otherwise keep a stale updated_at and mis-sort the library.
    doc.updated_at = datetime.datetime.utcnow()

    db.commit()
    db.refresh(doc)
    return _to_detail(doc)


@router.delete("/{barem_id}")
async def delete_barem(barem_id: str, db: Session = Depends(get_db)) -> dict:
    doc = db.get(BaremDoc, barem_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="barem not found")
    db.delete(doc)
    db.commit()
    return {"deleted": barem_id}
