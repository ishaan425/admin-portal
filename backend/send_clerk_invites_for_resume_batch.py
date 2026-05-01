"""Send Clerk invitations for parsed resume items in a batch."""

from __future__ import annotations

import argparse
import json
import sys

from services.auth_service import AuthError, require_local_org_admin
from services.clerk_invite_service import (
    ClerkInviteConfig,
    ClerkInvitePipelineError,
    clerk_invite_config_from_env,
    invite_candidates_from_resume_batch,
)
from services.database import connect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send candidate Clerk invitations for a parsed resume batch."
    )
    parser.add_argument("--batch-id", required=True, help="resume_parse_batches.id")
    parser.add_argument(
        "--uploaded-by-clerk-user-id",
        default="local_lpu_admin",
        help="Local org admin clerk_user_id. Default: local_lpu_admin",
    )
    parser.add_argument(
        "--organization-slug",
        default="lpu",
        help="Organization slug. Default: lpu",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print Clerk payloads without writing candidate rows or sending invites.",
    )
    parser.add_argument(
        "--resend",
        action="store_true",
        help="Send a new Clerk invitation even if an active invitation already exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = (
        ClerkInviteConfig(secret_key="dry_run", notify=False)
        if args.dry_run
        else clerk_invite_config_from_env()
    )

    with connect() as conn:
        with conn.transaction():
            current_member = require_local_org_admin(
                conn,
                clerk_user_id=args.uploaded_by_clerk_user_id,
                organization_slug=args.organization_slug,
            )
            result = invite_candidates_from_resume_batch(
                conn=conn,
                current_member=current_member,
                batch_id=args.batch_id,
                config=config,
                dry_run=args.dry_run,
                resend=args.resend,
            )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["failed_count"] == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AuthError, ClerkInvitePipelineError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
