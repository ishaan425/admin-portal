from services.auth_service import CurrentOrgMember
from services.clerk_invite_service import ClerkInviteConfig, process_parsed_resume_item


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        normalized = " ".join(str(query).lower().split())
        if "select id, status from invitations" in normalized:
            return FakeResult(None)
        if "insert into candidate_profiles" in normalized:
            return FakeResult(("profile-123",))
        if "insert into invitations" in normalized:
            return FakeResult(("invitation-123",))
        return FakeResult(None)


def current_member():
    return CurrentOrgMember(
        organization_id="org-123",
        organization_name="Amity",
        organization_slug="amity",
        organization_logo_url="https://example.com/logo.png",
        clerk_user_id="admin-123",
        email="admin@example.com",
        full_name="Admin",
        member_type="admin",
        role_key="org_admin",
        status="active",
    )


def parsed_item():
    return {
        "id": "item-123",
        "original_file_name": "Resume.pdf",
        "resume_file_key": "resume-key",
        "parsed_resume": {
            "personal_info": {
                "email": "candidate@example.com",
                "full_name": "Candidate One",
                "phone": "+10000000000",
            }
        },
    }


def test_candidate_invite_uses_pending_profile_before_real_clerk_user(monkeypatch):
    clerk_payloads = []

    def fake_create_clerk_invitation(secret_key, payload):
        clerk_payloads.append(payload)
        return 200, {"id": "clerk-invitation-123"}, {}

    monkeypatch.setattr(
        "services.clerk_invite_service.create_clerk_invitation",
        fake_create_clerk_invitation,
    )
    conn = FakeConn()

    result = process_parsed_resume_item(
        conn=conn,
        current_member=current_member(),
        item=parsed_item(),
        config=ClerkInviteConfig(secret_key="secret", redirect_url="https://app.growqr.ai/login"),
        seen_emails=set(),
        dry_run=False,
        resend=True,
    )

    assert result["status"] == "sent"
    assert result["candidate_profile_id"] == "profile-123"
    assert not any("insert into organization_members" in call[0].lower() for call in conn.calls)
    assert not any("local_candidate_" in str(call) for call in conn.calls)

    invitation_call = next(call for call in conn.calls if "insert into invitations" in call[0].lower())
    assert invitation_call[1][1] == "profile-123"
    assert invitation_call[1][2] is None

    assert clerk_payloads[0]["public_metadata"]["candidate_profile_id"] == "profile-123"
    assert "local_candidate_" not in str(clerk_payloads[0])


def test_candidate_invite_dry_run_does_not_create_pending_profile(monkeypatch):
    conn = FakeConn()

    result = process_parsed_resume_item(
        conn=conn,
        current_member=current_member(),
        item=parsed_item(),
        config=ClerkInviteConfig(secret_key="secret", redirect_url="https://app.growqr.ai/login"),
        seen_emails=set(),
        dry_run=True,
        resend=True,
    )

    assert result["status"] == "dry_run"
    assert "candidate_profile_id" not in result["payload"]["public_metadata"]
    assert not any("insert into candidate_profiles" in call[0].lower() for call in conn.calls)
    assert not any("insert into invitations" in call[0].lower() for call in conn.calls)
