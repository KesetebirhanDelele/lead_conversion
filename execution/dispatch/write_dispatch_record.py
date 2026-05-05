"""
execution/dispatch/write_dispatch_record.py

Writes a SHADOW dispatch record to sync_records for a Cora recommendation.

Shadow mode: the payload is logged to sync_records with status='SHADOW' so
the full dispatch cycle is exercised and auditable — without sending any
real outbound request. When Cory or GHL endpoints are live, status becomes
'SENT' and this module is updated in place.

Upsert strategy: if a SHADOW record already exists for (lead_id, destination),
its payload and updated_at are refreshed. The UNIQUE constraint on
(lead_id, destination, status) means each lead has at most one pending SHADOW
record per destination at a time.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from execution.db.sqlite import connect, init_db
from execution.dispatch.check_cooldown import cora_destination

_SQL_UPSERT = """
    INSERT INTO sync_records (lead_id, destination, status, payload_json, created_at, updated_at)
    VALUES (?, ?, 'SHADOW', ?, ?, ?)
    ON CONFLICT(lead_id, destination, status) DO UPDATE SET
        payload_json = excluded.payload_json,
        updated_at   = excluded.updated_at
"""


def write_shadow_record(
    lead_id: str,
    event_type: str,
    recommendation: dict,
    *,
    now: datetime | None = None,
    db_path: str | None = None,
) -> None:
    """Upsert a SHADOW sync record for a Cora recommendation.

    Args:
        lead_id:        Lead the record belongs to.
        event_type:     Cora event type (e.g. "SEND_INVITE").
        recommendation: Full dict from get_cora_recommendation / build_cora_recommendation.
        now:            Timestamp for created_at / updated_at; defaults to UTC now.
        db_path:        SQLite path; defaults to tmp/app.db.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    ts = now.isoformat()
    destination = cora_destination(event_type)
    payload_json = json.dumps(recommendation, default=str)

    conn = connect(db_path)
    try:
        init_db(conn)
        conn.execute(_SQL_UPSERT, (lead_id, destination, payload_json, ts, ts))
        conn.commit()
    finally:
        conn.close()
