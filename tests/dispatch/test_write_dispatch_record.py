"""
tests/dispatch/test_write_dispatch_record.py

Unit tests for execution/dispatch/write_dispatch_record.py.
Uses an isolated SQLite DB; never touches tmp/app.db.
"""

from __future__ import annotations

import gc
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.db.sqlite import connect, init_db
from execution.dispatch.check_cooldown import cora_destination
from execution.dispatch.write_dispatch_record import write_shadow_record

TEST_DB_PATH = str(REPO_ROOT / "tmp" / "test_write_dispatch_record.db")

_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
_LEAD = "lead-dispatch-write"
_EVENT = "SEND_INVITE"
_REC = {"lead_id": _LEAD, "event_type": _EVENT, "priority": "LOW", "reason_codes": ["NOT_INVITED"]}


class TestWriteShadowRecord(unittest.TestCase):

    def setUp(self) -> None:
        (REPO_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        conn = connect(TEST_DB_PATH)
        init_db(conn)
        conn.execute(
            "INSERT INTO leads (id, name, email, phone, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (_LEAD, "Test", "t@t.com", "5550000000", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        gc.collect()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def _fetch_row(self) -> dict | None:
        conn = connect(TEST_DB_PATH)
        row = conn.execute(
            "SELECT * FROM sync_records WHERE lead_id = ? AND destination = ?",
            (_LEAD, cora_destination(_EVENT)),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def test_writes_shadow_record(self):
        write_shadow_record(_LEAD, _EVENT, _REC, now=_NOW, db_path=TEST_DB_PATH)
        row = self._fetch_row()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "SHADOW")

    def test_destination_format(self):
        write_shadow_record(_LEAD, _EVENT, _REC, now=_NOW, db_path=TEST_DB_PATH)
        row = self._fetch_row()
        self.assertEqual(row["destination"], "CORA:SEND_INVITE")

    def test_payload_is_valid_json(self):
        write_shadow_record(_LEAD, _EVENT, _REC, now=_NOW, db_path=TEST_DB_PATH)
        row = self._fetch_row()
        payload = json.loads(row["payload_json"])
        self.assertEqual(payload["event_type"], _EVENT)

    def test_updated_at_matches_now(self):
        write_shadow_record(_LEAD, _EVENT, _REC, now=_NOW, db_path=TEST_DB_PATH)
        row = self._fetch_row()
        self.assertIn("2026-03-01", row["updated_at"])

    def test_second_write_upserts_not_duplicates(self):
        write_shadow_record(_LEAD, _EVENT, _REC, now=_NOW, db_path=TEST_DB_PATH)
        write_shadow_record(_LEAD, _EVENT, _REC, now=_NOW, db_path=TEST_DB_PATH)
        conn = connect(TEST_DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM sync_records WHERE lead_id = ? AND destination = ?",
            (_LEAD, cora_destination(_EVENT)),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_different_event_types_create_separate_rows(self):
        write_shadow_record(_LEAD, "SEND_INVITE",    _REC, now=_NOW, db_path=TEST_DB_PATH)
        write_shadow_record(_LEAD, "NUDGE_PROGRESS", _REC, now=_NOW, db_path=TEST_DB_PATH)
        conn = connect(TEST_DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM sync_records WHERE lead_id = ?", (_LEAD,)
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 2)
