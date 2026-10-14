from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.config import get_settings
from app.db.migrate import ensure_columns
from app.db.session import Base, SessionLocal, engine
from app.services.job_recovery import fail_orphaned_jobs
from app.services.results_store import backfill_all
from app import models  # noqa: F401 - registers ORM models on Base before create_all

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Simple table creation for now — swap for Alembic migrations once the
    # schema needs to evolve without dropping data (requirements.txt already
    # includes alembic for that). create_all never ALTERs, so ensure_columns
    # covers the one case that keeps coming up: a new nullable column added to
    # a model whose table an older database already has.
    Base.metadata.create_all(bind=engine)
    ensure_columns(engine, Base.metadata)

    # A worker killed outright (container rebuild, machine off, OOM) never
    # reaches its own `except` block, so its row stays `running` and the UI
    # polls it forever. Sweep those here — but only the ones whose process is
    # really gone: workers are detached on purpose and a plain uvicorn restart
    # must not disturb a run still in progress. See app/services/job_recovery.py.
    db = SessionLocal()
    try:
        orphaned = fail_orphaned_jobs(db)
        if orphaned:
            print(f"[startup] {orphaned} phiên chấm mồ côi đã được đánh dấu failed", flush=True)

        # Runs finished before the result tables existed (or whose worker
        # couldn't write them) still only exist as files; load them once.
        # Cheap after the first time — it only touches rows with
        # ingested_at NULL — and never allowed to block startup.
        try:
            counts = backfill_all(db)
            if counts["uploads"] or counts["jobs"] or counts["failed"]:
                print(
                    f"[startup] Nạp vào database: {counts['jobs']} phiên, {counts['uploads']} lần upload"
                    + (f", {counts['failed']} phiên lỗi" if counts["failed"] else ""),
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            print(f"[startup] Bỏ qua nạp dữ liệu cũ: {type(exc).__name__}: {exc}", flush=True)
    finally:
        db.close()

    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
