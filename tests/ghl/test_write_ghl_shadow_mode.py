"""
tests/ghl/test_write_ghl_shadow_mode.py

Integration tests for GHL_SHADOW_MODE behavior in
execution/ghl/write_ghl_contact_fields.py.

Uses an isolated SQLite DB; never touches tmp/app.db.
All tests set GHL_SHADOW_MODE=true and verify that:
  - No HTTP request is made
  - A SHADOW sync_records row is written with the M4 payload
  - The return dict has ok=True, sent=False, shadow=True
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
from execution.ghl.write_ghl_contact_fields import write_ghl_contact_fields
from execution.leads.upsert_lead import upsert_lead

TEST_DB_PATH = str(REPO_ROOT / "tmp" / "test_write_ghl_shadow_mode.db")

_NOW    = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
_LEAD   = "lead-shadow-m4-test"
_API_URL = "https://services.leadconnectorhq.com/contacts/fake"


def _fetch_shadow_row(lead_id: str) -> dict | None:
    conn = connect(TEST_DB_PATH)
    row = conn.execute(
        "SELECT * FROM sync_records WHERE lead_id = ? AND status = 'SHADOW' AND destination = 'GHL_WRITEBACK'",
        (lead_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


class TestShadowMode(unittest.TestCase):

    def setUp(self) -> None:
        (REPO_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        conn = connect(TEST_DB_PATH)
        init_db(conn)
        conn.commit()
        conn.close()
        upsert_lead(_LEAD, db_path=TEST_DB_PATH)
        # Enable shadow mode for every test.
        os.environ["GHL_SHADOW_MODE"] = "true"

    def tearDown(self) -> None:
        os.environ.pop("GHL_SHADOW_MODE", None)
        gc.collect()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def _call(self) -> dict:
        return write_ghl_contact_fields(
            _LEAD,
            now=_NOW,
            ghl_api_url=_API_URL,
            db_path=TEST_DB_PATH,
        )

    # ------------------------------------------------------------------
    # Return dict
    # ------------------------------------------------------------------

    def test_shadow_returns_ok_true(self):
        result = self._call()
        self.assertTrue(result["ok"])

    def test_shadow_returns_sent_false(self):
        result = self._call()
        self.assertFalse(result["sent"])

    def test_shadow_returns_shadow_true(self):
        result = self._call()
        self.assertTrue(result.get("shadow"))

    def test_shadow_message_contains_shadow_mode(self):
        result = self._call()
        self.assertIn("SHADOW_MODE", result["message"])

    def test_shadow_returns_app_lead_id(self):
        result = self._call()
        self.assertEqual(result["app_lead_id"], _LEAD)

    # ------------------------------------------------------------------
    # DB side-effect
    # ------------------------------------------------------------------

    def test_shadow_writes_sync_record(self):
        self._call()
        row = _fetch_shadow_row(_LEAD)
        self.assertIsNotNone(row)

    def test_shadow_record_destination_is_ghl_writeback(self):
        self._call()
        row = _fetch_shadow_row(_LEAD)
        self.assertEqual(row["destination"], "GHL_WRITEBACK")

    def test_shadow_record_payload_is_valid_json(self):
        self._call()
        row = _fetch_shadow_row(_LEAD)
        payload = json.loads(row["payload_json"])
        self.assertIn("customFields", payload)

    def test_shadow_record_payload_has_five_custom_fields(self):
        self._call()
        row = _fetch_shadow_row(_LEAD)
        payload = json.loads(row["payload_json"])
        self.assertEqual(len(payload["customFields"]), 5)

    def test_shadow_record_updated_at_matches_now(self):
        self._call()
        row = _fetch_shadow_row(_LEAD)
        self.assertIn("2026-03-01", row["updated_at"])

    def test_second_call_upserts_not_duplicates(self):
        self._call()
        self._call()
        conn = connect(TEST_DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM sync_records WHERE lead_id = ? AND status = 'SHADOW'",
            (_LEAD,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    # ------------------------------------------------------------------
    # No HTTP request made
    # ------------------------------------------------------------------

    def test_no_network_call_in_shadow_mode(self):
        import urllib.request as _urllib_request
        original_urlopen = _urllib_request.urlopen
        called = []

        def fail_if_called(*a, **kw):
            called.append(True)
            return original_urlopen(*a, **kw)

        _urllib_request.urlopen = fail_if_called
        try:
            self._call()
        finally:
            _urllib_request.urlopen = original_urlopen

        self.assertEqual(called, [], "urlopen must not be called in shadow mode")

    # ------------------------------------------------------------------
    # Shadow mode env var variants
    # ------------------------------------------------------------------

    def test_shadow_mode_value_1(self):
        os.environ["GHL_SHADOW_MODE"] = "1"
        result = self._call()
        self.assertTrue(result.get("shadow"))

    def test_shadow_mode_value_yes(self):
        os.environ["GHL_SHADOW_MODE"] = "yes"
        result = self._call()
        self.assertTrue(result.get("shadow"))

    def test_shadow_mode_false_does_not_shadow(self):
        os.environ["GHL_SHADOW_MODE"] = "false"
        result = self._call()
        self.assertFalse(result.get("shadow", False))


if __name__ == "__main__":
    unittest.main()
