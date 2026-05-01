# Admin And Student Portal Onboarding Flow

The GrowQR system has two portals that share the same identity and database layer.

## Portals

Admin Portal:
- Admins add students/candidates to their organization.
- Admins assign courses, quizzes, roleplays, interviews, jobs, and other resources.
- Admins can bulk upload candidate CVs.

Student Portal:
- Students log in with Clerk.
- Students see their profile, Q-score, resume data, courses, opportunities, and org-linked content.
- Students should not access admin functionality.

## Shared Ground

Both portals must use the same Clerk project/environment.

Clerk answers:

```text
Who is this person? -> user_xxx
```

GrowQR Postgres answers:

```text
Which organization does this user belong to?
Is this user an admin or candidate?
Which profile, courses, quizzes, roleplays, and interviews can this user access?
```

## Candidate Invite Flow

```text
Admin uploads CVs in Admin Portal
-> Backend creates pending candidate_profiles rows
-> Backend sends Clerk invites with candidate_profile_id metadata
-> Candidate clicks invite email
-> Candidate lands on Student Portal login
-> Candidate signs up/logs in with Clerk
-> Clerk creates real user_xxx
-> Clerk sends user.created webhook to Admin backend
-> Backend links user_xxx to candidate_profiles.clerk_user_id
-> Backend creates/updates organization_members row for that org
-> Student Portal can now load the candidate profile and org content
```

## Important Rules

- Do not create fake Clerk IDs for pending candidates.
- Pending candidates use `candidate_profiles.id`.
- Real Clerk IDs are stored only after Clerk creates the user.
- Student Portal and Admin Backend must use the same Clerk app.
- The invite redirect should point to Student Portal:

```env
CLERK_INVITE_REDIRECT_URL=https://app.growqr.ai/login
```

## Required Integration

Student Portal should send the Clerk JWT to backend APIs.

Backend should read:

```text
JWT sub = user_xxx
```

Then resolve:

```text
organization_members
candidate_profiles
resource_assignments
```

This keeps authentication in Clerk and authorization/business access in GrowQR Postgres.
