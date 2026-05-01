import pytest

from services.auth_service import CurrentOrgMember
from services.permission_service import PermissionError, require_enterprise_organization, require_feature_permission


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return FakeResult(self.rows.pop(0) if self.rows else None)


def current_member(role_key="enterprise_hr"):
    return CurrentOrgMember(
        organization_id="org-123",
        organization_name="Acme",
        organization_slug="acme",
        organization_logo_url="",
        clerk_user_id="user-123",
        email="hr@example.com",
        full_name="HR User",
        member_type="enterprise_hr",
        role_key=role_key,
        status="active",
    )


def test_require_feature_permission_accepts_action_mask():
    conn = FakeConn([(1 | 2 | 4 | 32,)])

    require_feature_permission(conn, current_member(), "jobs", "publish")

    assert conn.calls[0][1] == ("org-123", "enterprise_hr", "jobs")


def test_require_feature_permission_rejects_missing_action():
    conn = FakeConn([(1 | 2,)])

    with pytest.raises(PermissionError, match="jobs.publish"):
        require_feature_permission(conn, current_member(), "jobs", "publish")


def test_require_enterprise_organization_rejects_university():
    conn = FakeConn([("university",)])

    with pytest.raises(PermissionError, match="Only Enterprise"):
        require_enterprise_organization(conn, "org-123")
