from services.clerk_webhook_service import (
    extract_primary_email,
    link_candidate_from_clerk_event,
)


class FakeResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, pending_member_rows=None, candidate_profile_row=None):
        self.calls = []
        self.pending_member_rows = pending_member_rows or []
        self.candidate_profile_row = candidate_profile_row

    def execute(self, query, params=None):
        self.calls.append((query, params))
        normalized = " ".join(str(query).lower().split())
        if "update organization_members" in normalized and "returning organization_id" in normalized:
            return FakeResult(rows=self.pending_member_rows)
        if "from candidate_profiles" in normalized:
            return FakeResult(self.candidate_profile_row)
        return FakeResult(None)


def user_created_event():
    return {
        "type": "user.created",
        "data": {
            "id": "user_123",
            "first_name": "Candidate",
            "last_name": "One",
            "primary_email_address_id": "idn_123",
            "email_addresses": [
                {"id": "idn_123", "email_address": "candidate@example.com"}
            ],
            "public_metadata": {
                "candidate_profile_id": "profile-123",
                "organization_id": "11111111-1111-4111-8111-111111111111",
                "candidate_email": "candidate@example.com",
            },
        },
    }


def test_extract_primary_email_uses_primary_email_address_id():
    assert extract_primary_email(user_created_event()["data"]) == "candidate@example.com"


def test_link_candidate_from_clerk_event_attaches_real_user_id():
    conn = FakeConn(
        candidate_profile_row=(
            "profile-123",
            "11111111-1111-4111-8111-111111111111",
            "candidate@example.com",
            "Candidate One",
        )
    )

    result = link_candidate_from_clerk_event(conn, user_created_event())

    assert result.linked is True
    assert result.candidate_profile_id == "profile-123"
    assert result.clerk_user_id == "user_123"

    joined_calls = "\n".join(call[0].lower() for call in conn.calls)
    assert "insert into organization_members" in joined_calls
    assert "update candidate_profiles" in joined_calls
    assert "update invitations" in joined_calls
    assert not any("local_candidate_" in str(call) for call in conn.calls)

    member_call = next(call for call in conn.calls if "insert into organization_members" in call[0].lower())
    assert member_call[1][1] == "user_123"

    profile_call = next(call for call in conn.calls if "update candidate_profiles" in call[0].lower())
    assert profile_call[1][0] == "user_123"


def test_link_candidate_from_clerk_event_links_pending_admin_member_by_email():
    conn = FakeConn(
        pending_member_rows=[
            (
                "22222222-2222-4222-8222-222222222222",
                "admin@example.com",
                "admin",
                "org_admin",
            )
        ]
    )
    event = {
        "type": "user.created",
        "data": {
            "id": "user_admin_123",
            "first_name": "Admin",
            "last_name": "User",
            "primary_email_address_id": "idn_admin",
            "email_addresses": [
                {"id": "idn_admin", "email_address": "admin@example.com"}
            ],
            "public_metadata": {},
        },
    }

    result = link_candidate_from_clerk_event(conn, event)

    assert result.linked is True
    assert result.reason == "member_linked"
    assert result.clerk_user_id == "user_admin_123"
    assert result.linked_members[0]["member_type"] == "admin"
    assert result.linked_members[0]["role_key"] == "org_admin"

    member_call = next(call for call in conn.calls if "update organization_members" in call[0].lower())
    assert member_call[1] == ("user_admin_123", "Admin User", "admin@example.com")

    invitation_call = next(call for call in conn.calls if "update invitations" in call[0].lower())
    assert invitation_call[1] == (
        "user_admin_123",
        "22222222-2222-4222-8222-222222222222",
        "admin@example.com",
        "admin",
        "org_admin",
    )
