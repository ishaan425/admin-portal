"""Fast API-side enqueue flow for bulk resume uploads."""

from __future__ import annotations

import logging
from typing import Any

import psycopg

from services.auth_service import CurrentOrgMember
from services.resume_upload_contracts import (
    RESUME_UPLOAD_JOB_TYPE,
    ResumeUploadQueuePayload,
    UploadedResume,
)
from services.resume_upload_records import (
    create_batch,
    create_parse_item,
    store_uploaded_resume,
    validate_uploaded_resume,
)
from services.queue_service import QueueClient
from services.resume_parser import ResumeParseError
from services.storage_service import ObjectStorage


logger = logging.getLogger(__name__)


def create_resume_upload_batch(
    conn: psycopg.Connection,
    current_member: CurrentOrgMember,
    files: list[UploadedResume],
    storage: ObjectStorage,
    max_file_size_bytes: int,
) -> dict[str, Any]:
    if not files:
        raise ResumeParseError("At least one PDF file is required.")

    batch_id = create_batch(
        conn,
        organization_id=current_member.organization_id,
        uploaded_by=current_member.clerk_user_id,
        total_files=len(files),
        status="pending",
    )
    logger.info(
        "Created resume upload batch",
        extra={
            "batch_id": batch_id,
            "organization_id": current_member.organization_id,
            "total_files": len(files),
        },
    )

    items: list[dict[str, Any]] = []
    for file in files:
        validate_uploaded_resume(file, max_file_size_bytes)
        resume_file_key = store_uploaded_resume(
            storage=storage,
            organization_id=current_member.organization_id,
            batch_id=batch_id,
            file=file,
        )
        item_id = create_parse_item(
            conn=conn,
            batch_id=batch_id,
            organization_id=current_member.organization_id,
            file_name=file.file_name,
            resume_file_key=resume_file_key,
            parse_status="pending",
            parsed_resume=None,
            error_message=None,
        )
        items.append(
            {
                "resume_parse_item_id": item_id,
                "file_name": file.file_name,
                "resume_file_key": resume_file_key,
                "parse_status": "pending",
            }
        )

    queue_payload = ResumeUploadQueuePayload(
        batch_id=batch_id,
        organization_id=current_member.organization_id,
        uploaded_by_clerk_user_id=current_member.clerk_user_id,
        resend_invites=True,
    )

    return {
        "batch_id": batch_id,
        "status": "pending",
        "organization": {
            "id": current_member.organization_id,
            "name": current_member.organization_name,
            "slug": current_member.organization_slug,
        },
        "uploaded_by_clerk_user_id": current_member.clerk_user_id,
        "total_files": len(files),
        "items": items,
        "queue_payload": queue_payload.to_message(),
    }


def enqueue_resume_upload_batch(
    queue: QueueClient,
    enqueue_result: dict[str, Any],
) -> dict[str, Any]:
    message_id = queue.send_message(enqueue_result["queue_payload"])
    logger.info(
        "Enqueued resume upload batch",
        extra={
            "batch_id": enqueue_result.get("batch_id"),
            "queue_message_id": message_id,
        },
    )
    return {
        key: value
        for key, value in {
            **enqueue_result,
            "status": "queued",
            "queue_message_id": message_id,
        }.items()
        if key != "queue_payload"
    }
