-- Local development seed for a dummy LPU organization.

begin;

insert into organizations (id, name, slug, org_type, logo_url, status)
values (
    '11111111-1111-4111-8111-111111111111',
    'LPU',
    'lpu',
    'university',
    '',
    'active'
)
on conflict (slug) do update
set
    name = excluded.name,
    org_type = excluded.org_type,
    logo_url = excluded.logo_url,
    status = excluded.status,
    updated_at = now();

insert into organization_roles (organization_id, role_key, name, status)
values
    ('11111111-1111-4111-8111-111111111111', 'org_admin', 'Organization Admin', 'active'),
    ('11111111-1111-4111-8111-111111111111', 'candidate', 'Candidate', 'active')
on conflict (organization_id, role_key) do update
set
    name = excluded.name,
    status = excluded.status;

insert into organization_members (
    organization_id,
    clerk_user_id,
    email,
    full_name,
    member_type,
    role_key,
    status
)
values (
    '11111111-1111-4111-8111-111111111111',
    'local_lpu_admin',
    'admin@lpu.local',
    'LPU Local Admin',
    'admin',
    'org_admin',
    'active'
)
on conflict (organization_id, clerk_user_id) do update
set
    email = excluded.email,
    full_name = excluded.full_name,
    member_type = excluded.member_type,
    role_key = excluded.role_key,
    status = excluded.status,
    updated_at = now();

commit;
