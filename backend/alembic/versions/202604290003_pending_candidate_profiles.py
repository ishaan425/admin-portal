"""allow pending candidate profiles before Clerk user creation"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "202604290003"
down_revision = "202604290002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            alter table candidate_profiles
            drop constraint if exists fk_candidate_profiles_member
            """
        )
    )
    op.execute(sa.text("alter table candidate_profiles drop constraint if exists candidate_profiles_pkey"))
    op.execute(
        sa.text(
            """
            alter table candidate_profiles
            rename column candidate_clerk_user_id to clerk_user_id
            """
        )
    )
    op.execute(sa.text("alter table candidate_profiles alter column clerk_user_id drop not null"))
    op.execute(sa.text("alter table candidate_profiles add column id uuid default gen_random_uuid()"))
    op.execute(sa.text("alter table candidate_profiles alter column id set not null"))
    op.execute(sa.text("alter table candidate_profiles add column email text"))
    op.execute(sa.text("alter table candidate_profiles add column full_name text"))
    op.execute(
        sa.text(
            """
            update candidate_profiles cp
            set email = m.email,
                full_name = m.full_name
            from organization_members m
            where m.organization_id = cp.organization_id
              and m.clerk_user_id = cp.clerk_user_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            update invitations
            set target_clerk_user_id = null
            where target_clerk_user_id like 'local_candidate_%'
            """
        )
    )
    op.execute(
        sa.text(
            """
            update candidate_profiles
            set clerk_user_id = null
            where clerk_user_id like 'local_candidate_%'
            """
        )
    )
    op.execute(
        sa.text(
            """
            delete from organization_members
            where clerk_user_id like 'local_candidate_%'
              and member_type = 'candidate'
            """
        )
    )
    op.execute(sa.text("alter table candidate_profiles alter column email set not null"))
    op.execute(sa.text("alter table candidate_profiles add constraint candidate_profiles_pkey primary key (id)"))
    op.execute(
        sa.text(
            """
            alter table candidate_profiles
            add constraint ux_candidate_profiles_org_id unique (organization_id, id)
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table candidate_profiles
            add constraint ux_candidate_profiles_org_email unique (organization_id, email)
            """
        )
    )
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
            alter table candidate_profiles
            add constraint ck_candidate_profiles_email_normalized
            check (email = lower(btrim(email)))
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table candidate_profiles
            add constraint ck_candidate_profiles_email_not_blank
            check (btrim(email) <> '')
            """
        )
    )
    op.execute(
        sa.text(
            """
            create unique index if not exists ux_candidate_profiles_org_clerk_user_id
            on candidate_profiles (organization_id, clerk_user_id)
            where clerk_user_id is not null
            """
        )
    )

    op.execute(sa.text("alter table invitations add column candidate_profile_id uuid"))
    op.execute(
        sa.text(
            """
            update invitations inv
            set candidate_profile_id = cp.id
            from candidate_profiles cp
            where cp.organization_id = inv.organization_id
              and (
                cp.clerk_user_id = inv.target_clerk_user_id
                or cp.email = inv.target_email
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            alter table invitations
            add constraint fk_invitations_candidate_profile
            foreign key (organization_id, candidate_profile_id)
            references candidate_profiles(organization_id, id)
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("alter table invitations drop constraint if exists fk_invitations_candidate_profile"))
    op.execute(sa.text("alter table invitations drop column if exists candidate_profile_id"))
    op.execute(sa.text("drop index if exists ux_candidate_profiles_org_clerk_user_id"))
    op.execute(sa.text("alter table candidate_profiles drop constraint if exists ck_candidate_profiles_email_not_blank"))
    op.execute(sa.text("alter table candidate_profiles drop constraint if exists ck_candidate_profiles_email_normalized"))
    op.execute(sa.text("alter table candidate_profiles drop constraint if exists fk_candidate_profiles_member"))
    op.execute(sa.text("alter table candidate_profiles drop constraint if exists ux_candidate_profiles_org_email"))
    op.execute(sa.text("alter table candidate_profiles drop constraint if exists ux_candidate_profiles_org_id"))
    op.execute(sa.text("alter table candidate_profiles drop constraint if exists candidate_profiles_pkey"))
    op.execute(
        sa.text(
            """
            insert into organization_members (
                organization_id,
                clerk_user_id,
                email,
                full_name,
                member_type,
                role_key,
                status
            )
            select
                cp.organization_id,
                'rollback_candidate_' || cp.id::text,
                cp.email,
                cp.full_name,
                'candidate',
                'candidate',
                'invited'
            from candidate_profiles cp
            where cp.clerk_user_id is null
            on conflict (organization_id, email) do nothing
            """
        )
    )
    op.execute(
        sa.text(
            """
            update candidate_profiles
            set clerk_user_id = 'rollback_candidate_' || id::text
            where clerk_user_id is null
            """
        )
    )
    op.execute(sa.text("alter table candidate_profiles alter column clerk_user_id set not null"))
    op.execute(sa.text("alter table candidate_profiles add constraint candidate_profiles_pkey primary key (organization_id, clerk_user_id)"))
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
    op.execute(sa.text("alter table candidate_profiles drop column if exists email"))
    op.execute(sa.text("alter table candidate_profiles drop column if exists full_name"))
    op.execute(sa.text("alter table candidate_profiles drop column if exists id"))
    op.execute(
        sa.text(
            """
            alter table candidate_profiles
            rename column clerk_user_id to candidate_clerk_user_id
            """
        )
    )
