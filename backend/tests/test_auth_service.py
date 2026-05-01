import pytest

from services.auth_service import (
    AuthError,
    bearer_token_from_authorization,
    require_org_admin,
    resolve_org_admin_membership,
)
from services.settings import AppSettings


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return FakeResult(self.rows)


def admin_row(org_id="11111111-1111-4111-8111-111111111111", slug="lpu"):
    return (
        org_id,
        "LPU",
        slug,
        "https://example.com/logo.png",
        "user_123",
        "admin@example.com",
        "Admin User",
        "admin",
        "org_admin",
        "active",
    )


def test_bearer_token_from_authorization_requires_bearer_scheme():
    assert bearer_token_from_authorization("Bearer abc123") == "abc123"

    with pytest.raises(AuthError):
        bearer_token_from_authorization("Basic abc123")


def test_resolve_org_admin_membership_returns_current_member():
    conn = FakeConn([admin_row()])

    member = resolve_org_admin_membership(conn, "user_123", "lpu")

    assert member.organization_slug == "lpu"
    assert member.clerk_user_id == "user_123"
    assert conn.calls[0][1] == ["user_123", "lpu"]


def test_resolve_org_admin_membership_requires_slug_for_multiple_orgs():
    conn = FakeConn([admin_row(slug="lpu"), admin_row(slug="amity")])

    with pytest.raises(AuthError, match="Multiple admin organizations"):
        resolve_org_admin_membership(conn, "user_123")


def test_require_org_admin_requires_bearer_token():
    with pytest.raises(AuthError, match="Bearer token is required"):
        require_org_admin(
            FakeConn([admin_row()]),
            authorization=None,
            settings=AppSettings(),
    )
