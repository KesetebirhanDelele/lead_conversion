from __future__ import annotations

from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from execution.leads.get_lead_status import get_lead_status
from execution.leads.mark_course_invite_sent import mark_course_invite_sent
from execution.leads.upsert_lead import upsert_lead
from execution.progress.compute_course_state import compute_course_state
from execution.progress.record_progress_event import record_progress_event

load_dotenv()

app = FastAPI()


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


@app.post("/api/lead/status", response_model=LeadStatusResponse)
def lead_status(req: LeadStatusRequest) -> LeadStatusResponse:
    status = get_lead_status(req.lead_id)
    return LeadStatusResponse(
        lead_exists=status["lead_exists"],
        course_state=_build_course_state(status),
        hot_lead=_build_hot_lead(status),
    )


@app.post("/api/progress/update", response_model=ProgressUpdateResponse)
def progress_update(req: ProgressUpdateRequest) -> ProgressUpdateResponse:
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
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    compute_course_state(req.lead_id)

    status = get_lead_status(req.lead_id)
    return ProgressUpdateResponse(
        event_id=event_id,
        course_state=_build_course_state(status),
        hot_lead=_build_hot_lead(status),
    )
