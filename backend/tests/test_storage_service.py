from pathlib import Path

import pytest

from services.settings import AppSettings
from services.storage_service import (
    LocalFileStorage,
    StorageError,
    build_resume_file_key,
    safe_file_name,
    storage_from_settings,
)


def test_safe_file_name_removes_path_and_shell_unfriendly_characters():
    assert safe_file_name("../My Resume (Final).pdf") == "My-Resume-Final-.pdf"
    assert safe_file_name("   ") == "resume.pdf"


def test_build_resume_file_key_is_tenant_and_batch_scoped():
    key = build_resume_file_key(
        organization_id="org-123",
        batch_id="batch-456",
        original_file_name="My Resume.pdf",
        prefix="growqr-admin",
    )

    assert key.startswith("growqr-admin/organizations/org-123/resume-uploads/batch-456/")
    assert key.endswith("-My-Resume.pdf")


def test_local_file_storage_writes_under_configured_root(tmp_path):
    storage = LocalFileStorage(tmp_path)

    stored = storage.upload_bytes(
        key="organizations/org-123/resume.pdf",
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )

    assert stored.key == "organizations/org-123/resume.pdf"
    assert (tmp_path / stored.key).read_bytes() == b"%PDF-1.4"
    assert storage.download_bytes(stored.key) == b"%PDF-1.4"
    assert Path(storage.create_presigned_get_url(stored.key)).exists()


def test_storage_from_settings_requires_s3_bucket_for_s3_backend():
    with pytest.raises(StorageError, match="S3_BUCKET_NAME"):
        storage_from_settings(AppSettings(storage_backend="s3", s3_bucket_name=""))
