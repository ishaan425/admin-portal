from fastapi.testclient import TestClient

from api import main
from api.main import create_app
from services.settings import AppSettings


class FakeResult:
    def fetchone(self):
        return (1,)


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def transaction(self):
        return self

    def execute(self, query):
        return FakeResult()


def fake_member():
    return type(
        "Member",
        (),
        {
            "organization_id": "org-123",
            "organization_name": "Amity",
            "organization_slug": "amity",
            "organization_logo_url": "https://example.com/logo.png",
            "clerk_user_id": "user_123",
            "email": "admin@example.com",
            "full_name": "Admin User",
            "member_type": "admin",
            "role_key": "org_admin",
            "status": "active",
        },
    )()


def test_health_endpoint():
    app = create_app(AppSettings())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_endpoint_checks_database(monkeypatch):
    monkeypatch.setattr(main, "connect", lambda: FakeConn())
    app = create_app(AppSettings())
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_request_size_limit_returns_413():
    app = create_app(AppSettings(api_max_request_body_bytes=1))
    client = TestClient(app)

    response = client.post(
        "/admin/resumes/bulk-upload",
        files={"files": ("resume.pdf", b"abc", "application/pdf")},
    )

    assert response.status_code == 413


def test_admin_me_returns_current_admin(monkeypatch):
    app = create_app(AppSettings(auth_allow_local_headers=True))
    client = TestClient(app)

    monkeypatch.setattr(main, "connect", lambda: FakeConn())
    monkeypatch.setattr(main, "require_org_admin", lambda *args, **kwargs: fake_member())

    response = client.get(
        "/admin/me",
        headers={
            "X-Local-Clerk-User-Id": "local_amity_admin",
            "X-Organization-Slug": "amity",
        },
    )

    assert response.status_code == 200
    assert response.json()["organization"]["slug"] == "amity"
    assert response.json()["admin"]["role_key"] == "org_admin"


def test_batch_status_endpoint_returns_batch(monkeypatch):
    app = create_app(AppSettings(auth_allow_local_headers=True))
    client = TestClient(app)

    monkeypatch.setattr(main, "connect", lambda: FakeConn())
    monkeypatch.setattr(
        main,
        "require_org_admin",
        lambda *args, **kwargs: fake_member(),
    )
    monkeypatch.setattr(
        main,
        "get_resume_upload_batch_status",
        lambda conn, organization_id, batch_id: {
            "batch_id": batch_id,
            "status": "completed",
            "organization": {"id": organization_id},
            "items": [],
        },
    )

    response = client.get(
        "/admin/resumes/batches/batch-123",
        headers={"X-Local-Clerk-User-Id": "local_amity_admin"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_clerk_webhook_endpoint_links_candidate(monkeypatch):
    app = create_app(AppSettings(clerk_webhook_secret="whsec_test"))
    client = TestClient(app)

    monkeypatch.setattr(main, "connect", lambda: FakeConn())
    monkeypatch.setattr(
        main,
        "verify_clerk_webhook",
        lambda payload, headers, secret: {"type": "user.created"},
    )
    monkeypatch.setattr(
        main,
        "link_candidate_from_clerk_event",
        lambda conn, event: type(
            "Result",
            (),
            {
                "linked": True,
                "reason": "linked",
                "candidate_profile_id": "profile-123",
            },
        )(),
    )

    response = client.post("/webhooks/clerk", content=b"{}")

    assert response.status_code == 200
    assert response.json()["linked"] is True
    assert response.json()["candidate_profile_id"] == "profile-123"
