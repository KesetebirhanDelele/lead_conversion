"""
tests/dispatch/test_check_cooldown.py

Unit tests for execution/dispatch/check_cooldown.py.
Uses an isolated SQLite DB; never touches tmp/app.db.
"""

from __future__ import annotations

import gc
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.db.sqlite import connect, init_db
from execution.dispatch.check_cooldown import cora_destination, is_on_cooldown

TEST_DB_PATH = str(REPO_ROOT / "tmp" / "test_check_cooldown.db")

_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
_LEAD = "lead-cooldown-test"
_EVENT = "SEND_INVITE"


def _seed_lead() -> None:
    conn = connect(TEST_DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO leads (id, name, email, phone, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (_LEAD, "Test", "t@t.com", "5550000000", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()


def _insert_sync_record(status: str, updated_at: str) -> None:
    conn = connect(TEST_DB_PATH)
    conn.execute(
        """
        INSERT INTO sync_records (lead_id, destination, status, updated_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (_LEAD, cora_destination(_EVENT), status, updated_at, updated_at),
    )
    conn.commit()
    conn.close()


class TestIsOnCooldown(unittest.TestCase):

    def setUp(self) -> None:
        (REPO_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        conn = connect(TEST_DB_PATH)
        init_db(conn)
        conn.commit()
        conn.close()
        _seed_lead()

    def tearDown(self) -> None:
        gc.collect()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def test_no_record_returns_false(self):
        result = is_on_cooldown(_LEAD, _EVENT, now=_NOW, db_path=TEST_DB_PATH)
        self.assertFalse(result)

    def test_sent_within_24h_returns_true(self):
        recent = (_NOW - timedelta(hours=12)).isoformat()
        _insert_sync_record("SENT", recent)
        result = is_on_cooldown(_LEAD, _EVENT, now=_NOW, db_path=TEST_DB_PATH)
        self.assertTrue(result)

    def test_shadow_within_24h_returns_true(self):
        recent = (_NOW - timedelta(hours=6)).isoformat()
        _insert_sync_record("SHADOW", recent)
        result = is_on_cooldown(_LEAD, _EVENT, now=_NOW, db_path=TEST_DB_PATH)
        self.assertTrue(result)

    def test_sent_older_than_24h_returns_false(self):
        old = (_NOW - timedelta(hours=25)).isoformat()
        _insert_sync_record("SENT", old)
        result = is_on_cooldown(_LEAD, _EVENT, now=_NOW, db_path=TEST_DB_PATH)
        self.assertFalse(result)

    def test_failed_record_does_not_trigger_cooldown(self):
        recent = (_NOW - timedelta(hours=1)).isoformat()
        _insert_sync_record("FAILED", recent)
        result = is_on_cooldown(_LEAD, _EVENT, now=_NOW, db_path=TEST_DB_PATH)
        self.assertFalse(result)

    def test_different_event_type_does_not_trigger_cooldown(self):
        recent = (_NOW - timedelta(hours=1)).isoformat()
        _insert_sync_record("SENT", recent)
        result = is_on_cooldown(_LEAD, "NUDGE_PROGRESS", now=_NOW, db_path=TEST_DB_PATH)
        self.assertFalse(result)

    def test_different_lead_does_not_trigger_cooldown(self):
        recent = (_NOW - timedelta(hours=1)).isoformat()
        _insert_sync_record("SENT", recent)
        # Query for a lead that has no sync record — cooldown must be False.
        result = is_on_cooldown("no-such-lead-xyz", _EVENT, now=_NOW, db_path=TEST_DB_PATH)
        self.assertFalse(result)

    def test_custom_cooldown_hours_respected(self):
        six_hours_ago = (_NOW - timedelta(hours=6)).isoformat()
        _insert_sync_record("SENT", six_hours_ago)
        # 4h cooldown → 6h ago is outside → not on cooldown
        self.assertFalse(is_on_cooldown(_LEAD, _EVENT, cooldown_hours=4, now=_NOW, db_path=TEST_DB_PATH))
        # 8h cooldown → 6h ago is inside → on cooldown
        self.assertTrue(is_on_cooldown(_LEAD, _EVENT, cooldown_hours=8, now=_NOW, db_path=TEST_DB_PATH))


class TestCoraDestination(unittest.TestCase):

    def test_format(self):
        self.assertEqual(cora_destination("SEND_INVITE"), "CORA:SEND_INVITE")
        self.assertEqual(cora_destination("NUDGE_PROGRESS"), "CORA:NUDGE_PROGRESS")

    def test_different_events_are_distinct(self):
        self.assertNotEqual(cora_destination("A"), cora_destination("B"))
