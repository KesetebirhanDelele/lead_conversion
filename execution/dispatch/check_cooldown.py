"""
execution/dispatch/check_cooldown.py

Cooldown guard: returns True when a lead has already been dispatched for a
given event_type within the cooldown window.

Destination key format: "CORA:<EVENT_TYPE>"  (e.g. "CORA:SEND_INVITE")

A record counts toward the cooldown when its status is SENT or SHADOW —
both represent a successfully dispatched (or shadow-logged) action.
FAILED and NEEDS_SYNC records are ignored so they can always be retried.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from execution.db.sqlite import connect, init_db

_QUALIFYING_STATUSES = ("SENT", "SHADOW")

_SQL = """
    SELECT updated_at
    FROM   sync_records
    WHERE  lead_id    = ?
      AND  destination = ?
      AND  status IN ('SENT', 'SHADOW')
    ORDER  BY updated_at DESC
    LIMIT  1
"""


def cora_destination(event_type: str) -> str:
    return f"CORA:{event_type}"


def is_on_cooldown(
    lead_id: str,
    event_type: str,
    *,
    cooldown_hours: int = 24,
    now: datetime,
    db_path: str | None = None,
) -> bool:
    """Return True when lead_id has been dispatched for event_type within cooldown_hours.

    Args:
        lead_id:        Lead to check.
        event_type:     Cora event type string (e.g. "SEND_INVITE").
        cooldown_hours: Hours after last dispatch before the lead is eligible again.
        now:            Reference UTC datetime — must be supplied by the caller.
        db_path:        SQLite path; defaults to tmp/app.db.
    """
    destination = cora_destination(event_type)
    conn = connect(db_path)
    try:
        init_db(conn)
        row = conn.execute(_SQL, (lead_id, destination)).fetchone()
    finally:
        conn.close()

    if row is None:
        return False

    try:
        last_at = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False

    now_utc = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return (now_utc - last_at) < timedelta(hours=cooldown_hours)
