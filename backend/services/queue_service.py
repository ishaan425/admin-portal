"""Queue boundary for async resume upload processing."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from services.settings import AppSettings, get_settings


class QueueError(RuntimeError):
    pass


@dataclass(frozen=True)
class QueueMessage:
    message_id: str
    receipt_handle: str
    body: dict[str, Any]


class QueueClient(Protocol):
    def send_message(self, body: dict[str, Any]) -> str:
        ...

    def receive_messages(self, max_messages: int = 1, wait_time_seconds: int = 0) -> list[QueueMessage]:
        ...

    def delete_message(self, receipt_handle: str) -> None:
        ...


class LocalFileQueue:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def send_message(self, body: dict[str, Any]) -> str:
        message_id = uuid.uuid4().hex
        path = self.root / f"{message_id}.json"
        path.write_text(
            json.dumps({"message_id": message_id, "body": body}, sort_keys=True),
            encoding="utf-8",
        )
        return message_id

    def receive_messages(self, max_messages: int = 1, wait_time_seconds: int = 0) -> list[QueueMessage]:
        messages: list[QueueMessage] = []
        for path in sorted(self.root.glob("*.json"))[:max(1, max_messages)]:
            payload = json.loads(path.read_text(encoding="utf-8"))
            message_id = str(payload["message_id"])
            messages.append(
                QueueMessage(
                    message_id=message_id,
                    receipt_handle=str(path),
                    body=payload["body"],
                )
            )
        return messages

    def delete_message(self, receipt_handle: str) -> None:
        path = Path(receipt_handle)
        if path.exists():
            path.unlink()


class SQSQueue:
    def __init__(self, queue_url: str, region: str = ""):
        if not queue_url:
            raise QueueError("SQS_RESUME_UPLOAD_QUEUE_URL is required when QUEUE_BACKEND=sqs.")
        self.queue_url = queue_url
        self.client = boto3.client("sqs", region_name=region or None)

    def send_message(self, body: dict[str, Any]) -> str:
        try:
            response = self.client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(body, sort_keys=True),
            )
        except (BotoCoreError, ClientError) as exc:
            raise QueueError(f"Could not send SQS message: {exc}") from exc
        return str(response.get("MessageId") or "")

    def receive_messages(self, max_messages: int = 1, wait_time_seconds: int = 0) -> list[QueueMessage]:
        try:
            response = self.client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=min(max(1, max_messages), 10),
                WaitTimeSeconds=max(0, min(wait_time_seconds, 20)),
            )
        except (BotoCoreError, ClientError) as exc:
            raise QueueError(f"Could not receive SQS messages: {exc}") from exc

        messages: list[QueueMessage] = []
        for raw_message in response.get("Messages", []):
            try:
                body = json.loads(raw_message.get("Body") or "{}")
            except json.JSONDecodeError as exc:
                raise QueueError("SQS message body must be valid JSON.") from exc
            messages.append(
                QueueMessage(
                    message_id=str(raw_message.get("MessageId") or ""),
                    receipt_handle=str(raw_message.get("ReceiptHandle") or ""),
                    body=body,
                )
            )
        return messages

    def delete_message(self, receipt_handle: str) -> None:
        try:
            self.client.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle,
            )
        except (BotoCoreError, ClientError) as exc:
            raise QueueError(f"Could not delete SQS message: {exc}") from exc


def queue_from_settings(settings: AppSettings | None = None) -> QueueClient:
    settings = settings or get_settings()
    backend = settings.queue_backend.strip().lower()
    if backend == "local":
        return LocalFileQueue(settings.local_queue_root)
    if backend == "sqs":
        return SQSQueue(
            queue_url=settings.sqs_resume_upload_queue_url,
            region=settings.sqs_region,
        )
    raise QueueError("QUEUE_BACKEND must be either 'local' or 'sqs'.")
