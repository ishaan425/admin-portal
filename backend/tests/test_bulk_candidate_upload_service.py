import pytest

from services.bulk_candidate_upload_service import (
    UploadedResume,
    create_parse_item,
    store_uploaded_resume,
    validate_uploaded_resume,
)
from services.resume_parser import ResumeParseError
from services.storage_service import StoredObject


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return FakeResult(("33333333-3333-4333-8333-333333333333",))


def test_validate_uploaded_resume_accepts_small_pdf():
    validate_uploaded_resume(
        UploadedResume("resume.pdf", "application/pdf", b"%PDF-1.4"),
        max_file_size_bytes=100,
    )


def test_validate_uploaded_resume_rejects_non_pdf():
    with pytest.raises(ResumeParseError, match="Only PDF files"):
        validate_uploaded_resume(
            UploadedResume("resume.txt", "text/plain", b"hello"),
            max_file_size_bytes=100,
        )


def test_create_parse_item_writes_parser_metadata_separately():
    conn = FakeConn()
    parsed_resume = {
        "personal_info": {"email": "candidate@example.com"},
        "_parser": {"model": "gpt-5.4", "path": "vision"},
    }

    item_id = create_parse_item(
        conn=conn,
        batch_id="22222222-2222-4222-8222-222222222222",
        organization_id="11111111-1111-4111-8111-111111111111",
        file_name="resume.pdf",
        resume_file_key="growqr-admin/organizations/111/resume.pdf",
        parse_status="parsed",
        parsed_resume=parsed_resume,
        error_message=None,
    )

    query, params = conn.calls[0]
    assert item_id == "33333333-3333-4333-8333-333333333333"
    assert "insert into resume_parse_items" in query
    assert params[2] == "resume.pdf"
    assert params[3] == "growqr-admin/organizations/111/resume.pdf"
    assert params[4] == "parsed"
    assert params[7] is None


class FakeStorage:
    def __init__(self):
        self.calls = []

    def upload_bytes(self, key, content, content_type, metadata=None):
        self.calls.append(
            {
                "key": key,
                "content": content,
                "content_type": content_type,
                "metadata": metadata,
            }
        )
        return StoredObject(key=key)

    def create_presigned_get_url(self, key):
        return f"local://{key}"


def test_store_uploaded_resume_returns_private_object_key(monkeypatch):
    monkeypatch.setenv("S3_PREFIX", "test-prefix")
    from services.settings import get_settings

    get_settings.cache_clear()
    storage = FakeStorage()

    key = store_uploaded_resume(
        storage=storage,
        organization_id="11111111-1111-4111-8111-111111111111",
        batch_id="22222222-2222-4222-8222-222222222222",
        file=UploadedResume("My Resume.pdf", "application/pdf", b"%PDF-1.4"),
    )

    get_settings.cache_clear()
    assert key.startswith(
        "test-prefix/organizations/11111111-1111-4111-8111-111111111111/"
    )
    assert key.endswith("-My-Resume.pdf")
    assert storage.calls[0]["content"] == b"%PDF-1.4"
    assert storage.calls[0]["metadata"]["original_file_name"] == "My Resume.pdf"
