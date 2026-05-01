"""seed jobs feature key"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "202605010001"
down_revision = "202604300001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            insert into features (feature_key, category, status)
            values ('jobs', 'resources', 'active')
            on conflict (feature_key) do update
            set category = excluded.category,
                status = excluded.status
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("delete from features where feature_key = 'jobs'"))
