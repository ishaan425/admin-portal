"""DB-backed feature permission checks."""

from __future__ import annotations

import psycopg

from services.auth_service import CurrentOrgMember


ACTION_MASKS = {
    "read": 1,
    "create": 2,
    "update": 4,
    "delete": 8,
    "upload": 16,
    "publish": 32,
    "assign": 64,
    "export": 128,
}


class PermissionError(RuntimeError):
    pass


def require_feature_permission(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    feature_key: str,
    action: str,
) -> None:
    action_mask = ACTION_MASKS.get(action)
    if action_mask is None:
        raise PermissionError(f"Unsupported permission action: {action}.")

    row = conn.execute(
        """
        select rp.action_mask
        from role_permissions rp
        join organization_roles r
          on r.organization_id = rp.organization_id
         and r.role_key = rp.role_key
        join features f on f.feature_key = rp.feature_key
        where rp.organization_id = %s
          and rp.role_key = %s
          and rp.feature_key = %s
          and r.status = 'active'
          and f.status = 'active'
        """,
        (current_member.organization_id, current_member.role_key, feature_key),
    ).fetchone()
    if not row or int(row[0] or 0) & action_mask != action_mask:
        raise PermissionError(f"Missing {feature_key}.{action} permission.")


def require_enterprise_organization(conn: psycopg.Connection, organization_id: str) -> None:
    row = conn.execute(
        """
        select org_type
        from organizations
        where id = %s
          and status = 'active'
        """,
        (organization_id,),
    ).fetchone()
    if not row:
        raise PermissionError("Active organization was not found.")
    if row[0] != "enterprise":
        raise PermissionError("Only Enterprise organizations can manage job openings.")
