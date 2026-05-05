from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from execution.leads.get_lead_status import get_lead_status
from execution.leads.mark_course_invite_sent import mark_course_invite_sent
from execution.leads.upsert_lead import upsert_lead
from execution.progress.compute_course_state import compute_course_state
from execution.progress.record_progress_event import record_progress_event

from backend.auth import require_api_key
from backend.rate_limit import (
    check_rate_limit,
    ip_key,
    lead_id_key,
    _limit,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("api")

app = FastAPI(title="Lead Conversion API", version="2.0.0")


# ---------------------------------------------------------------------------
# Middleware — request logging
# ---------------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000)
    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        "%s %s %s %dms ip=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        client_ip,
    )
    return response


# ---------------------------------------------------------------------------
# Standardized error helper
# ---------------------------------------------------------------------------

def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


# ---------------------------------------------------------------------------
# Rate-limit dependency — per lead_id then per IP
# ---------------------------------------------------------------------------

async def _check_lead_rate(request: Request, lead_id: str) -> None:
    allowed, _ = check_rate_limit(lead_id_key(lead_id), _limit("RATE_LIMIT_LEAD"))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "RATE_LIMITED_LEAD", "message": f"Too many requests for lead {lead_id}."}},
        )


async def _check_ip_rate(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    allowed, _ = check_rate_limit(ip_key(ip), _limit("RATE_LIMIT_IP"))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "RATE_LIMITED_IP", "message": "Too many requests from this IP."}},
        )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class LeadStatusRequest(BaseModel):
    lead_id: str


class CourseStateOut(BaseModel):
    current_section: str | None
    completion_pct: float | None
    last_activity_at: str | None
    lead_signal: str | None


class HotLeadOut(BaseModel):
    signal: str | None
    score: float | None
    reason: str | None


class LeadStatusResponse(BaseModel):
    lead_exists: bool
    course_state: CourseStateOut
    hot_lead: HotLeadOut


class ProgressUpdateRequest(BaseModel):
    lead_id: str
    section: str


class ProgressUpdateResponse(BaseModel):
    event_id: str
    course_state: CourseStateOut
    hot_lead: HotLeadOut


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _build_course_state(status: dict) -> CourseStateOut:
    return CourseStateOut(
        current_section=status["course_state"]["current_section"],
        completion_pct=status["course_state"]["completion_pct"],
        last_activity_at=status["course_state"]["last_activity_at"],
        lead_signal=status["hot_lead"]["signal"],
    )


def _build_hot_lead(status: dict) -> HotLeadOut:
    return HotLeadOut(
        signal=status["hot_lead"]["signal"],
        score=status["hot_lead"]["score"],
        reason=status["hot_lead"]["reason"],
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Public health check — no auth required."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/lead/status", response_model=LeadStatusResponse)
async def lead_status(
    req: LeadStatusRequest,
    request: Request,
    _token: Annotated[str, Depends(require_api_key)],
) -> LeadStatusResponse:
    await _check_ip_rate(request)
    await _check_lead_rate(request, req.lead_id)

    status = get_lead_status(req.lead_id)
    return LeadStatusResponse(
        lead_exists=status["lead_exists"],
        course_state=_build_course_state(status),
        hot_lead=_build_hot_lead(status),
    )


@app.post("/api/progress/update", response_model=ProgressUpdateResponse)
async def progress_update(
    req: ProgressUpdateRequest,
    request: Request,
    _token: Annotated[str, Depends(require_api_key)],
) -> ProgressUpdateResponse:
    await _check_ip_rate(request)
    await _check_lead_rate(request, req.lead_id)

    event_id = f"{req.lead_id}:{req.section}"
    occurred_at = datetime.now(timezone.utc).isoformat()

    upsert_lead(req.lead_id)

    # Mark the lead as "invited via GPT" so the HOT signal invite gate passes.
    # invite_id is deterministic — repeated calls are silent no-ops.
    mark_course_invite_sent(
        invite_id=f"GPT_{req.lead_id}",
        lead_id=req.lead_id,
        channel="gpt",
        sent_at=occurred_at,
    )

    try:
        record_progress_event(
            event_id=event_id,
            lead_id=req.lead_id,
            section=req.section,
            occurred_at=occurred_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "DUPLICATE_EVENT", "message": str(exc)}},
        ) from exc

    compute_course_state(req.lead_id)

    status = get_lead_status(req.lead_id)
    return ProgressUpdateResponse(
        event_id=event_id,
        course_state=_build_course_state(status),
        hot_lead=_build_hot_lead(status),
    )
