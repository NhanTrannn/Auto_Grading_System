"""Load existing run files into the result tables by hand.

    python -m app.db.backfill              # every run not loaded yet
    python -m app.db.backfill <job_id> --force   # reload one run from its files

The API does the first form automatically at startup; this is for doing it
without a restart, or for rebuilding one run. `--force` discards that run's
rows first — including any OCR corrections or teacher overrides made on it.
"""

import sys

from app import models  # noqa: F401 - registers every model before create_all
from app.db.migrate import ensure_columns
from app.db.session import Base, SessionLocal, engine
from app.services.results_store import backfill_all, ingest_pipeline_job


def main() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_columns(engine, Base.metadata)
    args = sys.argv[1:]
    db = SessionLocal()
    try:
        if args and not args[0].startswith("-"):
            done = ingest_pipeline_job(db, args[0], force="--force" in args)
            print("Đã nạp." if done else "Không nạp (không có file, hoặc đã nạp rồi — thêm --force để nạp lại).")
        else:
            print(backfill_all(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
