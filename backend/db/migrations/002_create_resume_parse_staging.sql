-- Staging tables for bulk resume parsing results.
-- These tables store extracted JSON before candidate/profile onboarding decisions.

begin;

create table if not exists resume_parse_batches (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    uploaded_by_clerk_user_id text not null,
    status text not null default 'pending',
    total_files integer not null default 0,
    parsed_count integer not null default 0,
    failed_count integer not null default 0,
    created_at timestamptz not null default now(),
    completed_at timestamptz,
    constraint ux_resume_parse_batches_org_id unique (organization_id, id),
    constraint fk_resume_parse_batches_uploaded_by
        foreign key (organization_id, uploaded_by_clerk_user_id)
        references organization_members(organization_id, clerk_user_id),
    constraint ck_resume_parse_batches_status check (
        status in ('pending', 'processing', 'completed', 'completed_with_errors', 'failed')
    ),
    constraint ck_resume_parse_batches_counts check (
        total_files >= 0 and parsed_count >= 0 and failed_count >= 0
    )
);

create table if not exists resume_parse_items (
    id uuid primary key default gen_random_uuid(),
    batch_id uuid not null references resume_parse_batches(id) on delete cascade,
    organization_id uuid not null references organizations(id) on delete cascade,
    original_file_name text not null,
    resume_file_key text,
    parse_status text not null default 'pending',
    parsed_resume jsonb,
    parser_metadata jsonb not null default '{}'::jsonb,
    error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint fk_resume_parse_items_batch
        foreign key (organization_id, batch_id)
        references resume_parse_batches(organization_id, id)
        on delete cascade,
    constraint ck_resume_parse_items_file_name_not_blank check (btrim(original_file_name) <> ''),
    constraint ck_resume_parse_items_status check (
        parse_status in ('pending', 'processing', 'parsed', 'failed', 'skipped')
    ),
    constraint ck_resume_parse_items_parsed_resume_object check (
        parsed_resume is null or jsonb_typeof(parsed_resume) = 'object'
    ),
    constraint ck_resume_parse_items_parser_metadata_object check (
        jsonb_typeof(parser_metadata) = 'object'
    )
);

create index if not exists ix_resume_parse_batches_org_status
on resume_parse_batches (organization_id, status, created_at desc);

create index if not exists ix_resume_parse_items_batch_status
on resume_parse_items (batch_id, parse_status);

create index if not exists ix_resume_parse_items_org_created_at
on resume_parse_items (organization_id, created_at desc);

commit;
