"""End-to-end bulk candidate upload orchestration.

This service is synchronous for the MVP API boundary. It is intentionally kept
outside the FastAPI route so the same orchestration can later move to a worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from services.auth_service import CurrentOrgMember
from services.clerk_invite_service import ClerkInviteConfig, invite_candidates_from_resume_batch
from services.resume_parser import ResumeParseError, ResumeParserConfig, parse_resume
from services.settings import get_settings
from services.storage_service import ObjectStorage, build_resume_file_key, storage_from_settings


@dataclass(frozen=True)
class UploadedResume:
    file_name: str
    content_type: str
    content: bytes


async def process_bulk_candidate_upload(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    files: list[UploadedResume],
    parser_config: ResumeParserConfig,
    clerk_config: ClerkInviteConfig,
    storage: ObjectStorage | None = None,
    resend_invites: bool = False,
) -> dict[str, Any]:
    parse_result = await process_resume_parsing_batch(
        conn=conn,
        current_member=current_member,
        files=files,
        parser_config=parser_config,
        storage=storage,
    )

    invite_result = invite_candidates_from_resume_batch(
        conn=conn,
        current_member=current_member,
        batch_id=parse_result["batch_id"],
        config=clerk_config,
        dry_run=False,
        resend=resend_invites,
    )

    return {
        "batch_id": parse_result["batch_id"],
        "organization": parse_result["organization"],
        "uploaded_by_clerk_user_id": parse_result["uploaded_by_clerk_user_id"],
        "total_files": parse_result["total_files"],
        "parsed_count": parse_result["parsed_count"],
        "parse_failed_count": parse_result["failed_count"],
        "invited_count": invite_result["sent_count"],
        "invite_failed_count": invite_result["failed_count"],
        "invite_skipped_count": invite_result["skipped_count"],
        "items": merge_item_results(parse_result["items"], invite_result["items"]),
    }


def merge_item_results(
    parse_items: list[dict[str, Any]],
    invite_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    invite_by_parse_item_id = {
        item.get("resume_parse_item_id"): item for item in invite_items
    }

    merged: list[dict[str, Any]] = []
    for item in parse_items:
        invite_item = invite_by_parse_item_id.get(item.get("id"))
        merged.append(
            {
                "resume_parse_item_id": item.get("id"),
                "file_name": item.get("file_name"),
                "resume_file_key": item.get("resume_file_key"),
                "extracted_email": item.get("extracted_email", ""),
                "extracted_full_name": item.get("extracted_full_name", ""),
                "parse_status": item.get("status"),
                "parse_error_message": item.get("error_message"),
                "invite_status": invite_item.get("status") if invite_item else "not_attempted",
                "candidate_profile_id": invite_item.get("candidate_profile_id")
                if invite_item
                else None,
                "invitation_id": invite_item.get("invitation_id") if invite_item else None,
                "clerk_invitation_id": invite_item.get("clerk_invitation_id")
                if invite_item
                else None,
                "invite_error_message": invite_item.get("error_message") if invite_item else None,
            }
        )
    return merged


async def process_resume_parsing_batch(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    files: list[UploadedResume],
    parser_config: ResumeParserConfig,
    storage: ObjectStorage | None = None,
) -> dict[str, Any]:
    if not files:
        raise ResumeParseError("At least one PDF file is required.")

    storage = storage or storage_from_settings()
    batch_id = create_batch(
        conn,
        organization_id=current_member.organization_id,
        uploaded_by=current_member.clerk_user_id,
        total_files=len(files),
    )

    parsed_count = 0
    failed_count = 0
    items: list[dict[str, Any]] = []

    for file in files:
        item_result = await process_one_file(
            conn=conn,
            batch_id=batch_id,
            organization_id=current_member.organization_id,
            file=file,
            parser_config=parser_config,
            storage=storage,
        )
        items.append(item_result)
        if item_result["status"] == "parsed":
            parsed_count += 1
        else:
            failed_count += 1

    finish_batch(conn, batch_id, parsed_count, failed_count)

    return {
        "batch_id": batch_id,
        "organization": {
            "id": current_member.organization_id,
            "name": current_member.organization_name,
            "slug": current_member.organization_slug,
        },
        "uploaded_by_clerk_user_id": current_member.clerk_user_id,
        "total_files": len(files),
        "parsed_count": parsed_count,
        "failed_count": failed_count,
        "items": items,
    }


async def process_one_file(
    conn: psycopg.Connection,
    batch_id: str,
    organization_id: str,
    file: UploadedResume,
    parser_config: ResumeParserConfig,
    storage: ObjectStorage,
) -> dict[str, Any]:
    resume_file_key: str | None = None
    try:
        validate_uploaded_resume(file, parser_config.max_file_size_bytes)
        resume_file_key = store_uploaded_resume(
            storage=storage,
            organization_id=organization_id,
            batch_id=batch_id,
            file=file,
        )
        parsed_resume = await parse_resume(
            file.content,
            config=parser_config,
            source_name=file.file_name,
        )
        item_id = create_parse_item(
            conn=conn,
            batch_id=batch_id,
            organization_id=organization_id,
            file_name=file.file_name,
            resume_file_key=resume_file_key,
            parse_status="parsed",
            parsed_resume=parsed_resume,
            error_message=None,
        )
        personal_info = parsed_resume.get("personal_info") or {}
        return {
            "id": item_id,
            "file_name": file.file_name,
            "resume_file_key": resume_file_key,
            "status": "parsed",
            "extracted_email": personal_info.get("email") or "",
            "extracted_full_name": personal_info.get("full_name") or "",
        }
    except Exception as exc:
        item_id = create_parse_item(
            conn=conn,
            batch_id=batch_id,
            organization_id=organization_id,
            file_name=file.file_name,
            resume_file_key=resume_file_key,
            parse_status="failed",
            parsed_resume=None,
            error_message=str(exc),
        )
        return {
            "id": item_id,
            "file_name": file.file_name,
            "resume_file_key": resume_file_key,
            "status": "failed",
            "error_message": str(exc),
        }


def validate_uploaded_resume(file: UploadedResume, max_file_size_bytes: int) -> None:
    if not file.file_name.lower().endswith(".pdf"):
        raise ResumeParseError("Only PDF files are supported.")
    if not file.content:
        raise ResumeParseError("Uploaded PDF is empty.")
    if len(file.content) > max_file_size_bytes:
        raise ResumeParseError(f"Uploaded PDF exceeds {max_file_size_bytes} bytes.")


def store_uploaded_resume(
    storage: ObjectStorage,
    organization_id: str,
    batch_id: str,
    file: UploadedResume,
) -> str:
    key = build_resume_file_key(
        organization_id=organization_id,
        batch_id=batch_id,
        original_file_name=file.file_name,
        prefix=get_settings().s3_prefix,
    )
    stored_object = storage.upload_bytes(
        key=key,
        content=file.content,
        content_type=file.content_type or "application/pdf",
        metadata={
            "organization_id": organization_id,
            "batch_id": batch_id,
            "original_file_name": file.file_name,
        },
    )
    return stored_object.key


def create_batch(
    conn: psycopg.Connection,
    organization_id: str,
    uploaded_by: str,
    total_files: int,
    status: str = "processing",
) -> str:
    row = conn.execute(
        """
        insert into resume_parse_batches (
            organization_id,
            uploaded_by_clerk_user_id,
            status,
            total_files
        )
        values (%s, %s, %s, %s)
        returning id
        """,
        (organization_id, uploaded_by, status, total_files),
    ).fetchone()
    return str(row[0])


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


def create_parse_item(
    conn: psycopg.Connection,
    batch_id: str,
    organization_id: str,
    file_name: str,
    resume_file_key: str | None,
    parse_status: str,
    parsed_resume: dict[str, Any] | None,
    error_message: str | None,
) -> str:
    parser_metadata = {}
    if parsed_resume and isinstance(parsed_resume.get("_parser"), dict):
        parser_metadata = parsed_resume["_parser"]

    row = conn.execute(
        """
        insert into resume_parse_items (
            batch_id,
            organization_id,
            original_file_name,
            resume_file_key,
            parse_status,
            parsed_resume,
            parser_metadata,
            error_message
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            batch_id,
            organization_id,
            file_name,
            resume_file_key,
            parse_status,
            Jsonb(parsed_resume) if parsed_resume is not None else None,
            Jsonb(parser_metadata),
            error_message,
        ),
    ).fetchone()
    return str(row[0])
