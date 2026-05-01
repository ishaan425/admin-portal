import asyncio

import pytest

from services.resume_upload_contracts import RESUME_UPLOAD_JOB_TYPE, ResumeUploadJob
from services import resume_upload_worker_service
from services.resume_upload_worker_service import (
    ResumeUploadWorkerError,
    get_resume_upload_batch_state,
    get_pending_resume_parse_items,
    process_resume_upload_job,
    process_pending_resume_parse_items,
    resume_upload_job_from_message,
)


class FakeResult:
    def __init__(self, rows=None):
        self.rows = rows or []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return FakeResult(self.rows)


class SequencedConn:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return FakeResult([self.results.pop(0)])


def test_resume_upload_job_from_message_validates_job_type():
    with pytest.raises(ResumeUploadWorkerError, match="Unsupported"):
        resume_upload_job_from_message({"job_type": "other"})


def test_resume_upload_job_from_message_returns_job_contract():
    job = resume_upload_job_from_message(
        {
            "job_type": RESUME_UPLOAD_JOB_TYPE,
            "batch_id": "batch-123",
            "organization_id": "org-123",
            "uploaded_by_clerk_user_id": "admin-123",
        }
    )

    assert job.batch_id == "batch-123"
    assert job.organization_id == "org-123"
    assert job.uploaded_by_clerk_user_id == "admin-123"


def test_get_pending_resume_parse_items_reads_pending_and_failed_items():
    conn = FakeConn([("item-123", "Resume.pdf", "key-123")])

    items = get_pending_resume_parse_items(conn, "org-123", "batch-123")

    assert items == [
        {
            "id": "item-123",
            "original_file_name": "Resume.pdf",
            "resume_file_key": "key-123",
        }
    ]
    assert "parse_status in ('pending', 'failed')" in conn.calls[0][0]


def test_get_resume_upload_batch_state_reads_terminal_counts():
    conn = FakeConn([("completed", 3, 1)])

    state = get_resume_upload_batch_state(conn, "org-123", "batch-123")

    assert state == {"status": "completed", "parsed_count": 3, "failed_count": 1}


def test_process_resume_upload_job_skips_completed_batch():
    admin_row = (
        "org-123",
        "Amity",
        "amity",
        "",
        "admin-123",
        "admin@example.com",
        "Admin",
        "admin",
        "org_admin",
        "active",
    )
    conn = SequencedConn([admin_row, ("completed", 2, 0)])

    result = asyncio.run(
        process_resume_upload_job(
            conn=conn,
            job=ResumeUploadJob(
                batch_id="batch-123",
                organization_id="org-123",
                uploaded_by_clerk_user_id="admin-123",
            ),
            storage=object(),
            parser_config=object(),
            clerk_config=object(),
        )
    )

    assert result["status"] == "completed"
    assert result["parsed_count"] == 2
    assert result["items"] == []
    assert not any("update resume_parse_batches" in query for query, _params in conn.calls)


def test_process_pending_resume_parse_items_limits_openai_parse_concurrency(monkeypatch):
    active_count = 0
    max_active_count = 0

    async def fake_parse_resume(pdf_bytes, config, source_name):
        nonlocal active_count, max_active_count
        active_count += 1
        max_active_count = max(max_active_count, active_count)
        await asyncio.sleep(0.01)
        active_count -= 1
        return {
            "personal_info": {
                "email": f"{source_name}@example.com",
                "full_name": source_name,
            }
        }

    class FakeStorage:
        def download_bytes(self, key):
            return b"%PDF-1.4"

    items = [
        {
            "id": f"item-{index}",
            "original_file_name": f"resume-{index}",
            "resume_file_key": f"key-{index}",
        }
        for index in range(5)
    ]
    conn = FakeConn([])
    monkeypatch.setattr(resume_upload_worker_service, "parse_resume", fake_parse_resume)

    results = asyncio.run(
        process_pending_resume_parse_items(
            conn=conn,
            items=items,
            storage=FakeStorage(),
            parser_config=object(),
            concurrency=2,
        )
    )

    assert max_active_count == 2
    assert [item["status"] for item in results] == ["parsed"] * 5
    assert len(conn.calls) == 10
