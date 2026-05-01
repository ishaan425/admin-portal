from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request

from schemas.api_responses import AdminMeResponse
from services.auth_service import AuthError, require_org_admin
from services.database import connect


router = APIRouter(prefix="/admin")


@router.get("/me", response_model=AdminMeResponse)
def admin_me(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_organization_slug: Annotated[str | None, Header(alias="X-Organization-Slug")] = None,
) -> AdminMeResponse:
    try:
        with connect() as conn:
            current_member = require_org_admin(
                conn,
                authorization=authorization,
                organization_slug=x_organization_slug,
                settings=request.app.state.settings,
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
