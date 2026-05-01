from datetime import datetime, timezone

import pytest

from schemas.job_schema import JobOpeningCreate, JobOpeningUpdate
from services.auth_service import CurrentOrgMember
from services.job_opening_service import (
    JobOpeningError,
    create_job_opening,
    publish_job_opening,
    update_job_opening,
)


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [self.row] if self.row else []


class FakeConn:
    def __init__(self):
        self.calls = []
        self.job = {
            "id": "job-123",
            "organization_id": "org-123",
            "created_by": "user-123",
            "title": "Backend Developer",
            "status": "draft",
            "metadata": {
                "company_name": "Acme",
                "location": "Bengaluru",
                "work_mode": "hybrid",
                "employment_type": "full_time",
                "description": "Build backend systems",
                "requirements": ["Python"],
                "skills": ["Python"],
                "open_positions": 2,
            },
            "created_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        }

    def execute(self, query, params=None):
        self.calls.append((query, params))
        normalized = " ".join(str(query).lower().split())
        if "select org_type from organizations" in normalized:
            return FakeResult(("enterprise",))
        if "select rp.action_mask" in normalized:
            return FakeResult((255,))
        if "insert into org_resources" in normalized:
            return FakeResult(self.row())
        if "select id, organization_id, created_by_clerk_user_id" in normalized:
            return FakeResult(self.row())
        if "update org_resources set title" in normalized:
            title = params[0]
            metadata = params[1].obj
            if title:
                self.job["title"] = title
            self.job["metadata"] = metadata
            return FakeResult(self.row())
        if "update org_resources set status" in normalized:
            self.job["status"] = params[0]
            return FakeResult(self.row())
        return FakeResult(None)

    def row(self):
        return (
            self.job["id"],
            self.job["organization_id"],
            self.job["created_by"],
            self.job["title"],
            self.job["status"],
            self.job["metadata"],
            self.job["created_at"],
            self.job["updated_at"],
        )


def current_member():
    return CurrentOrgMember(
        organization_id="org-123",
        organization_name="Acme",
        organization_slug="acme",
        organization_logo_url="",
        clerk_user_id="user-123",
        email="hr@example.com",
        full_name="HR User",
        member_type="enterprise_hr",
        role_key="enterprise_hr",
        status="active",
    )


def create_payload():
    return JobOpeningCreate(
        title="Backend Developer",
        company_name="Acme",
        location="Bengaluru",
        work_mode="hybrid",
        employment_type="full_time",
        description="Build backend systems",
        requirements=["Python"],
        skills=["Python"],
        open_positions=2,
    )


def test_create_job_opening_writes_draft_job_resource():
    conn = FakeConn()

    result = create_job_opening(conn, current_member(), create_payload())

    assert result["status"] == "draft"
    assert result["metadata"]["work_mode"] == "hybrid"
    insert_call = next(call for call in conn.calls if "insert into org_resources" in call[0].lower())
    assert insert_call[1][0] == "org-123"
    assert insert_call[1][1] == "user-123"
    assert insert_call[1][2] == "Backend Developer"


def test_update_job_opening_merges_metadata():
    conn = FakeConn()

    result = update_job_opening(
        conn,
        current_member(),
        "job-123",
        JobOpeningUpdate(skills=["Python", "Postgres"]),
    )

    assert result["metadata"]["skills"] == ["Python", "Postgres"]
    assert result["metadata"]["location"] == "Bengaluru"


def test_update_job_opening_rejects_invalid_merged_range():
    conn = FakeConn()
    conn.job["metadata"]["salary_min"] = 1000000

    with pytest.raises(JobOpeningError, match="salary_min"):
        update_job_opening(
            conn,
            current_member(),
            "job-123",
            JobOpeningUpdate(salary_max=500000),
        )


def test_publish_job_opening_requires_complete_metadata():
    conn = FakeConn()
    conn.job["metadata"]["skills"] = []

    with pytest.raises(JobOpeningError, match="Missing required fields"):
        publish_job_opening(conn, current_member(), "job-123")


def test_publish_job_opening_sets_status():
    conn = FakeConn()

    result = publish_job_opening(conn, current_member(), "job-123")

    assert result["status"] == "published"
