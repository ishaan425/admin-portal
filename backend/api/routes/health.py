from __future__ import annotations

from fastapi import APIRouter, HTTPException

from schemas.api_responses import HealthResponse, ReadyResponse
from services.database import connect


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return {"status": "ok"}


@router.get("/ready", response_model=ReadyResponse)
def ready() -> ReadyResponse:
    try:
        with connect() as conn:
            conn.execute("select 1").fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is not ready.") from exc
    return {"status": "ready"}
