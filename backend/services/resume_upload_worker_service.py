"""Worker-side processing for queued resume upload batches."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from services.auth_service import CurrentOrgMember
from services.clerk_invite_service import ClerkInviteConfig, invite_candidates_from_resume_batch
from services.resume_parser import ResumeParserConfig, parse_resume
from services.resume_upload_enqueue_service import RESUME_UPLOAD_JOB_TYPE
from services.storage_service import ObjectStorage


class ResumeUploadWorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResumeUploadJob:
    batch_id: str
    organization_id: str
    uploaded_by_clerk_user_id: str
    resend_invites: bool = True


def resume_upload_job_from_message(body: dict[str, Any]) -> ResumeUploadJob:
    if body.get("job_type") != RESUME_UPLOAD_JOB_TYPE:
        raise ResumeUploadWorkerError("Unsupported queue job type.")

    batch_id = str(body.get("batch_id") or "").strip()
    organization_id = str(body.get("organization_id") or "").strip()
    uploaded_by = str(body.get("uploaded_by_clerk_user_id") or "").strip()
    if not batch_id or not organization_id or not uploaded_by:
        raise ResumeUploadWorkerError("Resume upload job is missing required identifiers.")

    return ResumeUploadJob(
        batch_id=batch_id,
        organization_id=organization_id,
        uploaded_by_clerk_user_id=uploaded_by,
        resend_invites=bool(body.get("resend_invites", True)),
    )


async def process_resume_upload_job(
    conn: psycopg.Connection,
    job: ResumeUploadJob,
    storage: ObjectStorage,
    parser_config: ResumeParserConfig,
    clerk_config: ClerkInviteConfig,
    parse_concurrency: int = 1,
) -> dict[str, Any]:
    current_member = get_uploading_admin_member(conn, job)
    mark_batch_processing(conn, job.batch_id)

    item_results = await process_pending_resume_parse_items(
        conn=conn,
        items=get_pending_resume_parse_items(conn, job.organization_id, job.batch_id),
        storage=storage,
        parser_config=parser_config,
        concurrency=parse_concurrency,
    )
    parsed_count = sum(1 for item in item_results if item["status"] == "parsed")
    failed_count = len(item_results) - parsed_count

    finish_batch(conn, job.batch_id, parsed_count, failed_count)
    invite_result = invite_candidates_from_resume_batch(
        conn=conn,
        current_member=current_member,
        batch_id=job.batch_id,
        config=clerk_config,
        dry_run=False,
        resend=job.resend_invites,
    )

    return {
        "batch_id": job.batch_id,
        "organization": {
            "id": current_member.organization_id,
            "name": current_member.organization_name,
            "slug": current_member.organization_slug,
        },
        "parsed_count": parsed_count,
        "failed_count": failed_count,
        "invited_count": invite_result["sent_count"],
        "invite_failed_count": invite_result["failed_count"],
        "invite_skipped_count": invite_result["skipped_count"],
        "items": item_results,
    }


async def process_pending_resume_parse_items(
    conn: psycopg.Connection,
    items: list[dict[str, Any]],
    storage: ObjectStorage,
    parser_config: ResumeParserConfig,
    concurrency: int,
) -> list[dict[str, Any]]:
    """Parse multiple resume items concurrently, while keeping DB writes sequential."""
    if not items:
        return []

    for item in items:
        mark_parse_item_processing(conn, item["id"])

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def parse_one(item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await parse_pending_resume_parse_item(
                item=item,
                storage=storage,
                parser_config=parser_config,
            )

    parsed_items = await asyncio.gather(*(parse_one(item) for item in items))
    item_results: list[dict[str, Any]] = []

    for item_result in parsed_items:
        parsed_resume = item_result.pop("_parsed_resume", None)
        if item_result["status"] == "parsed":
            mark_parse_item_parsed(conn, item_result["resume_parse_item_id"], parsed_resume or {})
        else:
            mark_parse_item_failed(
                conn,
                item_result["resume_parse_item_id"],
                item_result.get("error_message") or "Resume parsing failed.",
            )
        item_results.append(item_result)

    return item_results


async def parse_pending_resume_parse_item(
    item: dict[str, Any],
    storage: ObjectStorage,
    parser_config: ResumeParserConfig,
) -> dict[str, Any]:
    try:
        if not item.get("resume_file_key"):
            raise ResumeUploadWorkerError("Resume file key is missing.")
        pdf_bytes = await asyncio.to_thread(storage.download_bytes, item["resume_file_key"])
        parsed_resume = await parse_resume(
            pdf_bytes,
            config=parser_config,
            source_name=item["original_file_name"],
        )
        personal_info = parsed_resume.get("personal_info") or {}
        return {
            "resume_parse_item_id": item["id"],
            "file_name": item["original_file_name"],
            "resume_file_key": item["resume_file_key"],
            "status": "parsed",
            "extracted_email": personal_info.get("email") or "",
            "extracted_full_name": personal_info.get("full_name") or "",
            "_parsed_resume": parsed_resume,
        }
    except Exception as exc:
        return {
            "resume_parse_item_id": item["id"],
            "file_name": item["original_file_name"],
            "resume_file_key": item.get("resume_file_key"),
            "status": "failed",
            "error_message": str(exc),
        }


def get_uploading_admin_member(
    conn: psycopg.Connection,
    job: ResumeUploadJob,
) -> CurrentOrgMember:
    row = conn.execute(
        """
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
        where m.organization_id = %s
          and m.clerk_user_id = %s
          and m.status = 'active'
          and m.member_type = 'admin'
          and m.role_key = 'org_admin'
          and o.status = 'active'
        """,
        (job.organization_id, job.uploaded_by_clerk_user_id),
    ).fetchone()
    if not row:
        raise ResumeUploadWorkerError("Uploading admin membership was not found.")

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


def get_pending_resume_parse_items(
    conn: psycopg.Connection,
    organization_id: str,
    batch_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select id, original_file_name, resume_file_key
        from resume_parse_items
        where organization_id = %s
          and batch_id = %s
          and parse_status in ('pending', 'failed')
        order by created_at asc
        """,
        (organization_id, batch_id),
    ).fetchall()
    return [
        {
            "id": str(row[0]),
            "original_file_name": row[1],
            "resume_file_key": row[2],
        }
        for row in rows
    ]


def mark_batch_processing(conn: psycopg.Connection, batch_id: str) -> None:
    conn.execute(
        """
        update resume_parse_batches
        set status = 'processing'
        where id = %s
          and status in ('pending', 'failed')
        """,
        (batch_id,),
    )


def finish_batch(conn: psycopg.Connection, batch_id: str, parsed_count: int, failed_count: int) -> None:
    status = "completed" if failed_count == 0 else "completed_with_errors"
    conn.execute(
        """
        update resume_parse_batches
        set status = %s,
            parsed_count = %s,
            failed_count = %s,
            completed_at = %s
        where id = %s
        """,
        (status, parsed_count, failed_count, datetime.now(timezone.utc), batch_id),
    )


def mark_parse_item_processing(conn: psycopg.Connection, item_id: str) -> None:
    conn.execute(
        """
        update resume_parse_items
        set parse_status = 'processing',
            error_message = null,
            updated_at = now()
        where id = %s
        """,
        (item_id,),
    )


def mark_parse_item_parsed(
    conn: psycopg.Connection,
    item_id: str,
    parsed_resume: dict[str, Any],
) -> None:
    parser_metadata = {}
    if isinstance(parsed_resume.get("_parser"), dict):
        parser_metadata = parsed_resume["_parser"]
    conn.execute(
        """
        update resume_parse_items
        set parse_status = 'parsed',
            parsed_resume = %s,
            parser_metadata = %s,
            error_message = null,
            updated_at = now()
        where id = %s
        """,
        (Jsonb(parsed_resume), Jsonb(parser_metadata), item_id),
    )


def mark_parse_item_failed(conn: psycopg.Connection, item_id: str, error_message: str) -> None:
    conn.execute(
        """
        update resume_parse_items
        set parse_status = 'failed',
            error_message = %s,
            updated_at = now()
        where id = %s
        """,
        (error_message[:2000], item_id),
    )
