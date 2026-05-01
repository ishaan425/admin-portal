"""Poll the resume upload queue and process queued batches."""

from __future__ import annotations

import asyncio
import logging

from services.clerk_invite_service import clerk_invite_config_from_env
from services.database import connect
from services.queue_service import QueueClient, queue_from_settings
from services.resume_parser import config_from_env
from services.resume_upload_worker_service import (
    process_resume_upload_job,
    resume_upload_job_from_message,
)
from services.settings import get_settings
from services.storage_service import storage_from_settings


logger = logging.getLogger(__name__)


async def process_available_messages(queue: QueueClient) -> int:
    settings = get_settings()
    messages = queue.receive_messages(
        max_messages=settings.queue_receive_max_messages,
        wait_time_seconds=settings.queue_wait_time_seconds,
    )
    if not messages:
        return 0

    storage = storage_from_settings(settings)
    parser_config = config_from_env()
    clerk_config = clerk_invite_config_from_env()
    processed_count = 0

    for message in messages:
        try:
            job = resume_upload_job_from_message(message.body)
            with connect() as conn:
                conn.autocommit = True
                result = await process_resume_upload_job(
                    conn=conn,
                    job=job,
                    storage=storage,
                    parser_config=parser_config,
                    clerk_config=clerk_config,
                    parse_concurrency=settings.resume_parse_item_concurrency,
                )
            queue.delete_message(message.receipt_handle)
            processed_count += 1
            logger.info("Processed resume upload batch %s", result["batch_id"])
        except Exception:
            logger.exception("Failed to process queue message %s", message.message_id)

    return processed_count


async def run_forever() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    queue = queue_from_settings(settings)
    while True:
        processed_count = await process_available_messages(queue)
        if processed_count == 0:
            await asyncio.sleep(settings.worker_poll_interval_seconds)


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
