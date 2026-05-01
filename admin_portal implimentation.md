# GrowQR Admin Portal Implementation Plan

Date: April 27, 2026

## Purpose

This document captures what is already implemented, what is agreed architecturally, and what we are going to implement next for the GrowQR Admin Portal.

The immediate delivery goal is:

```text
organization admin uploads candidate data
-> backend processes candidate intake
-> candidate is created under the correct organization
-> Clerk invitation is generated
-> candidate accepts invite
-> candidate profile is linked
-> candidate Qscore/QR-based identity becomes available
```

This is the working implementation plan, not only a conceptual architecture note.

---

## 1. Current Product Direction

The admin portal is being built as a multi-tenant system where:

```text
GrowQR manages multiple organizations
each organization has its own members
each organization has its own candidates
each organization has its own branding
each organization has its own content/resources
```

Core product capabilities in scope:

```text
- organization-scoped login and access control
- bulk candidate intake
- resume parsing and candidate enrichment
- Clerk-based candidate onboarding
- dynamic organization-branded invitation emails
- candidate Qscore storage
- QR-linked candidate public access for Qscore visibility
- future support for courses, assessments, quizzes, jobs, and roleplays
```

---

## 2. What Is Already Implemented

The prototype scripts have been replaced by the current backend API, worker,
and reusable service modules.

### 2.1 Reusable Clerk invitation client

[backend/integrations/clerk_client.py](backend/integrations/clerk_client.py)

Purpose:

```text
- centralize Clerk invitation API calls
- centralize payload building
- make invite creation reusable by worker/backend code
```

### 2.2 Bulk resume upload API and worker step

The old local JSON parsing script has been removed. Resume uploads now flow
through the FastAPI boundary and queue-backed worker.

Purpose:

```text
- API stores uploaded PDFs in private object storage
- API creates resume_parse_batches and resume_parse_items records
- API enqueues the batch and returns quickly
- worker parses resumes with OpenAI extraction
- worker sends Clerk invites and updates Postgres
```

Reusable service:

[services/resume_parser.py](services/resume_parser.py)

Current boundary:

```text
bulk uploaded resumes -> object storage + queued parse/invite workflow
```

Next boundary:

```text
candidate intake workflow -> richer admin review and assignment tools
```

---

## 3. Agreed Data Model Direction

Database target:

```text
PostgreSQL is the source-of-truth database for the Admin Portal.
```

Implementation implications:

```text
- schema design should use Postgres-native constraints and indexes
- parsed resume data and Qscore data should use jsonb columns
- invitation dedupe should use a Postgres partial unique index
- original resume files should live in private object storage, not Postgres bytea
- local prototypes should not introduce SQLite-specific assumptions
```

The working data model is based on these nine tables:

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

### 3.1 organizations

Stores tenant/workspace information.

Key responsibilities:

```text
- tenant identity
- org name
- org type
- org logo URL
- active/disabled state
```

### 3.2 organization_members

Stores every person in an organization.

Includes:

```text
- admin
- teacher
- mentor
- recruiter
- enterprise HR
- placement coordinator
- candidate
```

Primary key:

```text
(organization_id, clerk_user_id)
```

Reason:

```text
The same Clerk user can exist in multiple organizations, but each membership stays isolated by organization.
```

### 3.3 candidate_profiles

Stores candidate-only data.

Current scope:

```text
- resume file reference
- parsed resume JSON
- Qscore JSON
- resume parse status
- QR token / QR status / QR timestamps
```

Reason:

```text
Candidate-specific fields should not sit on teacher/admin/recruiter rows.
```

### 3.4 features, organization_roles, role_permissions

These tables make access DB-driven.

Purpose:

```text
- define platform capabilities
- define org-approved roles
- map roles to feature access
```

Permission strategy:

```text
action_mask
1 read
2 create
4 update
8 delete
16 upload
32 publish
64 assign
128 export
```

### 3.5 org_resources

Stores organization-created business content in one compact table.

Current intended types:

```text
course
assessment
quiz
job
roleplay
```

Reason:

```text
One shared table keeps the first production version compact.
```

### 3.6 resource_assignments

Controls which candidates can access which resources.

Purpose:

```text
student/candidate portal visibility should be assignment-based, not only organization-based
```

### 3.7 invitations

Tracks Clerk invitation lifecycle.

Purpose:

```text
- record invite attempts
- store Clerk invitation IDs
- track send / accept / fail state
- support retries and debugging
```

---

## 4. Indexing Strategy

We are intentionally keeping indexing minimal and production-oriented.

### 4.1 Automatically created by PK/unique constraints

We rely first on:

```text
- primary keys
- unique constraints
```

These already create important indexes such as:

```text
organization_members(organization_id, clerk_user_id)
organization_members(organization_id, email)
organization_roles(organization_id, role_key)
role_permissions(organization_id, role_key, feature_key)
candidate_profiles(id)
candidate_profiles(organization_id, email)
resource_assignments(organization_id, resource_id, candidate_clerk_user_id)
```

### 4.2 Explicit indexes we are intentionally keeping

Only these five are required initially:

```text
1. organization_members(clerk_user_id)
2. organization_members(organization_id, member_type)
3. org_resources(organization_id, resource_type, status)
4. resource_assignments(organization_id, candidate_clerk_user_id)
5. candidate_profiles(organization_id, clerk_user_id) partial unique index
6. invitations(clerk_invitation_id) partial unique index
```

Why:

```text
1. login lookup
2. member/candidate listing inside an org
3. resource listing inside an org
4. student portal assigned-resource lookup
5. Clerk webhook/callback invite lookup
```

We are not adding speculative indexes until production query patterns prove the need.

---

## 5. Agreed Invitation Email Strategy

### 5.1 We are using Clerk for invitation creation

Candidate onboarding will use Clerk invitations.

Current product assumption:

```text
same GrowQR invitation template
dynamic organization name
dynamic organization logo URL
multiple organizations under one GrowQR app
```

### 5.2 Branding model

Backend flow:

```text
admin belongs to organization
backend resolves organization_id
backend reads organizations.name and organizations.logo_url
backend sends those values in Clerk invitation metadata
shared Clerk template renders those values
```

This gives:

```text
one shared template
many organizations
dynamic metadata per invite
```

This is scalable because template complexity stays constant while organization count grows as data only.

### 5.3 Current production boundary

For now we are not building:

```text
one separate email template per organization
```

We are building:

```text
one common layout
organization-specific name/logo variables
```

That is sufficient for the current requirement.

---

## 6. Bulk Candidate Intake We Are Going To Build

Bulk candidate upload is the first major backend workflow we should implement.

### 6.1 Product-level flow

```text
organization admin uploads bulk CSV and resumes
-> backend authenticates admin
-> backend resolves organization
-> backend parses candidate records
-> backend validates and dedupes within organization
-> backend stores candidate/member rows
-> backend stores candidate profile rows
-> backend creates Clerk invitation
-> backend stores invitation result
```

### 6.2 Important practical rule

For production, resume extraction should not be the only source of truth for email.

Preferred model:

```text
CSV = source of truth for email
resume file = enrichment source for extracted details
```

Reason:

```text
email extraction from resumes is not reliable enough to be the only onboarding key
```

### 6.3 First implementation scope

Initial candidate intake should support:

```text
- one candidate row with email/full_name/phone
- optional resume file
- parsed resume JSON
- Clerk invitation creation
- invitation status persistence
```

Before true “bulk”, we should make the single-candidate pipeline stable.

---

## 7. Recommended Implementation Order

This is the order we should actually build in code.

### Phase 1: One-candidate processing pipeline

Build one candidate end-to-end:

```text
input candidate data
-> normalize email
-> parse resume if file exists
-> upsert organization_members candidate row
-> upsert candidate_profiles row
-> create Clerk invitation
-> store invitation result
```

This is the most important first delivery.

### Phase 2: Bulk upload API boundary

Create a backend endpoint like:

```text
POST /admin/candidates/bulk-upload
```

Responsibilities:

```text
- authenticate admin with Clerk JWT
- resolve org member
- check candidates.upload permission
- accept upload
- create ingest batch/job
- hand off processing
```

Do not run heavy parsing and invite blasting inside the request thread.

### Phase 3: Background worker

The actual heavy processing should run in a worker.

Worker responsibilities:

```text
- read uploaded rows/files
- parse candidate info
- normalize/validate emails
- dedupe within same organization
- write candidate rows
- write candidate profile rows
- create Clerk invites
- record failures
```

### Phase 4: Admin UI for upload

Once the backend pipeline is stable:

```text
- add upload UI
- add progress/status
- show sent/failed/invited rows
```

### Phase 5: Retry and reporting

Later:

```text
- retry failed invites
- batch-level reporting
- candidate status filtering
```

---

## 8. Candidate Onboarding And Identity Linkage

Candidate onboarding will work like this:

```text
admin uploads candidate
-> backend creates org-scoped candidate/member record
-> Clerk invitation is sent
-> candidate accepts invitation
-> Clerk account is linked to org candidate identity
-> candidate profile becomes active under that organization
```

Important identity rule:

```text
candidate identity is organization-scoped
not global candidate-only identity
```

This avoids accidental cross-organization profile leakage.

---

## 9. Qscore And QR-Based Candidate Access

We have already agreed on the next candidate-facing model:

```text
candidate accepts Clerk invite
-> candidate profile exists
-> Qscore is linked to candidate profile
-> QR token is linked to candidate profile
-> QR scan can resolve candidate and show public candidate info
```

### 9.1 Where Qscore lives

Qscore belongs in:

```text
candidate_profiles.qscore
```

### 9.2 Where QR fields live

Since one candidate in one organization gets one QR only, QR fields should live in:

```text
candidate_profiles
```

Recommended fields:

```text
qr_token
qr_status
qr_created_at
qr_expires_at
last_qr_scanned_at
```

Important rule:

```text
qr_token must be unique and random
it must not expose raw clerk_user_id
```

### 9.3 QR flow

```text
candidate profile becomes active
-> backend generates qr_token
-> QR image points to /qr/{qr_token}
-> scanner opens QR URL
-> backend resolves candidate_profiles by qr_token
-> backend returns allowed public candidate info, initially Qscore
```

---

## 10. Files And Modules We Should Build Next

We should keep the code split into reusable backend units.

Current module layout:

```text
backend/
  api/
    main.py
    routes/
      admin.py
      health.py
      resumes.py
      webhooks.py
  integrations/
    clerk_client.py
  services/
    auth_service.py
    batch_status_service.py
    clerk_invite_service.py
    clerk_webhook_service.py
    queue_service.py
    resume_parser.py
    resume_upload_contracts.py
    resume_upload_enqueue_service.py
    resume_upload_records.py
    resume_upload_worker_service.py
    storage_service.py

  workers/
    resume_upload_worker.py
```

### What each active module does

`auth_service.py`

```text
verify Clerk bearer tokens and admin access against organization_members
```

`batch_status_service.py`

```text
return upload batch status for frontend polling
```

`clerk_invite_service.py`

```text
build org-branded Clerk invitation payloads and call Clerk
```

`integrations/clerk_client.py`

```text
low-level Clerk invitation HTTP client and payload builder
```

`resume_parser.py`

```text
extract structured candidate data from resumes
```

`resume_upload_enqueue_service.py`

```text
create parse batch/items, store PDFs, and enqueue worker job
```

`resume_upload_contracts.py`

```text
typed API/queue/worker contracts for resume upload flow
```

`resume_upload_records.py`

```text
database and storage helpers for resume upload batches/items
```

`resume_upload_worker_service.py`

```text
parse queued resumes, write parsed data, and trigger invites
```

`storage_service.py`

```text
store original resume PDFs locally or in S3
```

---

## 11. What We Are Not Building First

We should explicitly defer these until the onboarding spine is stable:

```text
- full role management UI
- reports dashboard
- advanced analytics
- custom email provider flow
- complex resource/course UI
- multiple QR types per candidate
- heavy candidate/public profile features beyond Qscore
```

Reason:

```text
The first proof of system value is successful org-scoped candidate intake and onboarding.
```

---

## 12. Practical First Milestone

The first milestone should be:

```text
one admin
one organization
one candidate input
one Clerk invite
one stored invitation result
one candidate profile with parsed data
```

More concretely:

```text
1. hardcoded candidate data works
2. Clerk invite is sent successfully
3. invitation result is persisted
4. org branding variables are attached
5. candidate profile row shape is fixed
```

Once that is stable, bulk is just scaling the same flow across many candidates.

---

## 13. Final Implementation Position

What we are implementing now is:

```text
a production-oriented onboarding spine for GrowQR Admin Portal
```

That spine includes:

```text
- org-scoped identity
- org-scoped candidate data
- minimal but correct indexing
- Clerk invite onboarding
- dynamic org branding through one shared template
- candidate Qscore storage
- QR-linked candidate identity at profile level
- future-ready resource and assignment model
```

This is the correct foundation to build the rest of the portal on top of.

---

## 14. Production Persistence Workflow

The local SQL files remain as the concrete schema source, but production schema
application now runs through Alembic:

```text
alembic upgrade head
```

Reason:

```text
Alembic records which schema revisions have already run in Postgres, so RDS
staging and production databases can be upgraded repeatably without manually
tracking SQL files.
```

Original uploaded resumes are now written through `services/storage_service.py`.
The default local backend writes to `.local_storage`; production should set:

```text
STORAGE_BACKEND=s3
S3_BUCKET_NAME=<private resume bucket>
S3_REGION=<aws region>
S3_PREFIX=<environment/application prefix>
```

Persistence rule:

```text
S3/private object storage stores original PDF bytes.
Postgres stores resume_file_key, resume_file_name, parsed resume jsonb, and parse status.
```

The bulk resume path stores the original file first, then writes the generated
`resume_file_key` into `resume_parse_items`. When a candidate profile is created
from a parsed item, that same key is copied into `candidate_profiles` so the
structured profile remains linked to the original private resume object.

---

## 15. Async Upload Worker Workflow

Bulk resume upload is now split between the API and a worker.

API responsibility:

```text
authenticate org admin
validate PDF uploads
store original PDFs through the storage service
create resume_parse_batches with status pending
create resume_parse_items with status pending and resume_file_key
send one queue message for the batch
return queued response quickly
```

Worker responsibility:

```text
poll queue
load batch message
mark batch processing
download each PDF by resume_file_key
parse resumes concurrently, capped by RESUME_PARSE_ITEM_CONCURRENCY
update resume_parse_items with parsed_resume jsonb or failure error
send Clerk candidate invites from parsed items
upsert pending candidate_profiles with resume_file_key and parsed JSON
store candidate_profile_id in Clerk invitation metadata
mark batch completed or completed_with_errors
delete queue message after success
```

The worker keeps Postgres writes sequential on its active connection, but runs
the PDF download/OpenAI extraction work concurrently. The default local cap is:

```text
RESUME_PARSE_ITEM_CONCURRENCY=5
```

Pending candidates do not get synthetic Clerk IDs. `candidate_profiles.id` is
the local pending identity, `candidate_profiles.clerk_user_id` stays null until
Clerk creates the real `user_xxx` during invite acceptance, and invitations
link back to `candidate_profile_id`.

Clerk must call the backend webhook after invite acceptance:

```text
POST /webhooks/clerk
```

The webhook verifies `CLERK_WEBHOOK_SECRET`, handles `user.created` /
`user.updated`, reads `candidate_profile_id` from Clerk public metadata, creates
or updates the candidate `organization_members` row with the real Clerk
`user_xxx`, attaches that ID to `candidate_profiles.clerk_user_id`, and marks
matching invitations as accepted.

Local development uses a file-backed queue:

```text
QUEUE_BACKEND=local
LOCAL_QUEUE_ROOT=.local_queue
```

AWS production should use SQS:

```text
QUEUE_BACKEND=sqs
SQS_RESUME_UPLOAD_QUEUE_URL=<queue url>
SQS_REGION=<aws region>
```

Run the local worker with:

```text
python -m workers.resume_upload_worker
```

The same container image can run either the API command or the worker command in
AWS. The API and worker both use the same RDS Postgres, storage backend, Clerk,
and OpenAI configuration.

---

## 16. Container Runtime Workflow

The backend lives in `backend/`. It builds one Docker image that can run the API,
worker, migrations, or local seed command.

Build the image:

```text
docker build -t growqr-admin-api:local backend
```

Run the API command:

```text
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Run the worker command:

```text
python -m workers.resume_upload_worker
```

Run migrations:

```text
alembic upgrade head
```

Local Docker Compose provides:

```text
postgres
migrate
seed
api
worker
```

Start the local API stack:

```text
docker compose up api
```

Start the worker as well:

```text
docker compose up api worker
```

The Compose stack uses local storage and a local file-backed queue through named
volumes. AWS deployments should keep the same container image but configure:

```text
DATABASE_URL=<RDS Postgres URL>
STORAGE_BACKEND=s3
S3_BUCKET_NAME=<private bucket>
QUEUE_BACKEND=sqs
SQS_RESUME_UPLOAD_QUEUE_URL=<queue url>
```

Secrets must come from AWS Secrets Manager or the deployment platform, not from a
checked-in env file.

The browser frontend lives in `frontend/` and replaces the Streamlit upload UI
for the main admin intake workflow.

Run it locally:

```text
cd frontend
npm run dev
```

Then open:

```text
http://localhost:5173
```

The local frontend is configured for:

```text
API URL: http://127.0.0.1:8000
Organization slug: amity
Local Clerk user id: local_amity_admin
```
