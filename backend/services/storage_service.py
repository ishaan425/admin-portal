"""Private object storage boundary for uploaded files."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from services.settings import AppSettings, get_settings


class StorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    bucket: str | None = None


class ObjectStorage(Protocol):
    def upload_bytes(
        self,
        key: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        ...

    def create_presigned_get_url(self, key: str) -> str:
        ...

    def download_bytes(self, key: str) -> bytes:
        ...


def safe_file_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    return cleaned or "resume.pdf"


def build_resume_file_key(
    organization_id: str,
    batch_id: str,
    original_file_name: str,
    prefix: str = "",
) -> str:
    clean_prefix = prefix.strip("/")
    parts = [
        "organizations",
        organization_id,
        "resume-uploads",
        batch_id,
        f"{uuid.uuid4().hex}-{safe_file_name(original_file_name)}",
    ]
    if clean_prefix:
        parts.insert(0, clean_prefix)
    return "/".join(parts)


class LocalFileStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def upload_bytes(
        self,
        key: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        if not content:
            raise StorageError("Cannot store an empty file.")
        destination = self.root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return StoredObject(key=key)

    def create_presigned_get_url(self, key: str) -> str:
        return str((self.root / key).resolve())

    def download_bytes(self, key: str) -> bytes:
        path = self.root / key
        if not path.exists() or not path.is_file():
            raise StorageError(f"Stored object was not found: {key}")
        return path.read_bytes()


class S3Storage:
    def __init__(self, bucket_name: str, region: str = "", ttl_seconds: int = 900):
        if not bucket_name:
            raise StorageError("S3_BUCKET_NAME is required when STORAGE_BACKEND=s3.")
        self.bucket_name = bucket_name
        self.ttl_seconds = ttl_seconds
        self.client = boto3.client("s3", region_name=region or None)

    def upload_bytes(
        self,
        key: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        if not content:
            raise StorageError("Cannot store an empty file.")
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=content,
                ContentType=content_type or "application/octet-stream",
                Metadata=metadata or {},
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Could not upload object to S3: {exc}") from exc
        return StoredObject(key=key, bucket=self.bucket_name)

    def create_presigned_get_url(self, key: str) -> str:
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=self.ttl_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Could not create S3 presigned URL: {exc}") from exc

    def download_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=key)
            body = response["Body"]
            return body.read()
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Could not download object from S3: {exc}") from exc


def storage_from_settings(settings: AppSettings | None = None) -> ObjectStorage:
    settings = settings or get_settings()
    backend = settings.storage_backend.strip().lower()
    if backend == "local":
        return LocalFileStorage(settings.local_storage_root)
    if backend == "s3":
        return S3Storage(
            bucket_name=settings.s3_bucket_name,
            region=settings.s3_region,
            ttl_seconds=settings.s3_presigned_url_ttl_seconds,
        )
    raise StorageError("STORAGE_BACKEND must be either 'local' or 's3'.")
