from services.auth_service import CurrentOrgMember
from services.bulk_candidate_upload_service import UploadedResume
from services.queue_service import LocalFileQueue
from services.resume_upload_enqueue_service import (
    RESUME_UPLOAD_JOB_TYPE,
    create_resume_upload_batch,
    enqueue_resume_upload_batch,
)
from services.storage_service import StoredObject


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self):
        self.calls = []
        self.next_ids = iter(
            [
                ("batch-123",),
                ("item-123",),
            ]
        )

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return FakeResult(next(self.next_ids))


class FakeStorage:
    def upload_bytes(self, key, content, content_type, metadata=None):
        return StoredObject(key=key)

    def create_presigned_get_url(self, key):
        return f"local://{key}"

    def download_bytes(self, key):
        return b"%PDF-1.4"


def current_member():
    return CurrentOrgMember(
        organization_id="org-123",
        organization_name="Amity",
        organization_slug="amity",
        organization_logo_url="https://example.com/logo.png",
        clerk_user_id="admin-123",
        email="admin@example.com",
        full_name="Admin",
        member_type="admin",
        role_key="org_admin",
        status="active",
    )


def test_create_resume_upload_batch_creates_pending_rows():
    conn = FakeConn()

    result = create_resume_upload_batch(
        conn=conn,
        current_member=current_member(),
        files=[UploadedResume("Resume.pdf", "application/pdf", b"%PDF-1.4")],
        storage=FakeStorage(),
        max_file_size_bytes=100,
    )

    assert result["status"] == "pending"
    assert result["batch_id"] == "batch-123"
    assert result["queue_payload"]["job_type"] == RESUME_UPLOAD_JOB_TYPE
    assert result["queue_payload"]["batch_id"] == "batch-123"
    assert conn.calls[0][1][2] == "pending"
    assert conn.calls[1][1][4] == "pending"


def test_enqueue_resume_upload_batch_sends_queue_message(tmp_path):
    queue = LocalFileQueue(tmp_path)
    enqueue_result = {
        "batch_id": "batch-123",
        "status": "pending",
        "queue_payload": {"job_type": RESUME_UPLOAD_JOB_TYPE, "batch_id": "batch-123"},
    }

    result = enqueue_resume_upload_batch(queue, enqueue_result)

    assert result["status"] == "queued"
    assert result["queue_message_id"]
    assert "queue_payload" not in result
    assert queue.receive_messages()[0].body["batch_id"] == "batch-123"
