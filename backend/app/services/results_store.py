"""Load a pipeline run's output files into the result tables.

The worker still writes everything to `var/pipeline_jobs/<job_id>/` exactly as
before — `roi_configs.json` (regions + page paths), `results.json` (OCR),
`graded/grading_results.json` + `student_summary.json` (scores), `crops/` —
and the existing endpoints still serve those files. This module reads the same
files once, at the end of a run, and writes them into the tables in
`app.models.results` so they can be queried, corrected and audited.

Used from three places:
- `app.pipeline_worker`, right after a run finishes (or fails after OCR);
- the API startup back-fill, for runs that predate these tables;
- `python -m app.db.backfill`, to do the same by hand.

Ingestion is one-shot per run. Results are immutable once graded, and the
tables then accumulate things the files don't have (OCR corrections, teacher
overrides) — rebuilding a run's rows from its files would silently throw
those away, so a run that already has submissions is skipped unless the
caller explicitly forces it.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.barem_doc import BaremDoc
from app.models.pipeline_job import PipelineJob
from app.models.results import (
    AnswerRegion,
    CriterionResult,
    JobExam,
    QuestionResult,
    SourcePage,
    StudentSubmission,
    TeacherOverride,
)
from app.models.upload import Upload

BACKEND_ROOT = Path(__file__).resolve().parents[2]
VAR_DIR = BACKEND_ROOT / "var"
JOBS_DIR = VAR_DIR / "pipeline_jobs"
UPLOADS_DIR = VAR_DIR / "pipeline_uploads"

# Same pattern pipeline.py's convert_results_to_samples() uses, so a region is
# filed under exactly the question the grader graded it as.
_CAU_KEY = re.compile(r"Cau_(\d+)([a-z]?)(?:_(\d+))?$", re.IGNORECASE)
UPLOAD_IN_PATH = re.compile(r"pipeline_uploads/([0-9a-f]{32})/")


def var_relative(path: str | Path) -> str:
    """Store paths relative to var/, never absolute.

    Absolute paths differ between Docker (`/app/var/...`) and a bare-metal
    install (`/srv/.../backend/var/...`), so the same database would point at
    nothing after moving between them — which is exactly what happened to
    `pipeline_jobs.result_path`. Relative paths survive the move.
    """
    text = str(path).replace("\\", "/")
    for marker in ("pipeline_uploads/", "pipeline_jobs/"):
        index = text.find(marker)
        if index >= 0:
            return text[index:]
    return text


def question_number_of(cau_key: str) -> int | None:
    match = _CAU_KEY.match(cau_key)
    return int(match.group(1)) if match else None


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _text(value) -> str | None:
    return value if isinstance(value, str) and value != "" else None


def _ocr_text(content) -> str | None:
    """OCR content is `{"lines": [...]}`; join lines exactly as pipeline.py does
    for a single-part answer (with "\\n", nothing stripped)."""
    if isinstance(content, dict) and isinstance(content.get("lines"), list):
        return "\n".join(str(line) for line in content["lines"])
    return None


# ── uploads ─────────────────────────────────────────────────────────────────


def register_upload(db: Session, upload_id: str, has_template: bool) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None:
        upload = Upload(upload_id=upload_id, has_template=has_template)
        db.add(upload)
    return upload


def backfill_uploads(db: Session) -> int:
    """Register every upload directory that has no row yet."""
    if not UPLOADS_DIR.is_dir():
        return 0
    known = {u for (u,) in db.query(Upload.upload_id).all()}
    added = 0
    for folder in sorted(UPLOADS_DIR.iterdir()):
        if not folder.is_dir() or folder.name in known:
            continue
        db.add(
            Upload(
                upload_id=folder.name,
                has_template=(folder / "template").is_dir(),
                created_at=datetime.datetime.utcfromtimestamp(folder.stat().st_mtime),
            )
        )
        added += 1
    db.commit()
    return added


# ── job exams (barem per exam code) ─────────────────────────────────────────


def record_job_exam(
    db: Session, job_id: str, ma_de: str, barem: BaremDoc | None, barem_content: str | None
) -> None:
    db.add(
        JobExam(
            job_id=job_id,
            ma_de=str(ma_de),
            barem_id=barem.barem_id if barem else None,
            barem_name=barem.name if barem else None,
            barem_content=barem_content,
        )
    )


def _backfill_job_exams(db: Session, job: PipelineJob, job_dir: Path, configs: list[dict]) -> None:
    """For runs created before job_exams existed.

    The barem actually used is the snapshot in `<job>/barems/ma_de_<code>.json`.
    The live library link is recovered by name: `pipeline_jobs.barem_name` is
    the names joined with ", " in the same order as the configs — matched only
    when exactly one library barem has that name, never guessed otherwise.
    """
    if db.query(JobExam).filter(JobExam.job_id == job.job_id).count():
        return
    names = [n.strip() for n in (job.barem_name or "").split(", ")] if job.barem_name else []
    for index, config in enumerate(configs):
        ma_de = str(config.get("ma_de"))
        snapshot_path = job_dir / "barems" / f"ma_de_{ma_de}.json"
        snapshot = snapshot_path.read_text(encoding="utf-8") if snapshot_path.exists() else None
        name = names[index] if index < len(names) else None
        barem = None
        if name:
            matches = db.query(BaremDoc).filter(BaremDoc.name == name).all()
            barem = matches[0] if len(matches) == 1 else None
        db.add(
            JobExam(
                job_id=job.job_id,
                ma_de=ma_de,
                barem_id=barem.barem_id if barem else None,
                barem_name=name,
                barem_content=snapshot,
            )
        )


# ── submissions ─────────────────────────────────────────────────────────────


def _student_of(sample_id: str) -> str:
    """`cau_1_001__HS_14` → `HS_14` (same split the frontend uses)."""
    index = sample_id.rfind("__")
    return sample_id[index + 2 :] if index >= 0 else sample_id


def _source_folder(pages: list[str]) -> str | None:
    """The student's folder name in the ZIP, from their first page's path:
    `.../students/<code folder>/<student folder>/<file>`."""
    if not pages:
        return None
    parts = var_relative(pages[0]).split("/")
    return parts[-2] if len(parts) >= 2 else None


def _criterion_row(cr: dict) -> CriterionResult:
    evidence = cr.get("evidence") if isinstance(cr.get("evidence"), dict) else {}
    return CriterionResult(
        criterion_id=str(cr.get("criterion_id")),
        part_label=_text(cr.get("part_label")),
        score=_num(cr.get("score")),
        max_score=_num(cr.get("max_score")),
        status=_text(cr.get("status")),
        stage=_text(cr.get("stage")),
        grading_method=_text(cr.get("grading_method")),
        criterion_content=_text(cr.get("criterion_content")) or _text(cr.get("content")),
        student_answer=_text(evidence.get("student_answer")),
        llm_reasoning=_text(cr.get("llm_reasoning")) or _text(cr.get("reason")),
        suggestion=_text(cr.get("suggestion")),
        heuristic_score=_num(cr.get("heuristic_score")),
        llm_score=_num(cr.get("llm_score")),
        confidence=_num(cr.get("confidence")),
        teacher_review_required=bool(cr.get("teacher_review_required")),
        raw=json.dumps(cr, ensure_ascii=False),
    )


def ingest_pipeline_job(db: Session, job_id: str, *, force: bool = False) -> bool:
    """Load one run's files into the result tables. Returns True if it did.

    Works on a partial run too: if OCR finished but grading failed, the
    submissions, pages and OCR regions are still recorded (no question rows).
    Commits on success; the caller's session is left clean either way.
    """
    job = db.get(PipelineJob, job_id)
    if job is None:
        return False
    job_dir = JOBS_DIR / job_id
    configs = _read_json(job_dir / "roi_configs.json")
    if not configs:
        return False

    existing = db.query(StudentSubmission).filter(StudentSubmission.job_id == job_id)
    if existing.count():
        if not force:
            return False
        # ORM delete so the cascades run even on a connection without FK
        # enforcement; FK ON DELETE CASCADE covers raw SQL deletes.
        for submission in existing.all():
            db.delete(submission)
        db.flush()

    ocr = _read_json(job_dir / "results.json") or {}
    graded = _read_json(job_dir / "graded" / "grading_results.json") or []
    summary = {row["hs"]: row for row in (_read_json(job_dir / "graded" / "student_summary.json") or [])}
    crops_dir = job_dir / "crops"

    samples_by_student: dict[str, list[dict]] = {}
    for sample in graded:
        samples_by_student.setdefault(_student_of(str(sample.get("sample_id", ""))), []).append(sample)

    upload_id: str | None = None

    for config in configs:
        ma_de = config.get("ma_de")
        rois = config.get("rois") or []
        for student in config.get("students") or []:
            hs_key = student["hs_key"]
            pages = student.get("pages") or []
            if upload_id is None and pages:
                match = UPLOAD_IN_PATH.search(var_relative(pages[0]))
                upload_id = match.group(1) if match else None

            totals = summary.get(hs_key)
            samples = samples_by_student.get(hs_key, [])
            submission = StudentSubmission(
                job_id=job_id,
                hs_key=hs_key,
                ma_de=str(ma_de) if ma_de is not None else None,
                source_folder=_source_folder(pages),
                total_score=_num(totals.get("score")) if totals else None,
                max_score=_num(totals.get("max_score")) if totals else None,
                needs_review=any(bool(s.get("teacher_review_required")) for s in samples),
            )

            for number, page in enumerate(pages, start=1):
                submission.pages.append(SourcePage(page_number=number, image_path=var_relative(page)))

            student_ocr = ocr.get(hs_key) if isinstance(ocr.get(hs_key), dict) else {}
            for roi in rois:
                cau_key = roi["cau_key"]
                entry = student_ocr.get(cau_key) if isinstance(student_ocr.get(cau_key), dict) else {}
                crop = crops_dir / f"{hs_key}_{cau_key}.png"
                submission.regions.append(
                    AnswerRegion(
                        cau_key=cau_key,
                        question_number=question_number_of(cau_key),
                        task_type=roi.get("task_type"),
                        page_number=int(roi.get("page", 1) or 1),
                        x=_num(roi.get("x")),
                        y=_num(roi.get("y")),
                        w=_num(roi.get("w")),
                        h=_num(roi.get("h")),
                        crop_path=var_relative(crop) if crop.exists() else None,
                        ocr_status=_text(entry.get("status")),
                        ocr_text=_ocr_text(entry.get("content")),
                        ocr_raw=json.dumps(entry, ensure_ascii=False) if entry else None,
                    )
                )

            for sample in samples:
                tokens = sample.get("token_usage") if isinstance(sample.get("token_usage"), dict) else {}
                question = QuestionResult(
                    question_number=int(sample.get("question_number") or 0),
                    score=_num(sample.get("score")),
                    max_score=_num(sample.get("max_score")),
                    status=_text(sample.get("status")),
                    teacher_review_required=bool(sample.get("teacher_review_required")),
                    grading_method=_text(sample.get("grading_method")),
                    latency_ms=_num(sample.get("latency_ms")),
                    total_tokens=int(tokens["total_tokens"]) if isinstance(tokens.get("total_tokens"), int) else None,
                    group_overrides=(
                        json.dumps(sample["group_overrides"], ensure_ascii=False)
                        if sample.get("group_overrides")
                        else None
                    ),
                )
                for cr in sample.get("criterion_results") or []:
                    question.criteria.append(_criterion_row(cr))
                submission.questions.append(question)

            db.add(submission)

    _backfill_job_exams(db, job, job_dir, configs)

    if upload_id and job.upload_id is None:
        register_upload(db, upload_id, has_template=(UPLOADS_DIR / upload_id / "template").is_dir())
        job.upload_id = upload_id
    job.ingested_at = datetime.datetime.utcnow()
    db.commit()
    return True


# ── teacher edits ───────────────────────────────────────────────────────────


def _status_for(score: float, max_score: float) -> str:
    if max_score and score >= max_score - 1e-9:
        return "correct"
    if score <= 1e-9:
        return "wrong"
    return "partially_correct"


def latest_overrides(db: Session, job_id: str) -> dict[tuple[str, str], tuple[TeacherOverride, CriterionResult]]:
    """{(hs_key, criterion_id): (newest override, the criterion row)} for one run."""
    rows = (
        db.query(TeacherOverride, CriterionResult, StudentSubmission.hs_key)
        .join(CriterionResult, TeacherOverride.criterion_result_id == CriterionResult.id)
        .join(QuestionResult, CriterionResult.question_result_id == QuestionResult.id)
        .join(StudentSubmission, QuestionResult.submission_id == StudentSubmission.id)
        .filter(StudentSubmission.job_id == job_id)
        .order_by(TeacherOverride.created_at, TeacherOverride.id)
        .all()
    )
    latest: dict[tuple[str, str], tuple[TeacherOverride, CriterionResult]] = {}
    for override, criterion, hs_key in rows:
        latest[(hs_key, criterion.criterion_id)] = (override, criterion)  # later rows win
    return latest


def apply_overrides(db: Session, job_id: str, grading_results: list[dict], summary: list[dict]) -> None:
    """Rewrite the served result so a teacher's score is THE score.

    The files keep the machine's verdict untouched; this overlays the newest
    override per criterion on the way out, so the results table, the review
    screen and the PDF all agree without each re-implementing the arithmetic.
    The machine's own score stays visible as `ai_score`.

    Question and student totals move by the delta. That is exact for plain
    criteria; group-scored criteria (all_or_nothing / LLM-decided) can't be
    overridden in the first place — see `override_criterion`.
    """
    latest = latest_overrides(db, job_id)
    if not latest:
        return
    by_hs = {row["hs"]: row for row in summary}
    touched: set[str] = set()

    for sample in grading_results:
        hs_key = _student_of(str(sample.get("sample_id", "")))
        delta = 0.0
        for cr in sample.get("criterion_results") or []:
            hit = latest.get((hs_key, str(cr.get("criterion_id"))))
            if hit is None:
                continue
            override, _criterion = hit
            ai_score = _num(cr.get("score")) or 0.0
            max_score = _num(cr.get("max_score")) or 0.0
            if abs(override.new_score - ai_score) < 1e-9:
                # "Hoàn về điểm máy chấm" is recorded as an override back to
                # the AI score; the audit trail keeps it, but the criterion is
                # no longer teacher-scored and shouldn't be badged as such.
                continue
            cr["ai_score"] = ai_score
            cr["ai_status"] = cr.get("status")
            cr["score"] = override.new_score
            cr["status"] = _status_for(override.new_score, max_score)
            cr["teacher_override"] = {
                "new_score": override.new_score,
                "old_score": override.old_score,
                "note": override.note,
                "created_by": override.created_by,
                "created_at": override.created_at.isoformat() if override.created_at else None,
            }
            delta += override.new_score - ai_score
        if delta:
            sample["score"] = round((_num(sample.get("score")) or 0.0) + delta, 4)
            sample["status"] = _status_for(sample["score"], _num(sample.get("max_score")) or 0.0)
            if hs_key in by_hs:
                by_hs[hs_key]["score"] = round((_num(by_hs[hs_key].get("score")) or 0.0) + delta, 4)
                touched.add(hs_key)

    # `wrong` lists the questions not at full marks; recompute it for anyone
    # whose scores moved instead of patching it question by question.
    for hs_key in touched:
        by_hs[hs_key]["wrong"] = [
            str(s.get("question_number"))
            for s in grading_results
            if _student_of(str(s.get("sample_id", ""))) == hs_key
            and (_num(s.get("score")) or 0.0) < (_num(s.get("max_score")) or 0.0) - 1e-9
        ]


def backfill_all(db: Session) -> dict[str, int]:
    """Register stray uploads and ingest every run not yet in the tables."""
    uploads = backfill_uploads(db)
    pending = (
        db.query(PipelineJob.job_id)
        .filter(PipelineJob.ingested_at.is_(None), PipelineJob.status.in_(("done", "failed")))
        .all()
    )
    ingested = failed = 0
    for (job_id,) in pending:
        try:
            if ingest_pipeline_job(db, job_id):
                ingested += 1
        except Exception as exc:  # noqa: BLE001 - one bad run must not stop the rest
            db.rollback()
            failed += 1
            print(f"[results_store] Không nạp được phiên {job_id}: {type(exc).__name__}: {exc}", flush=True)
    return {"uploads": uploads, "jobs": ingested, "failed": failed}
