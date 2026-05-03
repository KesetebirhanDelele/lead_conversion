from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from execution.leads.get_lead_status import get_lead_status
from execution.leads.upsert_lead import upsert_lead
from execution.progress.compute_course_state import compute_course_state
from execution.progress.record_progress_event import record_progress_event

app = FastAPI()


class LeadStatusRequest(BaseModel):
    lead_id: str


class CourseStateOut(BaseModel):
    current_section: str | None
    completion_pct: float | None


class LeadStatusResponse(BaseModel):
    lead_exists: bool
    course_state: CourseStateOut


class ProgressUpdateRequest(BaseModel):
    lead_id: str
    section: str


class ProgressUpdateResponse(BaseModel):
    event_id: str
    course_state: CourseStateOut


@app.post("/api/lead/status", response_model=LeadStatusResponse)
def lead_status(req: LeadStatusRequest) -> LeadStatusResponse:
    status = get_lead_status(req.lead_id)
    return LeadStatusResponse(
        lead_exists=status["lead_exists"],
        course_state=CourseStateOut(
            current_section=status["course_state"]["current_section"],
            completion_pct=status["course_state"]["completion_pct"],
        ),
    )


@app.post("/api/progress/update", response_model=ProgressUpdateResponse)
def progress_update(req: ProgressUpdateRequest) -> ProgressUpdateResponse:
    event_id = f"{req.lead_id}:{req.section}"
    occurred_at = datetime.now(timezone.utc).isoformat()

    upsert_lead(req.lead_id)

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
        course_state=CourseStateOut(
            current_section=status["course_state"]["current_section"],
            completion_pct=status["course_state"]["completion_pct"],
        ),
    )
