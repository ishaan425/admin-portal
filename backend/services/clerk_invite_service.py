"""Clerk invitation pipeline for parsed candidate resumes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from clerk_invitation_client import (
    CandidateInvite,
    build_invitation_payload,
    create_clerk_invitation,
    is_valid_email,
    normalize_email,
)
from services.auth_service import CurrentOrgMember
from services.settings import get_settings


DEFAULT_REDIRECT_URL = "https://app.growqr.ai/login"


class ClerkInvitePipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClerkInviteConfig:
    secret_key: str
    redirect_url: str = DEFAULT_REDIRECT_URL
    notify: bool = True


def clerk_invite_config_from_env() -> ClerkInviteConfig:
    settings = get_settings()
    secret_key = settings.clerk_secret_key.strip()
    if not secret_key:
        raise ClerkInvitePipelineError("CLERK_SECRET_KEY is required. Add it to .env.")

    return ClerkInviteConfig(
        secret_key=secret_key,
        redirect_url=settings.clerk_invite_redirect_url.strip() or DEFAULT_REDIRECT_URL,
        notify=settings.clerk_invite_notify,
    )


def invite_candidates_from_resume_batch(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    batch_id: str,
    config: ClerkInviteConfig,
    dry_run: bool = False,
    resend: bool = False,
) -> dict[str, Any]:
    items = get_parsed_resume_items(conn, current_member.organization_id, batch_id)
    results: list[dict[str, Any]] = []
    sent_count = 0
    failed_count = 0
    skipped_count = 0
    seen_emails: set[str] = set()

    for item in items:
        result = process_parsed_resume_item(
            conn=conn,
            current_member=current_member,
            item=item,
            config=config,
            seen_emails=seen_emails,
            dry_run=dry_run,
            resend=resend,
        )
        results.append(result)
        if result["status"] == "sent":
            sent_count += 1
        elif result["status"] in {"skipped", "dry_run"}:
            skipped_count += 1
        else:
            failed_count += 1

    return {
        "batch_id": batch_id,
        "organization": {
            "id": current_member.organization_id,
            "name": current_member.organization_name,
            "slug": current_member.organization_slug,
            "logo_url": current_member.organization_logo_url,
        },
        "dry_run": dry_run,
        "resend": resend,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "items": results,
    }


def process_parsed_resume_item(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    item: dict[str, Any],
    config: ClerkInviteConfig,
    seen_emails: set[str],
    dry_run: bool,
    resend: bool,
) -> dict[str, Any]:
    parsed_resume = item["parsed_resume"] or {}
    personal_info = parsed_resume.get("personal_info") or {}
    email = normalize_email(personal_info.get("email") or "")
    full_name = str(personal_info.get("full_name") or "").strip()
    phone = str(personal_info.get("phone") or "").strip()

    if not email or not is_valid_email(email):
        return fail_without_invite(
            conn,
            current_member=current_member,
            item=item,
            email=email,
            reason="Missing or invalid extracted email.",
            dry_run=dry_run,
        )
    if email in seen_emails:
        return fail_without_invite(
            conn,
            current_member=current_member,
            item=item,
            email=email,
            reason="Duplicate email in parsed batch.",
            dry_run=dry_run,
        )
    seen_emails.add(email)

    existing_invitation = find_existing_invitation(conn, current_member.organization_id, email)
    if existing_invitation and not resend:
        return {
            "resume_parse_item_id": item["id"],
            "file_name": item["original_file_name"],
            "email": email,
            "status": "skipped",
            "reason": f"Invitation already exists with status {existing_invitation['status']}.",
            "invitation_id": existing_invitation["id"],
        }

    candidate_profile_id = None
    if not dry_run:
        candidate_profile_id = upsert_candidate_profile(
            conn,
            organization_id=current_member.organization_id,
            email=email,
            full_name=full_name,
            file_key=item.get("resume_file_key"),
            file_name=item["original_file_name"],
            parsed_resume=parsed_resume,
        )
    invitation_metadata = {
        "source": "growqr_admin_portal_bulk_resume_upload",
        "organization_id": current_member.organization_id,
        "organization_slug": current_member.organization_slug,
        "resume_parse_item_id": item["id"],
        "candidate_email": email,
    }
    if candidate_profile_id:
        invitation_metadata["candidate_profile_id"] = candidate_profile_id

    payload = build_invitation_payload(
        CandidateInvite(email=email, full_name=full_name, phone=phone),
        redirect_url=config.redirect_url,
        notify=config.notify,
        tenant_name=current_member.organization_name,
        tenant_logo_url=current_member.organization_logo_url,
        public_metadata=invitation_metadata,
    )

    if dry_run:
        return {
            "resume_parse_item_id": item["id"],
            "file_name": item["original_file_name"],
            "email": email,
            "status": "dry_run",
            "payload": payload,
        }

    status_code, response_body, _headers = create_clerk_invitation(config.secret_key, payload)
    clerk_invitation_id = extract_clerk_invitation_id(response_body)
    is_success = 200 <= status_code < 300
    invitation_id = create_invitation_row(
        conn,
        current_member=current_member,
        email=email,
        candidate_profile_id=candidate_profile_id,
        target_clerk_user_id=None,
        clerk_invitation_id=clerk_invitation_id,
        status="sent" if is_success else "failed",
        error_message=None if is_success else summarize_error(response_body),
    )

    return {
        "resume_parse_item_id": item["id"],
        "file_name": item["original_file_name"],
        "email": email,
        "status": "sent" if is_success else "failed",
        "http_status": status_code,
        "candidate_profile_id": candidate_profile_id,
        "invitation_id": invitation_id,
        "clerk_invitation_id": clerk_invitation_id,
        "error_message": None if is_success else summarize_error(response_body),
    }


def fail_without_invite(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    item: dict[str, Any],
    email: str,
    reason: str,
    dry_run: bool,
) -> dict[str, Any]:
    if not dry_run:
        invitation_id = create_invitation_row(
            conn,
            current_member=current_member,
            email=email or "unknown@example.invalid",
            candidate_profile_id=None,
            target_clerk_user_id=None,
            clerk_invitation_id=None,
            status="failed",
            error_message=reason,
        )
    else:
        invitation_id = None

    return {
        "resume_parse_item_id": item["id"],
        "file_name": item["original_file_name"],
        "email": email,
        "status": "failed",
        "invitation_id": invitation_id,
        "error_message": reason,
    }


def get_parsed_resume_items(
    conn: psycopg.Connection,
    organization_id: str,
    batch_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select id, original_file_name, resume_file_key, parsed_resume
        from resume_parse_items
        where organization_id = %s
          and batch_id = %s
          and parse_status = 'parsed'
        order by created_at asc
        """,
        (organization_id, batch_id),
    ).fetchall()
    return [
        {
            "id": str(row[0]),
            "original_file_name": row[1],
            "resume_file_key": row[2],
            "parsed_resume": row[3],
        }
        for row in rows
    ]


def find_existing_invitation(
    conn: psycopg.Connection,
    organization_id: str,
    email: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        select id, status
        from invitations
        where organization_id = %s
          and target_email = %s
          and target_member_type = 'candidate'
          and status in ('pending', 'sent', 'accepted')
        order by created_at desc
        limit 1
        """,
        (organization_id, email),
    ).fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "status": row[1]}


def upsert_candidate_profile(
    conn: psycopg.Connection,
    organization_id: str,
    email: str,
    full_name: str,
    file_key: str | None,
    file_name: str,
    parsed_resume: dict[str, Any],
) -> str:
    row = conn.execute(
        """
        insert into candidate_profiles (
            organization_id,
            email,
            full_name,
            resume_file_key,
            resume_file_name,
            resume_data,
            resume_parse_status,
            resume_uploaded_at,
            updated_at
        )
        values (%s, %s, %s, %s, %s, %s, 'parsed', %s, now())
        on conflict (organization_id, email) do update
        set resume_file_key = excluded.resume_file_key,
            resume_file_name = excluded.resume_file_name,
            resume_data = excluded.resume_data,
            resume_parse_status = excluded.resume_parse_status,
            resume_uploaded_at = excluded.resume_uploaded_at,
            updated_at = now()
        returning id
        """,
        (
            organization_id,
            email,
            full_name,
            file_key,
            file_name,
            Jsonb(parsed_resume),
            datetime.now(timezone.utc),
        ),
    ).fetchone()
    return str(row[0])


def create_invitation_row(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    email: str,
    candidate_profile_id: str | None,
    target_clerk_user_id: str | None,
    clerk_invitation_id: str | None,
    status: str,
    error_message: str | None,
) -> str:
    row = conn.execute(
        """
        insert into invitations (
            organization_id,
            candidate_profile_id,
            target_clerk_user_id,
            target_email,
            target_member_type,
            target_role_key,
            invited_by_clerk_user_id,
            clerk_invitation_id,
            status,
            error_message,
            sent_at
        )
        values (%s, %s, %s, %s, 'candidate', 'candidate', %s, %s, %s, %s, %s)
        returning id
        """,
        (
            current_member.organization_id,
            candidate_profile_id,
            target_clerk_user_id,
            email,
            current_member.clerk_user_id,
            clerk_invitation_id,
            status,
            error_message,
            datetime.now(timezone.utc) if status == "sent" else None,
        ),
    ).fetchone()
    return str(row[0])


def extract_clerk_invitation_id(response_body: Any) -> str | None:
    if isinstance(response_body, dict):
        value = response_body.get("id")
        return str(value) if value else None
    return None


def summarize_error(response_body: Any) -> str:
    if isinstance(response_body, dict):
        if response_body.get("message"):
            return str(response_body["message"])
        if response_body.get("errors"):
            return str(response_body["errors"])[:1000]
    return str(response_body)[:1000]
