"""Clerk webhook handling for linking accepted invites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import psycopg
from svix.webhooks import Webhook, WebhookVerificationError


class ClerkWebhookError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateLinkResult:
    linked: bool
    reason: str
    candidate_profile_id: str | None = None
    organization_id: str | None = None
    clerk_user_id: str | None = None
    linked_members: tuple[dict[str, str], ...] = ()


def verify_clerk_webhook(
    payload: bytes,
    headers: Mapping[str, str],
    webhook_secret: str,
) -> dict[str, Any]:
    if not webhook_secret.strip():
        raise ClerkWebhookError("CLERK_WEBHOOK_SECRET is required for Clerk webhooks.")

    svix_headers = {
        "svix-id": headers.get("svix-id", ""),
        "svix-timestamp": headers.get("svix-timestamp", ""),
        "svix-signature": headers.get("svix-signature", ""),
    }
    try:
        event = Webhook(webhook_secret).verify(payload, svix_headers)
    except WebhookVerificationError as exc:
        raise ClerkWebhookError("Invalid Clerk webhook signature.") from exc
    if not isinstance(event, dict):
        raise ClerkWebhookError("Invalid Clerk webhook payload.")
    return event


def link_candidate_from_clerk_event(
    conn: psycopg.Connection,
    event: dict[str, Any],
) -> CandidateLinkResult:
    event_type = str(event.get("type") or "")
    if event_type not in {"user.created", "user.updated"}:
        return CandidateLinkResult(linked=False, reason="ignored_event_type")

    data = event.get("data") or {}
    clerk_user_id = str(data.get("id") or "").strip()
    if not clerk_user_id:
        return CandidateLinkResult(linked=False, reason="missing_clerk_user_id")

    public_metadata = data.get("public_metadata") or {}
    candidate_profile_id = str(public_metadata.get("candidate_profile_id") or "").strip()
    organization_id = str(public_metadata.get("organization_id") or "").strip()
    email = normalize_email(
        public_metadata.get("candidate_email")
        or extract_primary_email(data)
    )
    full_name = extract_full_name(data, public_metadata)

    linked_members = link_pending_organization_members(
        conn,
        clerk_user_id=clerk_user_id,
        email=email,
        full_name=full_name,
    )

    profile = find_pending_candidate_profile(
        conn,
        candidate_profile_id=candidate_profile_id or None,
        organization_id=organization_id or None,
        email=email or None,
    )
    if not profile:
        if linked_members:
            return CandidateLinkResult(
                linked=True,
                reason="member_linked",
                organization_id=linked_members[0]["organization_id"],
                clerk_user_id=clerk_user_id,
                linked_members=tuple(linked_members),
            )
        return CandidateLinkResult(
            linked=False,
            reason="pending_member_or_candidate_profile_not_found",
            clerk_user_id=clerk_user_id,
        )

    profile_id = profile["id"]
    profile_org_id = profile["organization_id"]
    profile_email = email or profile["email"]
    profile_full_name = full_name or profile["full_name"] or ""

    upsert_candidate_member(
        conn,
        organization_id=profile_org_id,
        clerk_user_id=clerk_user_id,
        email=profile_email,
        full_name=profile_full_name,
    )
    attach_clerk_user_to_candidate_profile(
        conn,
        candidate_profile_id=profile_id,
        clerk_user_id=clerk_user_id,
        full_name=profile_full_name,
    )
    mark_candidate_invitation_accepted(
        conn,
        organization_id=profile_org_id,
        candidate_profile_id=profile_id,
        email=profile_email,
        clerk_user_id=clerk_user_id,
    )

    return CandidateLinkResult(
        linked=True,
        reason="linked",
        candidate_profile_id=profile_id,
        organization_id=profile_org_id,
        clerk_user_id=clerk_user_id,
        linked_members=tuple(linked_members),
    )


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def extract_primary_email(data: dict[str, Any]) -> str:
    primary_email_id = data.get("primary_email_address_id")
    email_addresses = data.get("email_addresses") or []
    for email_address in email_addresses:
        if email_address.get("id") == primary_email_id:
            return str(email_address.get("email_address") or "")
    if email_addresses:
        return str(email_addresses[0].get("email_address") or "")
    return ""


def extract_full_name(data: dict[str, Any], public_metadata: dict[str, Any]) -> str:
    metadata_name = str(public_metadata.get("candidate_full_name") or "").strip()
    if metadata_name:
        return metadata_name

    first_name = str(data.get("first_name") or "").strip()
    last_name = str(data.get("last_name") or "").strip()
    return " ".join(part for part in [first_name, last_name] if part).strip()


def find_pending_candidate_profile(
    conn: psycopg.Connection,
    candidate_profile_id: str | None,
    organization_id: str | None,
    email: str | None,
) -> dict[str, str] | None:
    if candidate_profile_id:
        row = conn.execute(
            """
            select id, organization_id, email, coalesce(full_name, '')
            from candidate_profiles
            where id = %s
              and (%s::uuid is null or organization_id = %s::uuid)
            """,
            (candidate_profile_id, organization_id, organization_id),
        ).fetchone()
    elif organization_id and email:
        row = conn.execute(
            """
            select id, organization_id, email, coalesce(full_name, '')
            from candidate_profiles
            where organization_id = %s
              and email = %s
            """,
            (organization_id, email),
        ).fetchone()
    elif email:
        row = conn.execute(
            """
            select id, organization_id, email, coalesce(full_name, '')
            from candidate_profiles
            where email = %s
            order by updated_at desc
            limit 1
            """,
            (email,),
        ).fetchone()
    else:
        row = None

    if not row:
        return None
    return {
        "id": str(row[0]),
        "organization_id": str(row[1]),
        "email": row[2],
        "full_name": row[3],
    }


def link_pending_organization_members(
    conn: psycopg.Connection,
    clerk_user_id: str,
    email: str,
    full_name: str,
) -> list[dict[str, str]]:
    if not email:
        return []

    rows = conn.execute(
        """
        update organization_members
        set clerk_user_id = %s,
            full_name = coalesce(nullif(%s, ''), full_name),
            status = 'active',
            updated_at = now()
        where email = %s
          and clerk_user_id is null
          and status = 'invited'
        returning organization_id, email, member_type, role_key
        """,
        (clerk_user_id, full_name, email),
    ).fetchall()

    linked_members = [
        {
            "organization_id": str(row[0]),
            "email": row[1],
            "member_type": row[2],
            "role_key": row[3],
        }
        for row in rows
    ]
    for member in linked_members:
        mark_member_invitation_accepted(
            conn,
            organization_id=member["organization_id"],
            email=member["email"],
            member_type=member["member_type"],
            role_key=member["role_key"],
            clerk_user_id=clerk_user_id,
        )
    return linked_members


def mark_member_invitation_accepted(
    conn: psycopg.Connection,
    organization_id: str,
    email: str,
    member_type: str,
    role_key: str,
    clerk_user_id: str,
) -> None:
    conn.execute(
        """
        update invitations
        set target_clerk_user_id = %s,
            status = 'accepted',
            accepted_at = coalesce(accepted_at, now())
        where organization_id = %s
          and target_email = %s
          and target_member_type = %s
          and target_role_key = %s
          and status in ('pending', 'sent')
        """,
        (clerk_user_id, organization_id, email, member_type, role_key),
    )


def upsert_candidate_member(
    conn: psycopg.Connection,
    organization_id: str,
    clerk_user_id: str,
    email: str,
    full_name: str,
) -> None:
    conn.execute(
        """
        insert into organization_members (
            organization_id,
            clerk_user_id,
            email,
            full_name,
            member_type,
            role_key,
            status
        )
        values (%s, %s, %s, %s, 'candidate', 'candidate', 'active')
        on conflict (organization_id, email) do update
        set clerk_user_id = excluded.clerk_user_id,
            full_name = excluded.full_name,
            member_type = excluded.member_type,
            role_key = excluded.role_key,
            status = 'active',
            updated_at = now()
        """,
        (organization_id, clerk_user_id, email, full_name),
    )


def attach_clerk_user_to_candidate_profile(
    conn: psycopg.Connection,
    candidate_profile_id: str,
    clerk_user_id: str,
    full_name: str,
) -> None:
    conn.execute(
        """
        update candidate_profiles
        set clerk_user_id = %s,
            full_name = coalesce(nullif(%s, ''), full_name),
            updated_at = now()
        where id = %s
        """,
        (clerk_user_id, full_name, candidate_profile_id),
    )


def mark_candidate_invitation_accepted(
    conn: psycopg.Connection,
    organization_id: str,
    candidate_profile_id: str,
    email: str,
    clerk_user_id: str,
) -> None:
    conn.execute(
        """
        update invitations
        set target_clerk_user_id = %s,
            status = 'accepted',
            accepted_at = coalesce(accepted_at, now())
        where organization_id = %s
          and target_member_type = 'candidate'
          and (
            candidate_profile_id = %s
            or target_email = %s
          )
          and status in ('pending', 'sent')
        """,
        (clerk_user_id, organization_id, candidate_profile_id, email),
    )
