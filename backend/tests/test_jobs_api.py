from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.routes import jobs
from api.main import create_app
from services.settings import AppSettings


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def transaction(self):
        return self


def fake_member():
    return type(
        "Member",
        (),
        {
            "organization_id": "org-123",
            "organization_name": "Acme",
            "organization_slug": "acme",
            "organization_logo_url": "",
            "clerk_user_id": "user-123",
            "email": "hr@example.com",
            "full_name": "HR User",
            "member_type": "enterprise_hr",
            "role_key": "enterprise_hr",
            "status": "active",
        },
    )()


def job_response(status="draft"):
    timestamp = datetime(2026, 5, 1, tzinfo=timezone.utc).isoformat()
    return {
        "id": "job-123",
        "organization_id": "org-123",
        "created_by_clerk_user_id": "user-123",
        "title": "Backend Developer",
        "status": status,
        "metadata": {
            "location": "Bengaluru",
            "work_mode": "hybrid",
            "employment_type": "full_time",
            "skills": ["Python"],
            "requirements": ["Python"],
            "description": "Build backend systems",
            "open_positions": 2,
        },
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def test_create_job_endpoint_returns_created_job(monkeypatch):
    app = create_app(AppSettings())
    client = TestClient(app)

    monkeypatch.setattr(jobs, "connect", lambda: FakeConn())
    monkeypatch.setattr(jobs, "require_active_org_member", lambda *args, **kwargs: fake_member())
    monkeypatch.setattr(jobs, "create_job_opening", lambda conn, current_member, payload: job_response())

    response = client.post(
        "/admin/jobs",
        headers={"Authorization": "Bearer test-token", "X-Organization-Slug": "acme"},
        json={
            "title": "Backend Developer",
            "location": "Bengaluru",
            "work_mode": "hybrid",
            "employment_type": "full_time",
            "skills": ["Python"],
            "requirements": ["Python"],
            "description": "Build backend systems",
            "open_positions": 2,
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == "job-123"
    assert response.json()["status"] == "draft"


def test_publish_job_endpoint_returns_published_job(monkeypatch):
    app = create_app(AppSettings())
    client = TestClient(app)

    monkeypatch.setattr(jobs, "connect", lambda: FakeConn())
    monkeypatch.setattr(jobs, "require_active_org_member", lambda *args, **kwargs: fake_member())
    monkeypatch.setattr(jobs, "publish_job_opening", lambda conn, current_member, job_id: job_response("published"))

    response = client.post(
        "/admin/jobs/job-123/publish",
        headers={"Authorization": "Bearer test-token", "X-Organization-Slug": "acme"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "published"
