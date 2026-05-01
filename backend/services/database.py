"""Database helpers for local services and API handlers."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

from services.settings import get_settings


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def database_url_from_env() -> str:
    database_url = get_settings().database_url.strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required. Add it to .env.")
    return database_url


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url_from_env())
