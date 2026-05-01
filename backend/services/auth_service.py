"""Authentication and organization-member resolution."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
import psycopg
from jwt import PyJWKClient

from services.settings import AppSettings, get_settings


class AuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurrentOrgMember:
    organization_id: str
    organization_name: str
    organization_slug: str
    organization_logo_url: str
    clerk_user_id: str
    email: str
    full_name: str
    member_type: str
    role_key: str
    status: str


@lru_cache
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def clerk_user_id_from_jwt(token: str, settings: AppSettings | None = None) -> str:
    settings = settings or get_settings()
    token = (token or "").strip()
    if not token:
        raise AuthError("Bearer token is required.")
    if not settings.clerk_jwks_url:
        raise AuthError("CLERK_JWKS_URL is required for Clerk JWT authentication.")

    try:
        signing_key = _jwks_client(settings.clerk_jwks_url).get_signing_key_from_jwt(token)
        decode_kwargs: dict[str, Any] = {
            "key": signing_key.key,
            "algorithms": ["RS256"],
            "options": {"verify_aud": bool(settings.clerk_audience)},
        }
        if settings.clerk_issuer:
            decode_kwargs["issuer"] = settings.clerk_issuer
        if settings.clerk_audience:
            decode_kwargs["audience"] = settings.clerk_audience

        payload = jwt.decode(token, **decode_kwargs)
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid Clerk bearer token.") from exc
    except Exception as exc:
        raise AuthError(f"Could not verify Clerk bearer token: {exc}") from exc

    clerk_user_id = str(payload.get("sub") or "").strip()
    if not clerk_user_id:
        raise AuthError("Clerk token is missing a subject.")
    return clerk_user_id


def bearer_token_from_authorization(authorization: str | None) -> str:
    value = (authorization or "").strip()
    if not value:
        return ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("Authorization header must use Bearer authentication.")
    return token.strip()


def require_org_admin(
    conn: psycopg.Connection,
    authorization: str | None,
    organization_slug: str | None = None,
    settings: AppSettings | None = None,
) -> CurrentOrgMember:
    settings = settings or get_settings()
    token = bearer_token_from_authorization(authorization)
    if not token:
        raise AuthError("Bearer token is required.")

    return resolve_org_admin_membership(
        conn,
        clerk_user_id=clerk_user_id_from_jwt(token, settings),
        organization_slug=organization_slug,
    )


def require_active_org_member(
    conn: psycopg.Connection,
    authorization: str | None,
    organization_slug: str | None = None,
    settings: AppSettings | None = None,
) -> CurrentOrgMember:
    settings = settings or get_settings()
    token = bearer_token_from_authorization(authorization)
    if not token:
        raise AuthError("Bearer token is required.")

    return resolve_active_org_membership(
        conn,
        clerk_user_id=clerk_user_id_from_jwt(token, settings),
        organization_slug=organization_slug,
    )


def resolve_org_admin_membership(
    conn: psycopg.Connection,
    clerk_user_id: str,
    organization_slug: str | None = None,
) -> CurrentOrgMember:
    clerk_user_id = (clerk_user_id or "").strip()
    if not clerk_user_id:
        raise AuthError("Clerk user id is required.")

    params: list[Any] = [clerk_user_id]
    slug_filter = ""
    if organization_slug:
        slug_filter = "and o.slug = %s"
        params.append(organization_slug.strip())

    rows = conn.execute(
        f"""
        select
            m.organization_id,
            o.name,
            o.slug,
            coalesce(o.logo_url, ''),
            m.clerk_user_id,
            m.email,
            coalesce(m.full_name, ''),
            m.member_type,
            m.role_key,
            m.status
        from organization_members m
        join organizations o on o.id = m.organization_id
        where m.clerk_user_id = %s
          and m.status = 'active'
          and m.member_type = 'admin'
          and m.role_key = 'org_admin'
          and o.status = 'active'
          {slug_filter}
        order by o.created_at asc
        """,
        params,
    ).fetchall()

    if not rows:
        raise AuthError("Active org admin membership was not found.")
    if len(rows) > 1 and not organization_slug:
        raise AuthError("Multiple admin organizations found. Provide X-Organization-Slug.")

    row = rows[0]
    return CurrentOrgMember(
        organization_id=str(row[0]),
        organization_name=row[1],
        organization_slug=row[2],
        organization_logo_url=row[3],
        clerk_user_id=row[4],
        email=row[5],
        full_name=row[6],
        member_type=row[7],
        role_key=row[8],
        status=row[9],
    )


def resolve_active_org_membership(
    conn: psycopg.Connection,
    clerk_user_id: str,
    organization_slug: str | None = None,
) -> CurrentOrgMember:
    clerk_user_id = (clerk_user_id or "").strip()
    if not clerk_user_id:
        raise AuthError("Clerk user id is required.")

    params: list[Any] = [clerk_user_id]
    slug_filter = ""
    if organization_slug:
        slug_filter = "and o.slug = %s"
        params.append(organization_slug.strip())

    rows = conn.execute(
        f"""
        select
            m.organization_id,
            o.name,
            o.slug,
            coalesce(o.logo_url, ''),
            m.clerk_user_id,
            m.email,
            coalesce(m.full_name, ''),
            m.member_type,
            m.role_key,
            m.status
        from organization_members m
        join organizations o on o.id = m.organization_id
        where m.clerk_user_id = %s
          and m.status = 'active'
          and o.status = 'active'
          {slug_filter}
        order by o.created_at asc
        """,
        params,
    ).fetchall()

    if not rows:
        raise AuthError("Active organization membership was not found.")
    if len(rows) > 1 and not organization_slug:
        raise AuthError("Multiple organizations found. Provide X-Organization-Slug.")

    row = rows[0]
    return CurrentOrgMember(
        organization_id=str(row[0]),
        organization_name=row[1],
        organization_slug=row[2],
        organization_logo_url=row[3],
        clerk_user_id=row[4],
        email=row[5],
        full_name=row[6],
        member_type=row[7],
        role_key=row[8],
        status=row[9],
    )
