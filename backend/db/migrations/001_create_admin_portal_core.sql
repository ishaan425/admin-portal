-- GrowQR Admin Portal core schema.
-- Target database: PostgreSQL.

begin;

create extension if not exists pgcrypto;

create table if not exists organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    slug text not null,
    org_type text not null,
    logo_url text,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ux_organizations_slug unique (slug),
    constraint ck_organizations_status check (status in ('active', 'disabled')),
    constraint ck_organizations_slug_not_blank check (btrim(slug) <> ''),
    constraint ck_organizations_name_not_blank check (btrim(name) <> '')
);

create table if not exists features (
    feature_key text primary key,
    category text not null,
    status text not null default 'active',
    constraint ck_features_key_not_blank check (btrim(feature_key) <> ''),
    constraint ck_features_status check (status in ('active', 'disabled'))
);

create table if not exists organization_roles (
    organization_id uuid not null references organizations(id) on delete cascade,
    role_key text not null,
    name text not null,
    status text not null default 'active',
    primary key (organization_id, role_key),
    constraint ck_organization_roles_key_not_blank check (btrim(role_key) <> ''),
    constraint ck_organization_roles_status check (status in ('active', 'disabled'))
);

create table if not exists organization_members (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    clerk_user_id text,
    email text not null,
    full_name text,
    member_type text not null,
    role_key text not null,
    status text not null default 'invited',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ux_organization_members_org_clerk_user_id unique (organization_id, clerk_user_id),
    constraint ux_organization_members_org_email unique (organization_id, email),
    constraint fk_organization_members_role
        foreign key (organization_id, role_key)
        references organization_roles(organization_id, role_key),
    constraint ck_organization_members_clerk_user_id_not_blank check (
        clerk_user_id is null or btrim(clerk_user_id) <> ''
    ),
    constraint ck_organization_members_email_normalized check (email = lower(btrim(email))),
    constraint ck_organization_members_member_type check (
        member_type in (
            'admin',
            'teacher',
            'mentor',
            'recruiter',
            'enterprise_hr',
            'placement_coordinator',
            'candidate',
            'viewer'
        )
    ),
    constraint ck_organization_members_status check (
        status in ('invited', 'active', 'disabled', 'removed')
    )
);

create table if not exists candidate_profiles (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null,
    clerk_user_id text,
    email text not null,
    full_name text,
    resume_file_key text,
    resume_file_name text,
    resume_data jsonb not null default '{}'::jsonb,
    qscore jsonb not null default '{}'::jsonb,
    resume_parse_status text not null default 'not_uploaded',
    resume_uploaded_at timestamptz,
    qr_token text,
    qr_status text not null default 'not_created',
    qr_created_at timestamptz,
    qr_expires_at timestamptz,
    last_qr_scanned_at timestamptz,
    updated_at timestamptz not null default now(),
    constraint ux_candidate_profiles_org_id unique (organization_id, id),
    constraint ux_candidate_profiles_org_email unique (organization_id, email),
    constraint fk_candidate_profiles_member
        foreign key (organization_id, clerk_user_id)
        references organization_members(organization_id, clerk_user_id)
        on delete cascade,
    constraint ck_candidate_profiles_email_normalized check (email = lower(btrim(email))),
    constraint ck_candidate_profiles_email_not_blank check (btrim(email) <> ''),
    constraint ck_candidate_profiles_resume_parse_status check (
        resume_parse_status in ('not_uploaded', 'pending', 'parsed', 'failed')
    ),
    constraint ck_candidate_profiles_qr_status check (
        qr_status in ('not_created', 'active', 'disabled', 'expired')
    )
);

create table if not exists role_permissions (
    organization_id uuid not null,
    role_key text not null,
    feature_key text not null references features(feature_key) on delete cascade,
    action_mask integer not null,
    primary key (organization_id, role_key, feature_key),
    constraint fk_role_permissions_role
        foreign key (organization_id, role_key)
        references organization_roles(organization_id, role_key)
        on delete cascade,
    constraint ck_role_permissions_action_mask check (action_mask >= 0 and action_mask <= 255)
);

create table if not exists org_resources (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    resource_type text not null,
    created_by_clerk_user_id text not null,
    title text not null,
    status text not null default 'draft',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ux_org_resources_org_id unique (organization_id, id),
    constraint fk_org_resources_created_by
        foreign key (organization_id, created_by_clerk_user_id)
        references organization_members(organization_id, clerk_user_id),
    constraint ck_org_resources_type check (
        resource_type in ('course', 'assessment', 'quiz', 'job', 'roleplay')
    ),
    constraint ck_org_resources_status check (
        status in ('draft', 'active', 'published', 'archived', 'disabled')
    ),
    constraint ck_org_resources_title_not_blank check (btrim(title) <> '')
);

create table if not exists resource_assignments (
    organization_id uuid not null references organizations(id) on delete cascade,
    resource_id uuid not null references org_resources(id) on delete cascade,
    candidate_clerk_user_id text not null,
    assigned_by_clerk_user_id text not null,
    status text not null default 'active',
    assigned_at timestamptz not null default now(),
    primary key (organization_id, resource_id, candidate_clerk_user_id),
    constraint fk_resource_assignments_resource
        foreign key (organization_id, resource_id)
        references org_resources(organization_id, id)
        on delete cascade,
    constraint fk_resource_assignments_candidate
        foreign key (organization_id, candidate_clerk_user_id)
        references organization_members(organization_id, clerk_user_id)
        on delete cascade,
    constraint fk_resource_assignments_assigned_by
        foreign key (organization_id, assigned_by_clerk_user_id)
        references organization_members(organization_id, clerk_user_id),
    constraint ck_resource_assignments_status check (
        status in ('active', 'revoked', 'completed')
    )
);

create table if not exists invitations (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    candidate_profile_id uuid,
    target_clerk_user_id text,
    target_email text not null,
    target_member_type text not null,
    target_role_key text not null,
    invited_by_clerk_user_id text not null,
    clerk_invitation_id text,
    status text not null default 'pending',
    error_message text,
    created_at timestamptz not null default now(),
    sent_at timestamptz,
    accepted_at timestamptz,
    constraint fk_invitations_candidate_profile
        foreign key (organization_id, candidate_profile_id)
        references candidate_profiles(organization_id, id),
    constraint fk_invitations_target_member
        foreign key (organization_id, target_clerk_user_id)
        references organization_members(organization_id, clerk_user_id),
    constraint fk_invitations_role
        foreign key (organization_id, target_role_key)
        references organization_roles(organization_id, role_key),
    constraint fk_invitations_invited_by
        foreign key (organization_id, invited_by_clerk_user_id)
        references organization_members(organization_id, clerk_user_id),
    constraint ck_invitations_target_email_normalized check (target_email = lower(btrim(target_email))),
    constraint ck_invitations_target_member_type check (
        target_member_type in (
            'admin',
            'teacher',
            'mentor',
            'recruiter',
            'enterprise_hr',
            'placement_coordinator',
            'candidate',
            'viewer'
        )
    ),
    constraint ck_invitations_status check (
        status in ('pending', 'sent', 'accepted', 'failed', 'expired', 'revoked')
    )
);

create index if not exists ix_organization_members_clerk_user_id
on organization_members (clerk_user_id);

create index if not exists ix_organization_members_org_member_type
on organization_members (organization_id, member_type);

create index if not exists ix_org_resources_org_type_status
on org_resources (organization_id, resource_type, status);

create index if not exists ix_resource_assignments_candidate
on resource_assignments (organization_id, candidate_clerk_user_id);

create unique index if not exists ux_candidate_profiles_org_clerk_user_id
on candidate_profiles (organization_id, clerk_user_id)
where clerk_user_id is not null;

create unique index if not exists ux_invitations_clerk_invitation_id
on invitations (clerk_invitation_id)
where clerk_invitation_id is not null;

create unique index if not exists ux_candidate_profiles_qr_token
on candidate_profiles (qr_token)
where qr_token is not null;

commit;
