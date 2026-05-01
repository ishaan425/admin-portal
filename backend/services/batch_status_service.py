"""Read models for resume upload batch status."""

from __future__ import annotations

from typing import Any

import psycopg


def get_resume_upload_batch_status(
    conn: psycopg.Connection,
    organization_id: str,
    batch_id: str,
) -> dict[str, Any] | None:
    batch_row = conn.execute(
        """
        select
            b.id,
            b.status,
            b.total_files,
            b.parsed_count,
            b.failed_count,
            b.created_at,
            b.completed_at,
            o.id,
            o.name,
            o.slug
        from resume_parse_batches b
        join organizations o on o.id = b.organization_id
        where b.organization_id = %s
          and b.id = %s
        """,
        (organization_id, batch_id),
    ).fetchone()
    if not batch_row:
        return None

    item_rows = conn.execute(
        """
        select
            i.id,
            i.original_file_name,
            i.resume_file_key,
            i.parse_status,
            i.error_message,
            i.created_at,
            i.updated_at,
            i.parsed_resume #>> '{personal_info,email}' as extracted_email,
            i.parsed_resume #>> '{personal_info,full_name}' as extracted_full_name,
            inv.candidate_profile_id,
            inv.status as invite_status,
            inv.clerk_invitation_id,
            inv.error_message as invite_error_message
        from resume_parse_items i
        left join invitations inv
          on inv.organization_id = i.organization_id
         and inv.target_email = i.parsed_resume #>> '{personal_info,email}'
         and inv.target_member_type = 'candidate'
        where i.organization_id = %s
          and i.batch_id = %s
        order by i.created_at asc, inv.created_at desc
        """,
        (organization_id, batch_id),
    ).fetchall()

    seen_items: set[str] = set()
    items: list[dict[str, Any]] = []
    for row in item_rows:
        item_id = str(row[0])
        if item_id in seen_items:
            continue
        seen_items.add(item_id)
        items.append(
            {
                "resume_parse_item_id": item_id,
                "file_name": row[1],
                "resume_file_key": row[2],
                "parse_status": row[3],
                "parse_error_message": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "updated_at": row[6].isoformat() if row[6] else None,
                "extracted_email": row[7] or "",
                "extracted_full_name": row[8] or "",
                "candidate_profile_id": str(row[9]) if row[9] else None,
                "invite_status": row[10] or "not_attempted",
                "clerk_invitation_id": row[11],
                "invite_error_message": row[12],
            }
        )

    return {
        "batch_id": str(batch_row[0]),
        "status": batch_row[1],
        "total_files": batch_row[2],
        "parsed_count": batch_row[3],
        "failed_count": batch_row[4],
        "created_at": batch_row[5].isoformat() if batch_row[5] else None,
        "completed_at": batch_row[6].isoformat() if batch_row[6] else None,
        "organization": {
            "id": str(batch_row[7]),
            "name": batch_row[8],
            "slug": batch_row[9],
        },
        "items": items,
    }
