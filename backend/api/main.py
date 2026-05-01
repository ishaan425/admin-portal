"""Local FastAPI boundary for Admin Portal workflows."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes.admin import router as admin_router
from api.routes.health import router as health_router
from api.routes.resumes import router as resumes_router
from api.routes.webhooks import router as webhooks_router
from services.settings import AppSettings, get_settings


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

    app.include_router(health_router)
    app.include_router(admin_router)
    app.include_router(resumes_router)
    app.include_router(webhooks_router)
    return app


app = create_app()
