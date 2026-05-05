"""
scripts/scenario_full_flow.py

Manual smoke-test for M4 + M5 functionality.

Section A -- Full lead lifecycle (SQLite, always runs):
  upsert -> invite -> progress (3 sections) -> quiz scores -> recompute
  -> get_lead_status (temperature + avg_quiz_score) -> GHL shadow push

Section B -- PostgreSQL adapter (runs only when DATABASE_URL is set):
  Tests the _PgConnection / _PgRow / _adapt / postgres.init_db() layer
  directly with raw SQL.

  NOTE: The execution functions (upsert_lead, record_quiz_score, etc.)
  internally call sqlite.init_db() which uses AUTOINCREMENT -- SQLite-only
  syntax.  Full Postgres wiring of the execution layer is a future task.
  This section validates the adapter contract, not the full flow.

Usage:
  # Section A only (SQLite):
  python scripts/scenario_full_flow.py

  # Section A + B (SQLite + Postgres):
  $env:DATABASE_URL = "postgresql://user:pass@localhost/dbname"
  python scripts/scenario_full_flow.py

  # GHL shadow mode (set before running):
  $env:GHL_SHADOW_MODE = "true"
  python scripts/scenario_full_flow.py
"""

from __future__ import annotations

import gc
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# -- isolated SQLite DB for this scenario (auto-cleaned) ----------------------
_DB_PATH = str(REPO_ROOT / "tmp" / "scenario_full_flow.db")

# -- test fixtures -------------------------------------------------------------
_LEAD_ID  = "scenario-lead-001"
_PHONE    = "+15550000001"
_EMAIL    = "scenario@example.com"
_NAME     = "Scenario User"
_NOW      = "2026-05-05T12:00:00+00:00"
_SECTIONS = ["P1_S1", "P1_S2", "P2_S1"]   # 3 of 9 -> 33.33 % completion


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _sep(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print('-' * 60)


def _ok(label: str, value=None) -> None:
    suffix = f"  ->  {value}" if value is not None else ""
    print(f"  OK   {label}{suffix}")


def _fail(label: str, detail: str = "") -> None:
    suffix = f"  ->  {detail}" if detail else ""
    print(f"  FAIL {label}{suffix}")
    sys.exit(1)


def _assert(condition: bool, label: str, detail: str = "") -> None:
    if condition:
        _ok(label)
    else:
        _fail(label, detail)


# -----------------------------------------------------------------------------
# Section A -- Full lifecycle, SQLite
# -----------------------------------------------------------------------------

def run_sqlite_scenario() -> None:
    from execution.db.sqlite import connect, init_db
    from execution.leads.upsert_lead import upsert_lead
    from execution.leads.mark_course_invite_sent import mark_course_invite_sent
    from execution.progress.record_progress_event import record_progress_event
    from execution.progress.record_quiz_score import record_quiz_score
    from execution.progress.compute_course_state import compute_course_state
    from execution.leads.get_lead_status import get_lead_status

    # -- setup -----------------------------------------------------------------
    Path(REPO_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    if os.path.exists(_DB_PATH):
        os.remove(_DB_PATH)

    _sep("A1 ? upsert_lead")
    upsert_lead(_LEAD_ID, phone=_PHONE, email=_EMAIL, name=_NAME,
                db_path=_DB_PATH, now=_NOW)
    conn = connect(_DB_PATH)
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (_LEAD_ID,)).fetchone()
    conn.close()
    _assert(row is not None, "lead row exists")
    _assert(row["phone"] == _PHONE, "phone stored", row["phone"])
    _assert(row["email"] == _EMAIL, "email stored", row["email"])
    _ok("lead created", dict(row))

    # -- invite ----------------------------------------------------------------
    _sep("A2 ? mark_course_invite_sent")
    mark_course_invite_sent("invite-scenario-001", _LEAD_ID,
                            sent_at=_NOW, channel="email",
                            db_path=_DB_PATH)
    conn = connect(_DB_PATH)
    invite = conn.execute(
        "SELECT * FROM course_invites WHERE lead_id = ?", (_LEAD_ID,)
    ).fetchone()
    conn.close()
    _assert(invite is not None, "invite row exists")
    _assert(invite["sent_at"] is not None, "sent_at persisted", invite["sent_at"])
    _ok("invite recorded")

    # -- progress events -------------------------------------------------------
    _sep("A3 ? record_progress_event (3 sections)")
    for i, section in enumerate(_SECTIONS):
        record_progress_event(
            event_id=f"evt-scenario-{i}",
            lead_id=_LEAD_ID,
            section=section,
            occurred_at=_NOW,
            db_path=_DB_PATH,
        )
        _ok(f"recorded {section}")
    conn = connect(_DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM progress_events WHERE lead_id = ?", (_LEAD_ID,)
    ).fetchone()[0]
    conn.close()
    _assert(count == 3, f"3 progress_events in DB", str(count))

    # -- idempotency check -----------------------------------------------------
    _sep("A3b ? idempotency -- duplicate event ignored")
    record_progress_event(
        event_id="evt-scenario-0",   # same event_id as first
        lead_id=_LEAD_ID,
        section="P1_S1",
        occurred_at=_NOW,
        db_path=_DB_PATH,
    )
    conn = connect(_DB_PATH)
    count2 = conn.execute(
        "SELECT COUNT(*) FROM progress_events WHERE lead_id = ?", (_LEAD_ID,)
    ).fetchone()[0]
    conn.close()
    _assert(count2 == 3, "still 3 rows (no duplicate)", str(count2))

    # -- quiz scores -----------------------------------------------------------
    _sep("A4 ? record_quiz_score")
    r1 = record_quiz_score(_LEAD_ID, section_id="P1_S1", quiz_id="p1_s1_quiz_1",
                           score_pct=80.0, attempts=2, now=_NOW, db_path=_DB_PATH)
    _assert(r1["ok"],       "quiz 1 ok")
    _assert(r1["upserted"], "quiz 1 new row (upserted=True)")

    r2 = record_quiz_score(_LEAD_ID, section_id="P1_S2", quiz_id="p1_s2_quiz_1",
                           score_pct=60.0, attempts=3, now=_NOW, db_path=_DB_PATH)
    _assert(r2["ok"],       "quiz 2 ok")
    _assert(r2["upserted"], "quiz 2 new row")

    # upsert existing quiz (update path)
    r3 = record_quiz_score(_LEAD_ID, section_id="P1_S1", quiz_id="p1_s1_quiz_1",
                           score_pct=90.0, attempts=1, now=_NOW, db_path=_DB_PATH)
    _assert(r3["ok"],          "quiz 1 re-submit ok")
    _assert(not r3["upserted"], "quiz 1 re-submit -> update (upserted=False)")

    conn = connect(_DB_PATH)
    updated_score = conn.execute(
        "SELECT score_pct FROM quiz_scores WHERE lead_id = ? AND quiz_id = ?",
        (_LEAD_ID, "p1_s1_quiz_1"),
    ).fetchone()["score_pct"]
    conn.close()
    _assert(abs(updated_score - 90.0) < 0.01, "quiz score updated to 90.0", str(updated_score))

    # -- compute_course_state --------------------------------------------------
    _sep("A5 ? compute_course_state")
    compute_course_state(_LEAD_ID, db_path=_DB_PATH)
    conn = connect(_DB_PATH)
    cs = conn.execute(
        "SELECT * FROM course_state WHERE lead_id = ?", (_LEAD_ID,)
    ).fetchone()
    conn.close()
    _assert(cs is not None, "course_state row exists")
    expected_pct = round(3 / 9 * 100, 4)   # 33.3333...
    _assert(
        abs(cs["completion_pct"] - (3 / 9 * 100.0)) < 0.01,
        f"completion_pct ? {expected_pct:.2f}%",
        str(cs["completion_pct"]),
    )
    _assert(cs["avg_quiz_score"] is not None,   "avg_quiz_score populated")
    _assert(cs["avg_quiz_attempts"] is not None, "avg_quiz_attempts populated")
    # avg of 90.0 (quiz_1 updated) and 60.0 (quiz_2) -> 75.0
    _assert(
        abs(cs["avg_quiz_score"] - 75.0) < 0.01,
        "avg_quiz_score = 75.0 (mean of 90 + 60)",
        str(cs["avg_quiz_score"]),
    )
    _ok("course_state", {
        "completion_pct":   round(cs["completion_pct"], 2),
        "current_section":  cs["current_section"],
        "avg_quiz_score":   cs["avg_quiz_score"],
        "avg_quiz_attempts": cs["avg_quiz_attempts"],
    })

    # -- get_lead_status (temperature) -----------------------------------------
    _sep("A6 ? get_lead_status -> temperature with real quiz signals")
    status = get_lead_status(_LEAD_ID, db_path=_DB_PATH)
    _assert(status["lead_exists"],   "lead_exists = True")
    _assert(status["invite_sent"],   "invite_sent = True")
    _assert("temperature" in status, "temperature key present")
    temp = status["temperature"]
    _assert("score"        in temp, "temperature.score")
    _assert("signal"       in temp, "temperature.signal")
    _assert("label"        in temp, "temperature.label")
    _assert("reason_codes" in temp, "temperature.reason_codes")
    _assert(
        status["course_state"]["avg_quiz_score"] is not None,
        "course_state.avg_quiz_score in status",
        str(status["course_state"].get("avg_quiz_score")),
    )
    _ok("get_lead_status", {
        "completion_pct": status["course_state"]["completion_pct"],
        "avg_quiz_score": status["course_state"]["avg_quiz_score"],
        "hot_signal":     status["hot_lead"]["signal"],
        "temperature":    temp,
    })

    # -- GHL shadow mode -------------------------------------------------------
    _sep("A7 ? GHL shadow push (GHL_SHADOW_MODE=true)")
    os.environ["GHL_SHADOW_MODE"] = "true"
    try:
        from execution.ghl.write_ghl_contact_fields import write_ghl_contact_fields
        result = write_ghl_contact_fields(_LEAD_ID, now=_NOW, db_path=_DB_PATH)
        _assert(result["ok"],      "write_ghl ok=True")
        _assert(result.get("shadow"), "shadow=True (no HTTP POST)")
        _assert(not result["sent"], "sent=False")

        conn = connect(_DB_PATH)
        shadow_row = conn.execute(
            "SELECT status, payload_json FROM sync_records WHERE lead_id = ? AND destination = ?",
            (_LEAD_ID, "GHL_WRITEBACK"),
        ).fetchone()
        conn.close()
        _assert(shadow_row is not None,       "sync_records shadow row written")
        _assert(shadow_row["status"] == "SHADOW", "status = SHADOW")

        payload = json.loads(shadow_row["payload_json"])
        _assert("customFields" in payload,    "payload has customFields key")
        _assert(len(payload["customFields"]) == 5, "5 custom fields in payload")
        _ok("shadow payload", {k["key"]: k["field_value"] for k in payload["customFields"]})
    finally:
        del os.environ["GHL_SHADOW_MODE"]

    # -- cleanup ---------------------------------------------------------------
    gc.collect()
    if os.path.exists(_DB_PATH):
        os.remove(_DB_PATH)
    print(f"\n  (temp DB cleaned up: {_DB_PATH})")


# -----------------------------------------------------------------------------
# Section B -- PostgreSQL adapter smoke test
# -----------------------------------------------------------------------------

def run_postgres_scenario(database_url: str) -> None:
    """
    Tests the _PgConnection / _PgRow / _adapt / postgres.init_db() adapter layer.
    Does NOT run execution functions (they call sqlite.init_db internally).
    """
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("\n  WARN psycopg2 not installed -- skipping Postgres section.")
        print("       pip install psycopg2-binary")
        return

    from execution.db.postgres import connect as pg_connect, init_db as pg_init_db, _PgRow

    _sep("B1 ? postgres.connect() returns _PgConnection")
    try:
        pg_conn = pg_connect(database_url)
        _ok("connected", database_url.split("@")[-1])   # hide credentials
    except Exception as exc:
        _fail("could not connect to Postgres", str(exc))
        return

    _sep("B2 ? postgres.init_db() creates all tables")
    try:
        pg_init_db(pg_conn)
        _ok("init_db() completed without error")
    except Exception as exc:
        _fail("init_db() raised", str(exc))
        pg_conn.close()
        return

    _sep("B3 ? table presence check")
    expected_tables = [
        "leads", "course_invites", "progress_events", "course_state",
        "hot_lead_signals", "sync_records", "reflection_responses",
        "lead_final_scores", "quiz_scores",
    ]
    for tbl in expected_tables:
        row = pg_conn.execute(
            "SELECT to_regclass(%s) AS tbl", (f"public.{tbl}",)
        ).fetchone()
        _assert(row is not None and row["tbl"] is not None, f"table {tbl!r} exists")

    _sep("B4 ? _adapt() placeholder conversion")
    from execution.db.postgres import _adapt
    adapted = _adapt("SELECT * FROM leads WHERE id = ? AND email = ?")
    _assert(
        adapted == "SELECT * FROM leads WHERE id = %s AND email = %s",
        "? -> %s adapted",
        adapted,
    )

    _sep("B5 ? _PgRow string + integer key access")
    pg_conn.execute(
        "INSERT INTO leads (id, phone, email, name, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        ("pg-test-lead", "+15550000099", "pg@test.com", "PG Test",
         _NOW, _NOW),
    )
    pg_conn.commit()

    cur = pg_conn.execute("SELECT id, phone, email FROM leads WHERE id = %s", ("pg-test-lead",))
    row = cur.fetchone()
    _assert(isinstance(row, _PgRow), "_PgRow returned")
    _assert(row["id"]    == "pg-test-lead",  "string key 'id'",    row["id"])
    _assert(row[0]       == "pg-test-lead",  "int index [0]",       row[0])
    _assert(row["phone"] == "+15550000099",  "string key 'phone'",  row["phone"])
    _assert(row.get("email") == "pg@test.com", ".get('email')",     row.get("email"))
    _assert(row.get("missing", "X") == "X",   ".get missing -> default")

    _sep("B6 ? fetchall() returns list[_PgRow]")
    rows = pg_conn.execute("SELECT id FROM leads").fetchall()
    _assert(isinstance(rows, list),      "fetchall returns list")
    _assert(len(rows) >= 1,              f"at least 1 row ({len(rows)} found)")
    _assert(isinstance(rows[0], _PgRow), "each item is _PgRow")

    _sep("B7 ? quiz_scores table CRUD")
    pg_conn.execute(
        "INSERT INTO quiz_scores (lead_id, course_id, section_id, quiz_id, "
        "score_pct, attempts, recorded_at) VALUES (%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (lead_id, course_id, section_id, quiz_id) DO UPDATE "
        "SET score_pct = EXCLUDED.score_pct",
        ("pg-test-lead", "FREE_INTRO_AI_V0", "P1_S1", "q1", 88.5, 2, _NOW),
    )
    pg_conn.commit()
    qs = pg_conn.execute(
        "SELECT score_pct FROM quiz_scores WHERE lead_id = %s AND quiz_id = %s",
        ("pg-test-lead", "q1"),
    ).fetchone()
    _assert(qs is not None,                    "quiz_scores row inserted")
    _assert(abs(qs["score_pct"] - 88.5) < 0.01, "score_pct = 88.5", str(qs["score_pct"]))

    _sep("B8 ? connect() env-switch via sqlite.connect(db_path=None)")
    from execution.db.sqlite import connect as sq_connect
    from execution.db.postgres import _PgConnection
    sq_via_env = sq_connect(db_path=None)
    _assert(isinstance(sq_via_env, _PgConnection),
            "sqlite.connect(db_path=None) returns _PgConnection when DATABASE_URL is set")
    sq_via_env.close()

    # -- teardown --------------------------------------------------------------
    pg_conn.execute("DELETE FROM quiz_scores WHERE lead_id = %s", ("pg-test-lead",))
    pg_conn.execute("DELETE FROM leads WHERE id = %s",            ("pg-test-lead",))
    pg_conn.commit()
    pg_conn.close()
    print("\n  (Postgres test rows cleaned up)")


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  Lead Conversion -- Full-Flow Scenario")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    _sep("SECTION A -- SQLite full lifecycle")
    run_sqlite_scenario()
    print("\n  OK  Section A complete")

    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith(("postgres://", "postgresql://")):
        _sep("SECTION B -- PostgreSQL adapter")
        run_postgres_scenario(database_url)
        print("\n  OK  Section B complete")
    else:
        print("\n  --  Section B skipped (DATABASE_URL not set to a Postgres URL)")
        print("      Set DATABASE_URL=postgresql://user:pass@host/db to enable.")

    print("\n" + "=" * 60)
    print("  All checks passed.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
