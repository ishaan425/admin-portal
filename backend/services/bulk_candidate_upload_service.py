"""Shared helpers for bulk resume upload enqueueing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from services.resume_parser import ResumeParseError
from services.settings import get_settings
from services.storage_service import ObjectStorage, build_resume_file_key


@dataclass(frozen=True)
class UploadedResume:
    file_name: str
    content_type: str
    content: bytes


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
