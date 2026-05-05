"""
execution/ghl/write_ghl_contact_fields.py

Step 4 of the GHL handshake flow (directives/GHL_INTEGRATION.md):

    … → [Step 3 complete] → [Step 4 — this function] → GHL → Step 5 …

Responsibility: build the full canonical GHL custom-field payload for one lead
(via build_ghl_full_field_payload) and POST it to the configured GHL contact-
update endpoint.  No business logic lives here — only payload construction,
contact-ID resolution, and HTTP transport.

GHL contact resolution
----------------------
1. Preferred path — stored ghl_contact_id on the leads row (already embedded in
   the built payload, so no extra DB read is needed).
2. Fallback path — if ghl_contact_id is absent AND a ghl_lookup_url is provided,
   sync_ghl_contact_id is called to resolve and store it before sending.
3. If neither path yields a ghl_contact_id, no HTTP request is made and the
   function returns ok=False.

Safe no-op
----------
When ghl_api_url is None or blank the function returns ok=True, sent=False with
reason="NO_URL".  This mirrors the pattern in dispatch_cory_ghl so callers can
wire configuration gradually without breaking tests or dev environments.

Return shape
------------
    {
        "ok":             bool,
        "app_lead_id":    str,
        "ghl_contact_id": str | None,
        "sent":           bool,
        "status_code":    int | None,
        "message":        str,
    }
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime

from execution.db.sqlite import connect, init_db
from execution.ghl.build_ghl_full_field_payload import build_ghl_full_field_payload
from execution.ghl.build_m4_field_payload import build_m4_field_payload
from execution.ghl.lookup_ghl_contact_by_phone import lookup_ghl_contact_by_phone
from execution.leads.mark_sync_record_failed import mark_sync_record_failed
from execution.leads.mark_sync_record_sent import mark_sync_record_sent
from execution.leads.sync_ghl_contact_id import sync_ghl_contact_id

_CONTENT_TYPE          = "application/json"
_DESTINATION_WRITEBACK = "GHL_WRITEBACK"
_STATUS_NEEDS_SYNC     = "NEEDS_SYNC"
_STATUS_FAILED         = "FAILED"
_STATUS_SHADOW         = "SHADOW"


def _persist_early_exit_failed(app_lead_id: str, error: str, now: str, db_path) -> None:
    """Write a FAILED sync_records row for an early-exit writeback failure.

    Uses the same DELETE-before-INSERT pattern as the NEEDS_SYNC step so
    any prior row (NEEDS_SYNC, SENT, or FAILED) is replaced cleanly.
    Called only for the two cases where a real writeback was intended but
    could not proceed: missing ghl_contact_id and missing GHL_API_KEY.
    """
    _c = connect(db_path)
    try:
        init_db(_c)
        _c.execute(
            "DELETE FROM sync_records WHERE lead_id = ? AND destination = ?",
            (app_lead_id, _DESTINATION_WRITEBACK),
        )
        _c.execute(
            """
            INSERT INTO sync_records
                (lead_id, destination, status, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (app_lead_id, _DESTINATION_WRITEBACK, _STATUS_FAILED, error, now, now),
        )
        _c.commit()
    finally:
        _c.close()


def _write_shadow_ghl_record(
    app_lead_id: str,
    payload: dict,
    now: str,
    db_path,
) -> None:
    """Upsert a SHADOW sync_records row for a GHL writeback in shadow mode.

    Uses INSERT … ON CONFLICT DO UPDATE so repeated shadow runs don't
    accumulate duplicate rows — only payload_json and updated_at change.
    """
    payload_json = json.dumps(payload)
    _c = connect(db_path)
    try:
        init_db(_c)
        _c.execute(
            """
            INSERT INTO sync_records
                (lead_id, destination, status, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(lead_id, destination, status) DO UPDATE SET
                payload_json = excluded.payload_json,
                updated_at   = excluded.updated_at
            """,
            (app_lead_id, _DESTINATION_WRITEBACK, _STATUS_SHADOW, payload_json, now, now),
        )
        _c.commit()
    finally:
        _c.close()


def write_ghl_contact_fields(
    app_lead_id: str,
    *,
    now: str,
    ghl_api_url: str | None = None,
    ghl_lookup_url: str | None = None,
    base_url: str = "http://localhost:8501",
    db_path: str | None = None,
    timeout: int = 10,
) -> dict:
    """Build and POST the full canonical GHL field payload for one lead.

    This is Step 4 of the GHL handshake.  It must be called after Step 3
    (process_ghl_lead_intake) has completed and the course link is stored.

    Args:
        app_lead_id:    Internal lead identifier.
        now:            ISO-8601 UTC string for all time-dependent derivations.
                        Must be provided by the caller — this function never
                        calls datetime.now() internally.  Raises ValueError
                        when None.
        ghl_api_url:    URL of the GHL contact-update endpoint.  When None or
                        blank the function returns a safe no-op (sent=False,
                        ok=True) without making any network call.
        ghl_lookup_url: URL of the GHL contact-lookup endpoint used by
                        sync_ghl_contact_id when ghl_contact_id is not yet
                        stored on the lead.  Optional.
        base_url:       Base URL of the student portal, forwarded to
                        build_ghl_full_field_payload for course_link
                        construction.  Defaults to http://localhost:8501.
        db_path:        Path to the SQLite file; defaults to tmp/app.db.
        timeout:        Socket timeout in seconds for the outbound HTTP request.
                        Defaults to 10.

    Returns:
        dict — see module docstring for the return shape.
    """
    # ------------------------------------------------------------------
    # 0. Determinism guard.
    # ------------------------------------------------------------------
    if now is None:
        raise ValueError(
            "write_ghl_contact_fields: 'now' must be provided by the caller. "
            "Do not call datetime.now() inside execution functions."
        )

    # ------------------------------------------------------------------
    # 1. Build the full canonical payload.
    #    This reads all required DB rows and derives all field values.
    # ------------------------------------------------------------------
    build_result = build_ghl_full_field_payload(
        app_lead_id,
        now=now,
        base_url=base_url,
        db_path=db_path,
    )

    if not build_result["ok"]:
        return {
            "ok":             False,
            "app_lead_id":    app_lead_id,
            "ghl_contact_id": None,
            "sent":           False,
            "status_code":    None,
            "message":        build_result["message"],
        }

    field_payload = build_result["payload"]

    # ------------------------------------------------------------------
    # 2. Shadow mode — when GHL_SHADOW_MODE is set, log the M4 payload
    #    to sync_records and return without making any outbound HTTP call.
    # ------------------------------------------------------------------
    _shadow_env = os.environ.get("GHL_SHADOW_MODE", "").strip().lower()
    if _shadow_env in ("1", "true", "yes"):
        m4_payload = build_m4_field_payload(field_payload)
        _write_shadow_ghl_record(app_lead_id, m4_payload, now, db_path)
        return {
            "ok":             True,
            "app_lead_id":    app_lead_id,
            "ghl_contact_id": field_payload.get("ghl_contact_id"),
            "sent":           False,
            "shadow":         True,
            "status_code":    None,
            "message":        "GHL_SHADOW_MODE active — payload logged, HTTP POST skipped.",
        }

    # ------------------------------------------------------------------
    # 3. Guard: block send when course_link has not been generated yet.
    #
    #    invite_ready is derived from course_link in build_ghl_full_field_payload
    #    (invite_ready = course_link is not None).  Sending to GHL before a
    #    course_link exists would write invite_ready=False with a null link —
    #    correct per the schema but premature: the directive requires the full
    #    handshake (link generated → writeback → GHL sends) to complete in order.
    #    Blocking here enforces that constraint at the transport boundary.
    # ------------------------------------------------------------------
    if not field_payload.get("course_link"):
        return {
            "ok":             False,
            "app_lead_id":    app_lead_id,
            "ghl_contact_id": None,
            "sent":           False,
            "status_code":    None,
            "message":        "Writeback blocked: course_link not yet generated for this lead.",
        }

    # ------------------------------------------------------------------
    # 4. Resolve ghl_contact_id — phone-first.
    #
    #    Primary:   look up via phone number using lookup_ghl_contact_by_phone
    #               when GHL_API_KEY and GHL_LOCATION_ID are available.
    #    Secondary: use the stored ghl_contact_id from the leads row.
    #    Tertiary:  call sync_ghl_contact_id when a legacy ghl_lookup_url
    #               is configured.
    # ------------------------------------------------------------------
    ghl_contact_id: str | None = None

    _phone       = (field_payload.get("phone") or "").strip() or None
    _api_key_env = os.environ.get("GHL_API_KEY", "").strip() or None
    _location_id = os.environ.get("GHL_LOCATION_ID", "").strip() or None
    _base_url    = os.environ.get("GHL_API_BASE_URL", "https://services.leadconnectorhq.com").strip()

    if _phone and _api_key_env and _location_id:
        try:
            phone_result = lookup_ghl_contact_by_phone(
                _phone,
                api_key=_api_key_env,
                location_id=_location_id,
                base_url=_base_url,
                timeout=timeout,
            )
            if phone_result.get("ok") and phone_result.get("contact_id"):
                ghl_contact_id = phone_result["contact_id"]
        except Exception:
            pass  # phone lookup failure is non-fatal; fall through to stored ID

    if ghl_contact_id is None:
        ghl_contact_id = (field_payload.get("ghl_contact_id") or "").strip() or None

    if ghl_contact_id is None and ghl_lookup_url:
        sync_result = sync_ghl_contact_id(
            app_lead_id,
            db_path=db_path,
            ghl_lookup_url=ghl_lookup_url,
            timeout=timeout,
        )
        if sync_result.get("ok") and sync_result.get("updated"):
            ghl_contact_id = sync_result.get("ghl_contact_id") or None

    if ghl_contact_id is None:
        _persist_early_exit_failed(
            app_lead_id,
            "No ghl_contact_id resolved — cannot identify GHL contact endpoint.",
            now,
            db_path,
        )
        return {
            "ok":             False,
            "app_lead_id":    app_lead_id,
            "ghl_contact_id": None,
            "sent":           False,
            "status_code":    None,
            "message":        (
                "No ghl_contact_id available for this lead. "
                "Ensure the lead has a phone number and GHL_LOCATION_ID is set, "
                "or provide a ghl_lookup_url for legacy ID resolution."
            ),
        }

    # ------------------------------------------------------------------
    # 5. Safe no-op when no API URL is configured.
    # ------------------------------------------------------------------
    if not ghl_api_url or not str(ghl_api_url).strip():
        return {
            "ok":             True,
            "app_lead_id":    app_lead_id,
            "ghl_contact_id": ghl_contact_id,
            "sent":           False,
            "status_code":    None,
            "message":        "No ghl_api_url configured — payload built but not sent.",
        }

    # ------------------------------------------------------------------
    # 6. Resolve GHL API key — fail explicitly if absent.
    #
    #    The key must be supplied at runtime via the GHL_API_KEY environment
    #    variable.  It must never be hardcoded.  If it is missing, we return
    #    an error rather than silently sending an unauthenticated request.
    # ------------------------------------------------------------------
    api_key = os.environ.get("GHL_API_KEY")
    if not api_key:
        _persist_early_exit_failed(
            app_lead_id,
            "GHL_API_KEY environment variable is not set — request not sent.",
            now,
            db_path,
        )
        return {
            "ok":             False,
            "app_lead_id":    app_lead_id,
            "ghl_contact_id": ghl_contact_id,
            "sent":           False,
            "status_code":    None,
            "message":        "GHL_API_KEY environment variable is not set.",
        }

    # ------------------------------------------------------------------
    # 7. Write NEEDS_SYNC outbox record before the HTTP attempt.
    #
    #    DELETE all prior rows for (app_lead_id, GHL_WRITEBACK) first so
    #    that mark_sync_record_failed — which has no record_id targeted path
    #    and returns {changed: False} when a FAILED row already exists —
    #    always finds a clean slate.  This makes retries safe.
    # ------------------------------------------------------------------
    now_dt = datetime.fromisoformat(now)
    _conn = connect(db_path)
    try:
        init_db(_conn)
        _conn.execute(
            "DELETE FROM sync_records WHERE lead_id = ? AND destination = ?",
            (app_lead_id, _DESTINATION_WRITEBACK),
        )
        _conn.execute(
            """
            INSERT INTO sync_records
                (lead_id, destination, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (app_lead_id, _DESTINATION_WRITEBACK, _STATUS_NEEDS_SYNC, now, now),
        )
        _conn.commit()
        _sync_record_id = _conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]
    finally:
        _conn.close()

    # ------------------------------------------------------------------
    # 8. POST the canonical payload to GHL.
    #
    #    The body wraps the field payload with the target ghl_contact_id so
    #    the receiving endpoint always has full context in a single request.
    # ------------------------------------------------------------------
    outbound = {
        "ghl_contact_id": ghl_contact_id,
        "fields":         field_payload,
        "sent_at":        now,
    }

    body = json.dumps(outbound).encode("utf-8")
    req = urllib.request.Request(
        url=str(ghl_api_url).strip(),
        data=body,
        headers={
            "Authorization":  f"Bearer {api_key}",
            "Content-Type":   _CONTENT_TYPE,
            "Content-Length": str(len(body)),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            mark_sync_record_sent(
                app_lead_id,
                now_dt,
                destination=_DESTINATION_WRITEBACK,
                db_path=db_path,
                record_id=_sync_record_id,
            )
            return {
                "ok":             True,
                "app_lead_id":    app_lead_id,
                "ghl_contact_id": ghl_contact_id,
                "sent":           True,
                "status_code":    resp.status,
                "message":        "GHL contact fields updated successfully.",
            }

    except urllib.error.HTTPError as exc:
        mark_sync_record_failed(
            app_lead_id,
            now_dt,
            destination=_DESTINATION_WRITEBACK,
            error=f"HTTP {exc.code}: {exc.reason}",
            db_path=db_path,
        )
        return {
            "ok":             False,
            "app_lead_id":    app_lead_id,
            "ghl_contact_id": ghl_contact_id,
            "sent":           False,
            "status_code":    exc.code,
            "message":        f"GHL API returned HTTP {exc.code}: {exc.reason}",
        }

    except urllib.error.URLError as exc:
        mark_sync_record_failed(
            app_lead_id,
            now_dt,
            destination=_DESTINATION_WRITEBACK,
            error=f"Network error: {exc.reason}",
            db_path=db_path,
        )
        return {
            "ok":             False,
            "app_lead_id":    app_lead_id,
            "ghl_contact_id": ghl_contact_id,
            "sent":           False,
            "status_code":    None,
            "message":        f"Network error contacting GHL API: {exc.reason}",
        }
