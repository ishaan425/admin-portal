"""Save parsed resume JSON into existing candidate profile tables.

This local runner uses the existing Admin Portal schema only:
- organizations
- organization_members
- candidate_profiles
- resume_parse_batches
- resume_parse_items
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEFAULT_ORG_SLUG = "lpu"
DEFAULT_UPLOADED_BY = "local_lpu_admin"


class ImportErrorForUser(RuntimeError):
    pass


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def read_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ImportErrorForUser(f"Results file does not exist: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    resumes = data.get("resumes")
    if not isinstance(resumes, list):
        raise ImportErrorForUser("Expected results JSON to contain a resumes list.")
    return resumes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save parsed resume results into candidate_profiles."
    )
    parser.add_argument(
        "--results",
        default="parsed_resumes/results.json",
        help="Path to parsed resume results JSON.",
    )
    parser.add_argument(
        "--organization-slug",
        default=DEFAULT_ORG_SLUG,
        help="Organization slug to store candidates under. Default: lpu",
    )
    parser.add_argument(
        "--uploaded-by-clerk-user-id",
        default=DEFAULT_UPLOADED_BY,
        help="Existing org member clerk_user_id used as uploader. Default: local_lpu_admin",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print actions without writing to Postgres.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    resumes = read_results(Path(args.results).expanduser())
    if args.dry_run:
        return dry_run(resumes)

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise ImportErrorForUser("DATABASE_URL is required. Add it to .env.")

    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            organization = get_organization(conn, args.organization_slug)
            ensure_uploader_exists(conn, organization["id"], args.uploaded_by_clerk_user_id)
            batch_id = create_batch(
                conn,
                organization_id=organization["id"],
                uploaded_by=args.uploaded_by_clerk_user_id,
                total_files=len(resumes),
            )

            parsed_count = 0
            failed_count = 0
            for resume_item in resumes:
                if resume_item.get("status") != "parsed":
                    failed_count += 1
                    create_parse_item(
                        conn,
                        batch_id=batch_id,
                        organization_id=organization["id"],
                        resume_item=resume_item,
                        parse_status="failed",
                        parsed_resume=None,
                        error_message=resume_item.get("error") or "Resume was not parsed.",
                    )
                    continue

                parsed_resume = resume_item.get("parsed_resume") or {}
                personal_info = parsed_resume.get("personal_info") or {}
                email = normalize_email(personal_info.get("email"))
                if not EMAIL_PATTERN.match(email):
                    failed_count += 1
                    create_parse_item(
                        conn,
                        batch_id=batch_id,
                        organization_id=organization["id"],
                        resume_item=resume_item,
                        parse_status="failed",
                        parsed_resume=parsed_resume,
                        error_message=f"Missing or invalid extracted email: {email}",
                    )
                    continue

                full_name = str(personal_info.get("full_name") or "").strip()

                upsert_candidate_profile(
                    conn,
                    organization_id=organization["id"],
                    email=email,
                    full_name=full_name,
                    resume_item=resume_item,
                    parsed_resume=parsed_resume,
                )
                create_parse_item(
                    conn,
                    batch_id=batch_id,
                    organization_id=organization["id"],
                    resume_item=resume_item,
                    parse_status="parsed",
                    parsed_resume=parsed_resume,
                    error_message=None,
                )
                parsed_count += 1

            finish_batch(conn, batch_id, parsed_count, failed_count)

    print(f"Saved {parsed_count} candidate profile(s); {failed_count} failed.")
    return 0 if failed_count == 0 else 1


def dry_run(resumes: list[dict[str, Any]]) -> int:
    for resume_item in resumes:
        parsed_resume = resume_item.get("parsed_resume") or {}
        personal_info = parsed_resume.get("personal_info") or {}
        email = normalize_email(personal_info.get("email"))
        full_name = str(personal_info.get("full_name") or "").strip()
        status = "ok" if EMAIL_PATTERN.match(email) else "invalid_email"
        print(f"{status}: {resume_item.get('file_name')} -> {email} ({full_name})")
    return 0


def get_organization(conn: psycopg.Connection, slug: str) -> dict[str, Any]:
    row = conn.execute(
        "select id, name, logo_url from organizations where slug = %s",
        (slug,),
    ).fetchone()
    if not row:
        raise ImportErrorForUser(
            f"Organization slug '{slug}' does not exist. Run db/seeds/001_seed_lpu_dummy_org.sql."
        )
    return {"id": row[0], "name": row[1], "logo_url": row[2] or ""}


def ensure_uploader_exists(conn: psycopg.Connection, organization_id: str, clerk_user_id: str) -> None:
    row = conn.execute(
        """
        select 1
        from organization_members
        where organization_id = %s and clerk_user_id = %s
        """,
        (organization_id, clerk_user_id),
    ).fetchone()
    if not row:
        raise ImportErrorForUser(
            f"Uploader '{clerk_user_id}' is not a member of organization {organization_id}."
        )


def create_batch(
    conn: psycopg.Connection,
    organization_id: str,
    uploaded_by: str,
    total_files: int,
) -> str:
    row = conn.execute(
        """
        insert into resume_parse_batches (
            organization_id,
            uploaded_by_clerk_user_id,
            status,
            total_files
        )
        values (%s, %s, 'processing', %s)
        returning id
        """,
        (organization_id, uploaded_by, total_files),
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


def upsert_candidate_profile(
    conn: psycopg.Connection,
    organization_id: str,
    email: str,
    full_name: str,
    resume_item: dict[str, Any],
    parsed_resume: dict[str, Any],
) -> None:
    conn.execute(
        """
        insert into candidate_profiles (
            organization_id,
            email,
            full_name,
            resume_file_name,
            resume_data,
            resume_parse_status,
            resume_uploaded_at,
            updated_at
        )
        values (%s, %s, %s, %s, %s, 'parsed', %s, now())
        on conflict (organization_id, email) do update
        set resume_file_name = excluded.resume_file_name,
            full_name = excluded.full_name,
            resume_data = excluded.resume_data,
            resume_parse_status = excluded.resume_parse_status,
            resume_uploaded_at = excluded.resume_uploaded_at,
            updated_at = now()
        """,
        (
            organization_id,
            email,
            full_name,
            resume_item.get("file_name") or "",
            Jsonb(parsed_resume),
            datetime.now(timezone.utc),
        ),
    )


def create_parse_item(
    conn: psycopg.Connection,
    batch_id: str,
    organization_id: str,
    resume_item: dict[str, Any],
    parse_status: str,
    parsed_resume: dict[str, Any] | None,
    error_message: str | None,
) -> None:
    parser_metadata = {}
    if parsed_resume and isinstance(parsed_resume.get("_parser"), dict):
        parser_metadata = parsed_resume["_parser"]

    conn.execute(
        """
        insert into resume_parse_items (
            batch_id,
            organization_id,
            original_file_name,
            parse_status,
            parsed_resume,
            parser_metadata,
            error_message
        )
        values (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            batch_id,
            organization_id,
            resume_item.get("file_name") or "",
            parse_status,
            Jsonb(parsed_resume) if parsed_resume is not None else None,
            Jsonb(parser_metadata),
            error_message,
        ),
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportErrorForUser as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
