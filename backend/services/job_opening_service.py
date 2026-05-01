"""Enterprise job opening business logic."""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from schemas.job_schema import JobOpeningCreate, JobOpeningUpdate
from services.auth_service import CurrentOrgMember
from services.permission_service import require_enterprise_organization, require_feature_permission


JOBS_FEATURE_KEY = "jobs"


class JobOpeningError(RuntimeError):
    pass


class JobOpeningNotFoundError(JobOpeningError):
    pass


def create_job_opening(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    payload: JobOpeningCreate,
) -> dict[str, Any]:
    require_job_access(conn, current_member, "create")
    metadata = job_metadata_from_model(payload)
    row = conn.execute(
        """
        insert into org_resources (
            organization_id,
            resource_type,
            created_by_clerk_user_id,
            title,
            status,
            metadata
        )
        values (%s, 'job', %s, %s, 'draft', %s)
        returning id, organization_id, created_by_clerk_user_id, title, status, metadata, created_at, updated_at
        """,
        (
            current_member.organization_id,
            current_member.clerk_user_id,
            payload.title,
            Jsonb(metadata),
        ),
    ).fetchone()
    return job_response_from_row(row)


def list_job_openings(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    status: str | None = None,
) -> list[dict[str, Any]]:
    require_job_access(conn, current_member, "read")
    params: list[Any] = [current_member.organization_id]
    status_filter = ""
    if status:
        status_filter = "and status = %s"
        params.append(status)

    rows = conn.execute(
        f"""
        select id, organization_id, created_by_clerk_user_id, title, status, metadata, created_at, updated_at
        from org_resources
        where organization_id = %s
          and resource_type = 'job'
          {status_filter}
        order by created_at desc
        """,
        params,
    ).fetchall()
    return [job_response_from_row(row) for row in rows]


def get_job_opening(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    job_id: str,
) -> dict[str, Any]:
    require_job_access(conn, current_member, "read")
    return get_job_opening_for_org(conn, current_member.organization_id, job_id)


def update_job_opening(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    job_id: str,
    payload: JobOpeningUpdate,
) -> dict[str, Any]:
    require_job_access(conn, current_member, "update")
    current_job = get_job_opening_for_org(conn, current_member.organization_id, job_id)
    metadata = dict(current_job["metadata"] or {})
    updates = payload.model_dump(exclude_unset=True, mode="json")
    title = updates.pop("title", None)
    metadata.update({key: value for key, value in updates.items()})
    validate_metadata_ranges(metadata)
    validate_publishable_metadata(
        title=title or current_job["title"],
        metadata=metadata,
        require_complete=current_job["status"] == "published",
    )

    row = conn.execute(
        """
        update org_resources
        set title = coalesce(%s, title),
            metadata = %s,
            updated_at = now()
        where organization_id = %s
          and id = %s
          and resource_type = 'job'
        returning id, organization_id, created_by_clerk_user_id, title, status, metadata, created_at, updated_at
        """,
        (
            title,
            Jsonb(metadata),
            current_member.organization_id,
            job_id,
        ),
    ).fetchone()
    if not row:
        raise JobOpeningNotFoundError("Job opening was not found.")
    return job_response_from_row(row)


def publish_job_opening(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    job_id: str,
) -> dict[str, Any]:
    require_job_access(conn, current_member, "publish")
    current_job = get_job_opening_for_org(conn, current_member.organization_id, job_id)
    validate_publishable_metadata(
        title=current_job["title"],
        metadata=current_job["metadata"],
        require_complete=True,
    )
    return set_job_status(conn, current_member.organization_id, job_id, "published")


def archive_job_opening(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    job_id: str,
) -> dict[str, Any]:
    require_job_access(conn, current_member, "update")
    get_job_opening_for_org(conn, current_member.organization_id, job_id)
    return set_job_status(conn, current_member.organization_id, job_id, "archived")


def require_job_access(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    action: str,
) -> None:
    require_enterprise_organization(conn, current_member.organization_id)
    require_feature_permission(conn, current_member, JOBS_FEATURE_KEY, action)


def get_job_opening_for_org(
    conn: psycopg.Connection,
    organization_id: str,
    job_id: str,
) -> dict[str, Any]:
    row = conn.execute(
        """
        select id, organization_id, created_by_clerk_user_id, title, status, metadata, created_at, updated_at
        from org_resources
        where organization_id = %s
          and id = %s
          and resource_type = 'job'
        """,
        (organization_id, job_id),
    ).fetchone()
    if not row:
        raise JobOpeningNotFoundError("Job opening was not found.")
    return job_response_from_row(row)


def set_job_status(
    conn: psycopg.Connection,
    organization_id: str,
    job_id: str,
    status: str,
) -> dict[str, Any]:
    row = conn.execute(
        """
        update org_resources
        set status = %s,
            updated_at = now()
        where organization_id = %s
          and id = %s
          and resource_type = 'job'
        returning id, organization_id, created_by_clerk_user_id, title, status, metadata, created_at, updated_at
        """,
        (status, organization_id, job_id),
    ).fetchone()
    if not row:
        raise JobOpeningNotFoundError("Job opening was not found.")
    return job_response_from_row(row)


def job_metadata_from_model(payload: JobOpeningCreate) -> dict[str, Any]:
    return payload.model_dump(exclude={"title"}, mode="json")


def validate_publishable_metadata(
    title: str,
    metadata: dict[str, Any],
    require_complete: bool,
) -> None:
    if not require_complete:
        return

    required_metadata_fields = [
        "work_mode",
        "employment_type",
        "location",
        "description",
        "requirements",
        "skills",
        "open_positions",
    ]
    missing = [field for field in required_metadata_fields if not metadata.get(field)]
    if not title.strip():
        missing.insert(0, "title")
    if missing:
        raise JobOpeningError(f"Cannot publish job opening. Missing required fields: {', '.join(missing)}.")


def validate_metadata_ranges(metadata: dict[str, Any]) -> None:
    experience_min = metadata.get("experience_min_years")
    experience_max = metadata.get("experience_max_years")
    if experience_min is not None and experience_max is not None and experience_min > experience_max:
        raise JobOpeningError("experience_min_years cannot exceed experience_max_years.")

    salary_min = metadata.get("salary_min")
    salary_max = metadata.get("salary_max")
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        raise JobOpeningError("salary_min cannot exceed salary_max.")


def job_response_from_row(row: Any) -> dict[str, Any]:
    metadata = row[5] or {}
    return {
        "id": str(row[0]),
        "organization_id": str(row[1]),
        "created_by_clerk_user_id": row[2],
        "title": row[3],
        "status": row[4],
        "metadata": normalize_json_value(metadata),
        "created_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
    }


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_json_value(item) for item in value]
    return value
