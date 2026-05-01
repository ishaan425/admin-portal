"""Reusable Clerk invitation helpers for admin portal onboarding.

This module is intentionally small and dependency-light so it can be reused by:

- local smoke-test scripts
- future bulk upload workers
- backend service code
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import certifi


CLERK_INVITATIONS_URL = "https://api.clerk.com/v1/invitations"
DEFAULT_REDIRECT_URL = "https://app.growqr.ai/login"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(email))


@dataclass(frozen=True)
class CandidateInvite:
    email: str
    full_name: str
    phone: str

    def normalized_email(self) -> str:
        return normalize_email(self.email)


def build_invitation_payload(
    candidate: CandidateInvite,
    redirect_url: str,
    notify: bool,
    tenant_name: str,
    tenant_logo_url: str,
    public_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "source": "admin_portal_new_hardcoded_candidate_invite",
        "invited": True,
        "tenant_name": tenant_name,
        "tenant_logo_url": tenant_logo_url,
        "candidate_full_name": candidate.full_name,
        "candidate_phone": candidate.phone,
    }
    if public_metadata:
        metadata.update(public_metadata)

    return {
        "email_address": candidate.normalized_email(),
        "redirect_url": redirect_url,
        "ignore_existing": True,
        "notify": notify,
        "public_metadata": metadata,
    }


def create_clerk_invitation(
    secret_key: str,
    payload: dict[str, Any],
) -> tuple[int, Any, dict[str, str]]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        CLERK_INVITATIONS_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "GrowQR-AdminPortal/1.0",
        },
    )

    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            raw = response.read().decode("utf-8")
            headers = dict(response.headers.items())
            return response.status, json.loads(raw) if raw else {}, headers
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        headers = dict(exc.headers.items())
        try:
            return exc.code, json.loads(raw), headers
        except json.JSONDecodeError:
            return exc.code, raw, headers
    except urllib.error.URLError as exc:
        return 0, {"message": f"Network error while calling Clerk: {exc.reason}"}, {}


def require_public_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")
