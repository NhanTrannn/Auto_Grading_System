"""Managing pipeline data: deleting runs, reclaiming disk, teacher corrections.

Mounted under `/pipeline` next to `routes/pipeline.py`, which creates and
serves runs; this module changes them after the fact. Everything here works
on the result tables (`app.models.results`), never on the run's files except
to delete them.
"""

from __future__ import annotations

import datetime
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.pipeline_job import PipelineJob
from app.models.results import (
    AnswerRegion,
    CriterionResult,
    QuestionResult,
    StudentSubmission,
    TeacherOverride,
)
from app.models.upload import Upload
from app.schemas.grading import JobStatus
from app.services import results_store
from app.services.job_recovery import worker_is_alive

router = APIRouter()

# An upload with no run is normally abandoned — but for the first stretch after
# uploading, the teacher is still on the "map the regions" screen and the run
# doesn't exist *yet*. Cleaning only older uploads keeps that window safe.
ORPHAN_UPLOAD_MIN_AGE = datetime.timedelta(hours=24)


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


# ── deleting a run ──────────────────────────────────────────────────────────


@router.delete("/jobs/{job_id}")
async def delete_pipeline_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    """Delete a run: its row (results cascade with it) and its directory.

    Refused while its worker is still alive, which would otherwise keep
    writing into a directory that no longer exists. The upload it read from
    is kept — another run may use it, and the storage cleanup handles it once
    nothing does.
    """
    job = db.get(PipelineJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên chấm.")
    if job.status in (JobStatus.PENDING, JobStatus.RUNNING) and worker_is_alive(job.worker_pid, job_id):
        raise HTTPException(status_code=409, detail="Phiên đang chạy — đợi chạy xong rồi mới xoá được.")

    job_dir = results_store.JOBS_DIR / job_id
    freed = _dir_size(job_dir)
    # ORM delete of the children first, so the cascade also works on a
    # database whose FK constraints predate this code (ALTER-added columns
    # carry none); on a fresh one ON DELETE CASCADE would do it anyway.
    for submission in db.query(StudentSubmission).filter(StudentSubmission.job_id == job_id).all():
        db.delete(submission)
    db.delete(job)
    db.commit()
    shutil.rmtree(job_dir, ignore_errors=True)
    return {"deleted": job_id, "freed_bytes": freed}


# ── storage ─────────────────────────────────────────────────────────────────


def _uploads_in_use(db: Session) -> set[str]:
    used = {u for (u,) in db.query(PipelineJob.upload_id).filter(PipelineJob.upload_id.isnot(None)).all()}
    # Runs not yet ingested may lack upload_id; their roi_configs.json still
    # names the upload in every page path, so check the text directly rather
    # than risk deleting the pages of a run nobody has loaded yet.
    for (job_id,) in db.query(PipelineJob.job_id).filter(PipelineJob.upload_id.is_(None)).all():
        configs = results_store.JOBS_DIR / job_id / "roi_configs.json"
        if configs.exists():
            text = configs.read_text(encoding="utf-8")
            used.update(m.group(1) for m in results_store.UPLOAD_IN_PATH.finditer(text.replace("\\", "/")))
    return used


def _storage_plan(db: Session) -> dict:
    uploads_dir = results_store.UPLOADS_DIR
    in_use = _uploads_in_use(db)
    cutoff = datetime.datetime.now() - ORPHAN_UPLOAD_MIN_AGE

    orphans: list[Path] = []
    leftover_zips: list[Path] = []
    if uploads_dir.is_dir():
        for folder in uploads_dir.iterdir():
            if not folder.is_dir():
                continue
            leftover_zips.extend(z for z in folder.glob("*.zip") if z.is_file())
            modified = datetime.datetime.fromtimestamp(folder.stat().st_mtime)
            if folder.name not in in_use and modified < cutoff:
                orphans.append(folder)

    orphan_set = set(orphans)
    zips_outside_orphans = [z for z in leftover_zips if z.parent not in orphan_set]
    return {
        "orphans": orphans,
        "zips": zips_outside_orphans,
        "summary": {
            "jobs_count": db.query(PipelineJob).count(),
            "jobs_bytes": _dir_size(results_store.JOBS_DIR),
            "uploads_count": len([f for f in uploads_dir.iterdir() if f.is_dir()]) if uploads_dir.is_dir() else 0,
            "uploads_bytes": _dir_size(uploads_dir),
            "orphan_uploads_count": len(orphans),
            "orphan_uploads_bytes": sum(_dir_size(f) for f in orphans),
            "leftover_zip_bytes": sum(z.stat().st_size for z in zips_outside_orphans),
        },
    }


@router.get("/storage")
async def get_storage(db: Session = Depends(get_db)) -> dict:
    return _storage_plan(db)["summary"]


@router.post("/storage/cleanup")
async def cleanup_storage(db: Session = Depends(get_db)) -> dict:
    """Delete uploads no run uses (older than a day) and archives already unpacked."""
    plan = _storage_plan(db)
    freed = plan["summary"]["orphan_uploads_bytes"] + plan["summary"]["leftover_zip_bytes"]
    for folder in plan["orphans"]:
        shutil.rmtree(folder, ignore_errors=True)
        upload = db.get(Upload, folder.name)
        if upload is not None:
            db.delete(upload)
    for archive in plan["zips"]:
        archive.unlink(missing_ok=True)
    db.commit()
    return {
        "removed_uploads": len(plan["orphans"]),
        "removed_zips": len(plan["zips"]),
        "freed_bytes": freed,
        "storage": _storage_plan(db)["summary"],
    }


# ── teacher corrections ─────────────────────────────────────────────────────


def _submission(db: Session, job_id: str, hs_key: str) -> StudentSubmission:
    submission = (
        db.query(StudentSubmission)
        .filter(StudentSubmission.job_id == job_id, StudentSubmission.hs_key == hs_key)
        .one_or_none()
    )
    if submission is None:
        # A finished run whose files were never loaded (e.g. the worker's
        # ingest failed) — load it now rather than refusing the edit.
        if results_store.ingest_pipeline_job(db, job_id):
            return _submission(db, job_id, hs_key)
        raise HTTPException(status_code=404, detail=f"Không tìm thấy {hs_key} trong phiên này.")
    return submission


@router.get("/jobs/{job_id}/edits")
async def get_job_edits(job_id: str, db: Session = Depends(get_db)) -> dict:
    """Every OCR correction in a run, keyed `{hs_key: {cau_key: {...}}}`.

    Score overrides aren't listed here: they are already applied to
    `/jobs/{id}/result` (as `teacher_override` on each criterion), which is
    what every screen reads scores from.
    """
    rows = (
        db.query(AnswerRegion, StudentSubmission.hs_key)
        .join(StudentSubmission, AnswerRegion.submission_id == StudentSubmission.id)
        .filter(StudentSubmission.job_id == job_id, AnswerRegion.ocr_text_corrected.isnot(None))
        .all()
    )
    corrections: dict[str, dict[str, dict]] = {}
    for region, hs_key in rows:
        corrections.setdefault(hs_key, {})[region.cau_key] = {
            "text": region.ocr_text_corrected,
            "corrected_by": region.corrected_by,
            "corrected_at": region.corrected_at.isoformat() if region.corrected_at else None,
        }
    return {"ocr_corrections": corrections}


class OcrCorrection(BaseModel):
    # None or "" clears the correction, falling back to what OCR read.
    text: str | None = None
    corrected_by: str | None = None


@router.put("/jobs/{job_id}/students/{hs_key}/regions/{cau_key}/ocr")
async def correct_ocr(
    job_id: str, hs_key: str, cau_key: str, body: OcrCorrection, db: Session = Depends(get_db)
) -> dict:
    """Record what the student actually wrote, when OCR misread it.

    The OCR reading itself (`ocr_text`) is never overwritten, so the
    correction stays auditable. This does not re-grade: the score came from
    the misread text, and changing it is the teacher's call via an override.
    """
    submission = _submission(db, job_id, hs_key)
    region = (
        db.query(AnswerRegion)
        .filter(AnswerRegion.submission_id == submission.id, AnswerRegion.cau_key == cau_key)
        .one_or_none()
    )
    if region is None:
        raise HTTPException(status_code=404, detail=f"Không có vùng {cau_key} của {hs_key}.")
    cleared = body.text is None or body.text == "" or body.text == region.ocr_text
    region.ocr_text_corrected = None if cleared else body.text
    region.corrected_by = None if cleared else (body.corrected_by or None)
    region.corrected_at = None if cleared else datetime.datetime.utcnow()
    db.commit()
    return {"cau_key": cau_key, "text": region.ocr_text_corrected}


class ScoreOverride(BaseModel):
    new_score: float = Field(ge=0)
    note: str | None = None
    created_by: str | None = None


@router.post("/jobs/{job_id}/students/{hs_key}/criteria/{criterion_id}/override")
async def override_criterion(
    job_id: str, hs_key: str, criterion_id: str, body: ScoreOverride, db: Session = Depends(get_db)
) -> dict:
    """Set a criterion's score by hand. Appends to the audit trail, never edits it.

    Posting the machine's own score back is how an override is undone — it
    stays in the history as "returned to the AI score".
    """
    submission = _submission(db, job_id, hs_key)
    criterion = (
        db.query(CriterionResult)
        .join(QuestionResult, CriterionResult.question_result_id == QuestionResult.id)
        .filter(QuestionResult.submission_id == submission.id, CriterionResult.criterion_id == criterion_id)
        .first()
    )
    if criterion is None:
        raise HTTPException(status_code=404, detail=f"Không có tiêu chí {criterion_id} của {hs_key}.")
    if criterion.max_score is not None and body.new_score > criterion.max_score + 1e-9:
        raise HTTPException(
            status_code=400, detail=f"Điểm tối đa của {criterion_id} là {criterion.max_score:g}."
        )
    raw = json.loads(criterion.raw or "{}")
    # Same test aggregate_with_group_rules() uses: a group_id alone is just
    # weight-split scoring, summed like any other criterion.
    if raw.get("group_id") and (raw.get("group_all_or_nothing") or raw.get("group_llm_decided")):
        # Its points are decided for the whole group (all-or-nothing or by the
        # LLM), not summed from members, so changing one member's score would
        # move the total by an amount the group rule never awards.
        raise HTTPException(
            status_code=409,
            detail=f"{criterion_id} thuộc nhóm {raw['group_id']} được tính điểm chung — chưa hỗ trợ sửa điểm từng tiêu chí trong nhóm.",
        )

    previous = criterion.overrides[-1].new_score if criterion.overrides else criterion.score
    override = TeacherOverride(
        criterion_result_id=criterion.id,
        old_score=previous,
        new_score=body.new_score,
        note=body.note or None,
        created_by=body.created_by or None,
    )
    db.add(override)
    if submission.total_score is not None and previous is not None:
        submission.total_score = round(submission.total_score + body.new_score - previous, 4)
    db.commit()
    return {
        "criterion_id": criterion_id,
        "ai_score": criterion.score,
        "old_score": previous,
        "new_score": body.new_score,
        "history": len(criterion.overrides),
    }
