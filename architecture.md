# GrowQR Admin Portal Technical Requirements

Date: April 22, 2026  
Reference Diagram: `docs/admin-portal-final-erd.png`

## 1. Objective

This document defines the current technical direction for the GrowQR Admin Portal database model. The model supports organization-level access control, Clerk-based authentication, candidate onboarding, resume/Qscore storage, courses/assessments/quizzes/jobs/roleplays, student portal assignment visibility, and invitation tracking.

The design target is:

```text
- PostgreSQL source-of-truth database
- compact schema
- tenant-safe data
- DB-driven roles and permissions
- Clerk-compatible identity
- no unnecessary tables
- only required indexes
```

Implementation boundary:

```text
All production persistence for the Admin Portal should be modeled for PostgreSQL.
Postgres-native capabilities such as jsonb, composite keys, foreign keys, and partial unique indexes are expected parts of the design.
Local experiments should not introduce SQLite-only behavior or schemas that diverge from the Postgres model.
```

## 2. Core Rule

`organizations.id` is the tenant boundary.

All organization-owned records are scoped to `organization_id`. Backend APIs must never trust organization scope only from frontend payload. The backend derives organization access from Clerk authentication plus `organization_members`.

Business meaning:

```text
Amity data stays under Amity.
Enterprise data stays under Enterprise.
The same candidate can exist in both, but resume/Qscore/assignments do not leak across organizations.
```

## 3. Tables

The model uses nine tables.

```text
1. organizations
2. organization_members
3. candidate_profiles
4. features
5. organization_roles
6. role_permissions
7. org_resources
8. resource_assignments
9. invitations
```

## 4. Table Requirements

### 4.1 organizations

Stores one organization/customer workspace.

Fields:

```text
id PK
name
slug
org_type
logo_url
status
created_at
updated_at
```

Reason:

```text
This table owns tenant identity, organization type, branding, and active/disabled state.
```

### 4.2 organization_members

Stores every person inside an organization.

Includes:

```text
admins
teachers
mentors
recruiters
enterprise HR users
placement coordinators
candidates/students
```

Fields:

```text
organization_id PK, FK -> organizations.id
clerk_user_id PK
email
full_name
member_type
role_key
status
created_at
updated_at
```

Primary key:

```text
(organization_id, clerk_user_id)
```

Reason:

```text
Clerk identifies the person; organization_id identifies the business context.
```

### 4.3 candidate_profiles

Stores candidate-only data.

Fields:

```text
id PK
organization_id FK
clerk_user_id nullable, FK -> organization_members.clerk_user_id
email
full_name
resume_file_key
resume_file_name
resume_data jsonb
qscore jsonb
resume_parse_status
resume_uploaded_at
updated_at
```

Relationship:

```text
candidate_profiles(organization_id, clerk_user_id)
    -> organization_members(organization_id, clerk_user_id)
```

Reason:

```text
Resume and Qscore fields belong only to candidates, so they stay outside admin/teacher/recruiter rows.
Pending invited candidates may exist before Clerk creates a real user_xxx id, so profiles use an internal UUID primary key.
The real Clerk user id is attached to clerk_user_id after invitation acceptance/webhook processing.
```

Storage rule:

```text
Original resumes go to private object storage.
Postgres stores only file keys and parsed JSON.
```

### 4.4 features

Stores GrowQR platform capabilities.

Fields:

```text
feature_key PK
category
status
```

Examples:

```text
organization_members
candidates
candidate_resumes
candidate_qscores
courses
assessments
quizzes
jobs
roleplays
reports
```

Reason:

```text
Backend permission checks need stable feature keys owned by GrowQR.
```

### 4.5 organization_roles

Stores approved roles inside an organization.

Fields:

```text
organization_id PK, FK -> organizations.id
role_key PK
name
status
```

Examples:

```text
org_admin
teacher
mentor
recruiter
enterprise_hr
placement_coordinator
candidate
viewer
```

Reason:

```text
Roles are organization-scoped so different organization types can receive different approved role sets.
```

### 4.6 role_permissions

Stores what each role can do for each feature.

Fields:

```text
organization_id PK, FK
role_key PK, FK
feature_key PK, FK
action_mask
```

Relationships:

```text
role_permissions(organization_id, role_key)
    -> organization_roles(organization_id, role_key)

role_permissions(feature_key)
    -> features(feature_key)
```

Action mask:

```text
1 read
2 create
4 update
8 delete
16 upload
32 publish
64 assign
128 export
```

Reason:

```text
action_mask is compact, fast to check, and avoids many permission columns.
```

### 4.7 org_resources

Stores organization-created content.

Resource types:

```text
course
assessment
quiz
job
roleplay
```

Fields:

```text
id PK
organization_id FK -> organizations.id
resource_type
created_by_clerk_user_id
title
status
metadata jsonb
created_at
updated_at
```

Relationship:

```text
org_resources(organization_id, created_by_clerk_user_id)
    -> organization_members(organization_id, clerk_user_id)
```

Reason:

```text
One compact resources table supports multiple product content types without creating separate tables too early.
```

### 4.8 resource_assignments

Controls which candidates can access which resources.

Fields:

```text
organization_id PK, FK
resource_id PK, FK -> org_resources.id
candidate_clerk_user_id PK, FK (real Clerk user id; assignments require accepted candidates)
assigned_by_clerk_user_id
status
assigned_at
```

Relationships:

```text
resource_assignments(resource_id)
    -> org_resources.id

resource_assignments(organization_id, candidate_clerk_user_id)
    -> organization_members(organization_id, clerk_user_id)

resource_assignments(organization_id, assigned_by_clerk_user_id)
    -> organization_members(organization_id, clerk_user_id)
```

Reason:

```text
Student portal visibility is assignment-based, not just organization-based.
```

### 4.9 invitations

Tracks Clerk invitation lifecycle.

Fields:

```text
id PK
organization_id FK -> organizations.id
candidate_profile_id nullable, FK -> candidate_profiles.id
target_clerk_user_id nullable
target_email
target_member_type
target_role_key
invited_by_clerk_user_id
clerk_invitation_id
status
error_message
created_at
sent_at
accepted_at
```

Reason:

```text
Admins and support need to track whether onboarding invites were sent, accepted, failed, expired, or revoked.
```

## 5. Backend Flow Requirements

### 5.1 Login And Authorization

```text
1. User logs in through Clerk.
2. Backend verifies Clerk JWT.
3. Backend finds organization_members by clerk_user_id.
4. Backend resolves organization_id and role_key.
5. Backend checks role_permissions for the requested feature/action.
6. Backend allows or rejects the request.
```

### 5.2 Creating Courses, Assessments, Quizzes, Jobs, Roleplays

```text
1. Member requests content creation.
2. Backend checks feature/action permission.
3. Backend inserts org_resources row.
4. metadata jsonb stores resource-specific details.
```

### 5.3 Assigning Content To Candidates

```text
1. Authorized member selects resource and candidates.
2. Backend verifies all candidates belong to same organization.
3. Backend inserts resource_assignments rows.
4. Student portal reads assignments for current candidate only.
```

### 5.4 Candidate Resume And Qscore

```text
1. Pending candidate profile may exist before organization_members if the candidate has not accepted a Clerk invite yet.
2. Resume file is stored in private object storage.
3. Parsed resume JSON is stored in candidate_profiles.resume_data.
4. Qscore is stored in candidate_profiles.qscore.
5. Access always requires matching organization_id.
```

### 5.5 Invitation Flow

```text
1. Admin invites candidate/member.
2. Backend checks invite permission.
3. Backend creates or updates a pending candidate_profiles row keyed by internal UUID.
4. Backend calls Clerk with candidate_profile_id in invitation metadata.
5. Backend stores clerk_invitation_id, candidate_profile_id, and status in invitations.
6. Clerk calls `POST /webhooks/clerk` after user creation/update.
7. Backend updates candidate_profiles.clerk_user_id, invitations.target_clerk_user_id, and invitation/member status.
```

## 6. Required Constraints

These constraints create indexes automatically.

```sql
-- organizations
primary key (id);
unique (slug);

-- organization_members
primary key (organization_id, clerk_user_id);
unique (organization_id, email);

-- candidate_profiles
primary key (id);
unique (organization_id, id);
unique (organization_id, email);

-- features
primary key (feature_key);

-- organization_roles
primary key (organization_id, role_key);

-- role_permissions
primary key (organization_id, role_key, feature_key);

-- org_resources
primary key (id);

-- resource_assignments
primary key (organization_id, resource_id, candidate_clerk_user_id);

-- invitations
primary key (id);
```

## 7. Required Explicit Indexes

Only five explicit indexes are required initially.

```sql
create index ix_organization_members_clerk_user_id
on organization_members (clerk_user_id);
```

One-line reason:

```text
Needed to resolve organization memberships during Clerk login.
```

```sql
create index ix_organization_members_org_member_type
on organization_members (organization_id, member_type);
```

One-line reason:

```text
Needed to list candidates/admins/teachers/recruiters inside one organization.
```

```sql
create index ix_org_resources_org_type_status
on org_resources (organization_id, resource_type, status);
```

One-line reason:

```text
Needed to list published courses, active jobs, quizzes, assessments, and roleplays by organization.
```

```sql
create index ix_resource_assignments_candidate
on resource_assignments (organization_id, candidate_clerk_user_id);
```

One-line reason:

```text
Needed for the student portal to fetch assigned resources for the logged-in candidate.
```

```sql
create unique index ux_candidate_profiles_org_clerk_user_id
on candidate_profiles (organization_id, clerk_user_id)
where clerk_user_id is not null;
```

One-line reason:

```text
Needed to link a pending profile to a real Clerk user after invitation acceptance while still allowing pending profiles without Clerk ids.
```

```sql
create unique index ux_invitations_clerk_invitation_id
on invitations (clerk_invitation_id)
where clerk_invitation_id is not null;
```

One-line reason:

```text
Needed to find and deduplicate invitation rows during Clerk webhook/callback processing.
```

## 8. Indexes Not Added Initially

Do not add these until query logs prove they are needed:

```sql
organization_members(organization_id, role_key);
org_resources(organization_id, created_by_clerk_user_id);
resource_assignments(organization_id, resource_id);
invitations(organization_id, target_email);
```

Reason:

```text
They may be useful later, but adding them now increases write cost and storage without a confirmed hot access path.
```

## 9. Implementation Notes

```text
- Store email as lower(trim(email)).
- Store resumes in object storage, not Postgres bytea.
- GrowQR owns feature_key definitions.
- GrowQR seeds approved role_key values per organization type.
- Organization admins assign existing roles and cannot create arbitrary feature keys.
- Backend must enforce permissions even if frontend hides unavailable UI.
- Additional indexes are added only after production query logs show need.
```

## 10. Summary

This model keeps the Admin Portal production-ready while staying compact.

```text
organizations provide tenant isolation.
organization_members connect Clerk users to org roles.
role_permissions control access to features.
org_resources store portal-created content.
resource_assignments control student/candidate visibility.
candidate_profiles isolate resume and Qscore data.
invitations track Clerk onboarding.
```

The initial indexing strategy is intentionally minimal:

```text
Use primary keys and unique constraints first.
Add only five explicit indexes for real high-frequency access paths.
Avoid speculative indexes until query behavior proves they are needed.
```
