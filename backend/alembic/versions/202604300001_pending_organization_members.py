"""allow pending organization members before Clerk user creation"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "202604300001"
down_revision = "202604290003"
branch_labels = None
depends_on = None


MEMBER_FKS = [
    ("candidate_profiles", "fk_candidate_profiles_member"),
    ("org_resources", "fk_org_resources_created_by"),
    ("resource_assignments", "fk_resource_assignments_candidate"),
    ("resource_assignments", "fk_resource_assignments_assigned_by"),
    ("invitations", "fk_invitations_target_member"),
    ("invitations", "fk_invitations_invited_by"),
    ("resume_parse_batches", "fk_resume_parse_batches_uploaded_by"),
]


def upgrade() -> None:
    for table_name, constraint_name in MEMBER_FKS:
        op.execute(sa.text(f"alter table {table_name} drop constraint if exists {constraint_name}"))

    op.execute(sa.text("alter table organization_members drop constraint if exists organization_members_pkey"))
    op.execute(sa.text("alter table organization_members add column if not exists id uuid default gen_random_uuid()"))
    op.execute(sa.text("alter table organization_members alter column id set not null"))
    op.execute(sa.text("alter table organization_members add constraint organization_members_pkey primary key (id)"))
    op.execute(sa.text("alter table organization_members drop constraint if exists ck_organization_members_clerk_user_id_not_blank"))
    op.execute(sa.text("alter table organization_members alter column clerk_user_id drop not null"))
    op.execute(
        sa.text(
            """
            alter table organization_members
            add constraint ck_organization_members_clerk_user_id_not_blank
            check (clerk_user_id is null or btrim(clerk_user_id) <> '')
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table organization_members
            add constraint ux_organization_members_org_clerk_user_id
            unique (organization_id, clerk_user_id)
            """
        )
    )

    recreate_member_fks()


def downgrade() -> None:
    for table_name, constraint_name in MEMBER_FKS:
        op.execute(sa.text(f"alter table {table_name} drop constraint if exists {constraint_name}"))

    op.execute(
        sa.text(
            """
            update organization_members
            set clerk_user_id = 'rollback_member_' || id::text
            where clerk_user_id is null
            """
        )
    )
    op.execute(sa.text("alter table organization_members drop constraint if exists ux_organization_members_org_clerk_user_id"))
    op.execute(sa.text("alter table organization_members drop constraint if exists organization_members_pkey"))
    op.execute(sa.text("alter table organization_members drop constraint if exists ck_organization_members_clerk_user_id_not_blank"))
    op.execute(sa.text("alter table organization_members alter column clerk_user_id set not null"))
    op.execute(
        sa.text(
            """
            alter table organization_members
            add constraint ck_organization_members_clerk_user_id_not_blank
            check (btrim(clerk_user_id) <> '')
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table organization_members
            add constraint organization_members_pkey
            primary key (organization_id, clerk_user_id)
            """
        )
    )
    recreate_member_fks()
    op.execute(sa.text("alter table organization_members drop column if exists id"))


def recreate_member_fks() -> None:
    op.execute(
        sa.text(
            """
            alter table candidate_profiles
            add constraint fk_candidate_profiles_member
            foreign key (organization_id, clerk_user_id)
            references organization_members(organization_id, clerk_user_id)
            on delete cascade
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table org_resources
            add constraint fk_org_resources_created_by
            foreign key (organization_id, created_by_clerk_user_id)
            references organization_members(organization_id, clerk_user_id)
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table resource_assignments
            add constraint fk_resource_assignments_candidate
            foreign key (organization_id, candidate_clerk_user_id)
            references organization_members(organization_id, clerk_user_id)
            on delete cascade
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table resource_assignments
            add constraint fk_resource_assignments_assigned_by
            foreign key (organization_id, assigned_by_clerk_user_id)
            references organization_members(organization_id, clerk_user_id)
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table invitations
            add constraint fk_invitations_target_member
            foreign key (organization_id, target_clerk_user_id)
            references organization_members(organization_id, clerk_user_id)
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table invitations
            add constraint fk_invitations_invited_by
            foreign key (organization_id, invited_by_clerk_user_id)
            references organization_members(organization_id, clerk_user_id)
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table resume_parse_batches
            add constraint fk_resume_parse_batches_uploaded_by
            foreign key (organization_id, uploaded_by_clerk_user_id)
            references organization_members(organization_id, clerk_user_id)
            """
        )
    )
