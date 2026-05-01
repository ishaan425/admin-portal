from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from services.clerk_webhook_service import (
    ClerkWebhookError,
    link_candidate_from_clerk_event,
    verify_clerk_webhook,
)
from services.database import connect


router = APIRouter(prefix="/webhooks")


@router.post("/clerk")
async def clerk_webhook(request: Request) -> dict:
    try:
        payload = await request.body()
        event = verify_clerk_webhook(
            payload,
            request.headers,
            request.app.state.settings.clerk_webhook_secret,
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
