"""create resume parse staging schema"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import op


revision = "202604290002"
down_revision = "202604290001"
branch_labels = None
depends_on = None


def _execute_sql_file(relative_path: str) -> None:
    root = Path(__file__).resolve().parents[2]
    sql = (root / relative_path).read_text(encoding="utf-8")
    for statement in sql.split(";"):
        cleaned = statement.strip()
        if cleaned and cleaned.lower() not in {"begin", "commit"}:
            op.execute(sa.text(cleaned))


def upgrade() -> None:
    _execute_sql_file("db/migrations/002_create_resume_parse_staging.sql")


def downgrade() -> None:
    op.execute("drop table if exists resume_parse_items cascade")
    op.execute("drop table if exists resume_parse_batches cascade")
