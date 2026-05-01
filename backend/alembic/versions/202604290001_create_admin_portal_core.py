"""create admin portal core schema"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import op


revision = "202604290001"
down_revision = None
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
    _execute_sql_file("db/migrations/001_create_admin_portal_core.sql")


def downgrade() -> None:
    op.execute("drop table if exists invitations cascade")
    op.execute("drop table if exists resource_assignments cascade")
    op.execute("drop table if exists org_resources cascade")
    op.execute("drop table if exists role_permissions cascade")
    op.execute("drop table if exists candidate_profiles cascade")
    op.execute("drop table if exists organization_members cascade")
    op.execute("drop table if exists organization_roles cascade")
    op.execute("drop table if exists features cascade")
    op.execute("drop table if exists organizations cascade")
