from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request

from schemas.job_schema import JobOpeningCreate, JobOpeningResponse, JobOpeningUpdate
from services.auth_service import AuthError, require_active_org_member
from services.database import connect
from services.job_opening_service import (
    JobOpeningError,
    JobOpeningNotFoundError,
    archive_job_opening,
    create_job_opening,
    get_job_opening,
    list_job_openings,
    publish_job_opening,
    update_job_opening,
)
from services.permission_service import PermissionError


router = APIRouter(prefix="/admin/jobs")


@router.get("", response_model=list[JobOpeningResponse])
def list_jobs(
    request: Request,
    status: Literal["draft", "published", "archived"] | None = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
) -> list[JobOpeningResponse]:
    try:
        with connect() as conn:
            current_member = require_active_org_member(
                conn,
                authorization=authorization,
                organization_slug=x_organization_slug,
                settings=request.app.state.settings,
            )
            return list_job_openings(conn, current_member, status=status)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("", response_model=JobOpeningResponse, status_code=201)
def create_job(
    payload: JobOpeningCreate,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
) -> JobOpeningResponse:
    try:
        with connect() as conn:
            with conn.transaction():
                current_member = require_active_org_member(
                    conn,
                    authorization=authorization,
                    organization_slug=x_organization_slug,
                    settings=request.app.state.settings,
                )
                return create_job_opening(conn, current_member, payload)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except JobOpeningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{job_id}", response_model=JobOpeningResponse)
def get_job(
    job_id: str,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
) -> JobOpeningResponse:
    try:
        with connect() as conn:
            current_member = require_active_org_member(
                conn,
                authorization=authorization,
                organization_slug=x_organization_slug,
                settings=request.app.state.settings,
            )
            return get_job_opening(conn, current_member, job_id)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except JobOpeningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/{job_id}", response_model=JobOpeningResponse)
def update_job(
    job_id: str,
    payload: JobOpeningUpdate,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
) -> JobOpeningResponse:
    try:
        with connect() as conn:
            with conn.transaction():
                current_member = require_active_org_member(
                    conn,
                    authorization=authorization,
                    organization_slug=x_organization_slug,
                    settings=request.app.state.settings,
                )
                return update_job_opening(conn, current_member, job_id, payload)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except JobOpeningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobOpeningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{job_id}/publish", response_model=JobOpeningResponse)
def publish_job(
    job_id: str,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
) -> JobOpeningResponse:
    try:
        with connect() as conn:
            with conn.transaction():
                current_member = require_active_org_member(
                    conn,
                    authorization=authorization,
                    organization_slug=x_organization_slug,
                    settings=request.app.state.settings,
                )
                return publish_job_opening(conn, current_member, job_id)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except JobOpeningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobOpeningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{job_id}/archive", response_model=JobOpeningResponse)
def archive_job(
    job_id: str,
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
) -> JobOpeningResponse:
    try:
        with connect() as conn:
            with conn.transaction():
                current_member = require_active_org_member(
                    conn,
                    authorization=authorization,
                    organization_slug=x_organization_slug,
                    settings=request.app.state.settings,
                )
                return archive_job_opening(conn, current_member, job_id)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except JobOpeningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
