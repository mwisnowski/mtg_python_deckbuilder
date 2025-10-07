from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Any, Dict

from ..services.telemetry import log_frontend_event

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


class TelemetryEvent(BaseModel):
    event: str = Field(..., min_length=1)
    data: Dict[str, Any] | None = None


@router.post("/events", status_code=204)
async def ingest_event(payload: TelemetryEvent, request: Request) -> Response:
    log_frontend_event(request, event=payload.event, data=payload.data or {})
    return Response(status_code=204)
