"""Local FastAPI boundary for Admin Portal workflows."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.auth_service import AuthError, require_org_admin
from services.batch_status_service import get_resume_upload_batch_status
from services.bulk_candidate_upload_service import UploadedResume
from services.clerk_invite_service import ClerkInvitePipelineError
from services.clerk_webhook_service import (
    ClerkWebhookError,
    link_candidate_from_clerk_event,
    verify_clerk_webhook,
)
from services.database import connect
from services.queue_service import QueueError, queue_from_settings
from services.resume_parser import ResumeParseError
from services.resume_upload_enqueue_service import (
    create_resume_upload_batch,
    enqueue_resume_upload_batch,
)
from services.settings import AppSettings, get_settings
from services.storage_service import storage_from_settings


logger = logging.getLogger(__name__)


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="GrowQR Admin Portal API")
    app.state.settings = settings

    cors_origins = settings.cors_origin_list
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-Local-Clerk-User-Id",
                "X-Organization-Slug",
            ],
        )

    @app.middleware("http")
    async def enforce_request_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            body_size = int(content_length)
        else:
            body_size = 0
        if body_size > settings.api_max_request_body_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body is too large."},
            )
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled API error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    register_routes(app)
    return app


def register_routes(app: FastAPI) -> None:
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        try:
            with connect() as conn:
                conn.execute("select 1").fetchone()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database is not ready.") from exc
        return {"status": "ready"}

    @app.get("/admin/me")
    def admin_me(
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_local_clerk_user_id: Annotated[
            str | None, Header(alias="X-Local-Clerk-User-Id")
        ] = None,
        x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
    ) -> dict:
        try:
            with connect() as conn:
                current_member = require_org_admin(
                    conn,
                    authorization=authorization,
                    organization_slug=x_organization_slug,
                    local_clerk_user_id=x_local_clerk_user_id,
                    settings=app.state.settings,
                )
            return {
                "organization": {
                    "id": current_member.organization_id,
                    "name": current_member.organization_name,
                    "slug": current_member.organization_slug,
                    "logo_url": current_member.organization_logo_url,
                },
                "admin": {
                    "clerk_user_id": current_member.clerk_user_id,
                    "email": current_member.email,
                    "full_name": current_member.full_name,
                    "member_type": current_member.member_type,
                    "role_key": current_member.role_key,
                    "status": current_member.status,
                },
            }
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/webhooks/clerk")
    async def clerk_webhook(request: Request) -> dict:
        try:
            payload = await request.body()
            event = verify_clerk_webhook(
                payload,
                request.headers,
                app.state.settings.clerk_webhook_secret,
            )
            with connect() as conn:
                with conn.transaction():
                    result = link_candidate_from_clerk_event(conn, event)
            return {
                "status": "ok",
                "linked": result.linked,
                "reason": result.reason,
                "candidate_profile_id": result.candidate_profile_id,
            }
        except ClerkWebhookError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/admin/resumes/bulk-upload")
    async def bulk_upload_resumes(
        files: Annotated[list[UploadFile], File(description="One or more PDF resumes.")],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_local_clerk_user_id: Annotated[
            str | None, Header(alias="X-Local-Clerk-User-Id")
        ] = None,
        x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
    ) -> dict:
        try:
            uploaded_files = [
                UploadedResume(
                    file_name=file.filename or "resume.pdf",
                    content_type=file.content_type or "",
                    content=await file.read(),
                )
                for file in files
            ]

            storage = storage_from_settings(app.state.settings)
            queue = queue_from_settings(app.state.settings)
            with connect() as conn:
                with conn.transaction():
                    current_member = require_org_admin(
                        conn,
                        authorization=authorization,
                        organization_slug=x_organization_slug,
                        local_clerk_user_id=x_local_clerk_user_id,
                        settings=app.state.settings,
                    )
                    enqueue_result = create_resume_upload_batch(
                        conn=conn,
                        current_member=current_member,
                        files=uploaded_files,
                        storage=storage,
                        max_file_size_bytes=app.state.settings.resume_parse_max_file_size_bytes,
                    )
            return enqueue_resume_upload_batch(queue, enqueue_result)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ClerkInvitePipelineError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except QueueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except ResumeParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/admin/resumes/batches/{batch_id}")
    def get_bulk_resume_batch(
        batch_id: str,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        x_local_clerk_user_id: Annotated[
            str | None, Header(alias="X-Local-Clerk-User-Id")
        ] = None,
        x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
    ) -> dict:
        try:
            with connect() as conn:
                current_member = require_org_admin(
                    conn,
                    authorization=authorization,
                    organization_slug=x_organization_slug,
                    local_clerk_user_id=x_local_clerk_user_id,
                    settings=app.state.settings,
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


app = create_app()
