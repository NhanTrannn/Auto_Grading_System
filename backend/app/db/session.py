from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_IS_SQLITE = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
)


if _IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:
        """Per-connection SQLite settings — none of these persist on their own.

        - foreign_keys: SQLite ships with FK enforcement OFF, so without this
          every `ondelete="CASCADE"` in the models is decorative and deleting a
          job would leave its submissions/results orphaned.
        - journal_mode=WAL: a pipeline worker (separate process) commits
          progress several times a second while the API serves reads; in the
          default rollback-journal mode a reader blocks the writer and either
          side can hit "database is locked". WAL lets them run concurrently.
        - busy_timeout: when two writers do collide, wait up to 10s instead of
          failing on the first contention.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
