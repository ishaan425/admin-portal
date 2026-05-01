import pytest

from services.queue_service import LocalFileQueue, QueueError, queue_from_settings
from services.settings import AppSettings


def test_local_file_queue_sends_receives_and_deletes_message(tmp_path):
    queue = LocalFileQueue(tmp_path)

    message_id = queue.send_message({"batch_id": "batch-123"})
    messages = queue.receive_messages()

    assert messages[0].message_id == message_id
    assert messages[0].body == {"batch_id": "batch-123"}

    queue.delete_message(messages[0].receipt_handle)
    assert queue.receive_messages() == []


def test_queue_from_settings_requires_sqs_queue_url_for_sqs_backend():
    with pytest.raises(QueueError, match="SQS_RESUME_UPLOAD_QUEUE_URL"):
        queue_from_settings(AppSettings(queue_backend="sqs", sqs_resume_upload_queue_url=""))
