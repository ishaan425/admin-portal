from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile

from schemas.api_responses import ResumeUploadBatchResponse, ResumeUploadEnqueueResponse
from services.auth_service import AuthError, require_org_admin
from services.batch_status_service import get_resume_upload_batch_status
from services.database import connect
from services.queue_service import QueueError, queue_from_settings
from services.resume_parser import ResumeParseError
from services.resume_upload_contracts import UploadedResume
from services.resume_upload_enqueue_service import (
    create_resume_upload_batch,
    enqueue_resume_upload_batch,
)
from services.storage_service import storage_from_settings


router = APIRouter(prefix="/admin/resumes")


@router.post("/bulk-upload", response_model=ResumeUploadEnqueueResponse)
async def bulk_upload_resumes(
    request: Request,
    files: Annotated[list[UploadFile], File(description="One or more PDF resumes.")],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
) -> ResumeUploadEnqueueResponse:
    try:
        uploaded_files = [
            UploadedResume(
                file_name=file.filename or "resume.pdf",
                content_type=file.content_type or "",
                content=await file.read(),
            )
            for file in files
        ]

        settings = request.app.state.settings
        storage = storage_from_settings(settings)
        queue = queue_from_settings(settings)
        with connect() as conn:
            with conn.transaction():
                current_member = require_org_admin(
                    conn,
                    authorization=authorization,
                    organization_slug=x_organization_slug,
                    settings=settings,
                )
                enqueue_result = create_resume_upload_batch(
                    conn=conn,
                    current_member=current_member,
                    files=uploaded_files,
                    storage=storage,
                    max_file_size_bytes=settings.resume_parse_max_file_size_bytes,
                )
        return enqueue_resume_upload_batch(queue, enqueue_result)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except QueueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ResumeParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/batches/{batch_id}", response_model=ResumeUploadBatchResponse)
def get_bulk_resume_batch(
    request: Request,
    batch_id: str,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
) -> ResumeUploadBatchResponse:
    try:
        with connect() as conn:
            current_member = require_org_admin(
                conn,
                authorization=authorization,
                organization_slug=x_organization_slug,
                settings=request.app.state.settings,
            )
            result = get_resume_upload_batch_status(
                conn,
                organization_id=current_member.organization_id,
                batch_id=batch_id,
            )
        if not result:
            raise HTTPException(status_code=404, detail="Batch was not found.")
        return result
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
