"""Add columns that appeared in a model after its table was already created.

`Base.metadata.create_all` only ever CREATEs — it never ALTERs — so adding a
field to an existing model silently leaves older databases without the column
and every query against it fails. Alembic is the real answer (it is already in
requirements.txt); until the schema needs anything beyond new nullable
columns, this covers the one case that actually keeps happening.

Deliberately narrow: it only ever runs `ADD COLUMN`, and only for columns that
are nullable or carry a default. It never drops, renames or retypes anything,
so it cannot destroy data.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateColumn

logger = logging.getLogger("uvicorn.error")


def ensure_columns(engine: Engine, metadata) -> list[str]:
    """Add any model column missing from its existing table. Returns what it added."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []

    with engine.begin() as connection:
        for table in metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all just made it, or will
            present = {col["name"] for col in inspector.get_columns(table.name)}

            for column in table.columns:
                if column.name in present:
                    continue
                if not column.nullable and column.default is None and column.server_default is None:
                    # Can't backfill a NOT NULL column without a value; leave it
                    # to a real migration rather than guessing one.
                    logger.warning(
                        "Bỏ qua cột %s.%s: NOT NULL và không có default, cần migration thật.",
                        table.name,
                        column.name,
                    )
                    continue

                ddl = CreateColumn(column).compile(engine)
                connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {ddl}"))
                added.append(f"{table.name}.{column.name}")

    if added:
        logger.info("Đã thêm cột còn thiếu: %s", ", ".join(added))
    return added
