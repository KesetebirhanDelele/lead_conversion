"""
tests/dispatch/test_run_dispatch_cycle.py

Integration tests for execution/dispatch/run_dispatch_cycle.py.
Uses an isolated SQLite DB; never touches tmp/app.db.

Strategy: seed leads directly into the DB, then run the full cycle and
assert on sync_records rows (shadow dispatches written) and the summary dict.
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
from execution.dispatch.check_cooldown import cora_destination
from execution.dispatch.run_dispatch_cycle import run_dispatch_cycle
from execution.leads.upsert_lead import upsert_lead

TEST_DB_PATH = str(REPO_ROOT / "tmp" / "test_run_dispatch_cycle.db")

_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)


class TestRunDispatchCycle(unittest.TestCase):

    def setUp(self) -> None:
        (REPO_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        conn = connect(TEST_DB_PATH)
        init_db(conn)
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        gc.collect()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def _shadow_count(self) -> int:
        conn = connect(TEST_DB_PATH)
        n = conn.execute(
            "SELECT COUNT(*) FROM sync_records WHERE status = 'SHADOW'",
        ).fetchone()[0]
        conn.close()
        return n

    # ------------------------------------------------------------------
    # T1 — empty DB → clean zero-result cycle
    # ------------------------------------------------------------------
    def test_empty_db_returns_zero_dispatched(self):
        result = run_dispatch_cycle(now=_NOW, db_path=TEST_DB_PATH)
        self.assertEqual(result["total_scanned"], 0)
        self.assertEqual(result["dispatched"], 0)
        self.assertEqual(result["errors"], 0)
        self.assertTrue(result["ok"])

    def test_empty_db_returns_required_keys(self):
        result = run_dispatch_cycle(now=_NOW, db_path=TEST_DB_PATH)
        for key in ("ok", "generated_at", "total_scanned", "dispatched",
                    "cooldown_skipped", "no_action", "errors"):
            self.assertIn(key, result, f"Missing key: {key}")

    # ------------------------------------------------------------------
    # T2 — uninvited lead → SEND_INVITE shadow record written
    # ------------------------------------------------------------------
    def test_uninvited_lead_gets_shadow_dispatch(self):
        upsert_lead("L-uninvited", db_path=TEST_DB_PATH)

        result = run_dispatch_cycle(now=_NOW, db_path=TEST_DB_PATH)

        self.assertEqual(result["dispatched"], 1)
        self.assertEqual(self._shadow_count(), 1)

    def test_shadow_record_has_send_invite_destination(self):
        upsert_lead("L-uninvited2", db_path=TEST_DB_PATH)
        run_dispatch_cycle(now=_NOW, db_path=TEST_DB_PATH)

        conn = connect(TEST_DB_PATH)
        row = conn.execute(
            "SELECT destination FROM sync_records WHERE status = 'SHADOW'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["destination"], cora_destination("SEND_INVITE"))

    # ------------------------------------------------------------------
    # T3 — same lead on second cycle → cooldown_skipped
    # ------------------------------------------------------------------
    def test_second_cycle_within_cooldown_skips_lead(self):
        upsert_lead("L-cooldown", db_path=TEST_DB_PATH)

        run_dispatch_cycle(now=_NOW, db_path=TEST_DB_PATH)
        result2 = run_dispatch_cycle(now=_NOW, db_path=TEST_DB_PATH)

        self.assertEqual(result2["dispatched"], 0)
        self.assertEqual(result2["cooldown_skipped"], 1)

    def test_second_cycle_after_cooldown_dispatches_again(self):
        upsert_lead("L-postcooldown", db_path=TEST_DB_PATH)

        run_dispatch_cycle(now=_NOW, db_path=TEST_DB_PATH)
        # Advance time past the 24h cooldown window.
        future = _NOW + timedelta(hours=25)
        result2 = run_dispatch_cycle(now=future, db_path=TEST_DB_PATH)

        self.assertEqual(result2["dispatched"], 1)

    # ------------------------------------------------------------------
    # T4 — summary dict counts are consistent with DB state
    # ------------------------------------------------------------------
    def test_shadow_count_matches_dispatched(self):
        for i in range(3):
            upsert_lead(f"L-multi-{i}", db_path=TEST_DB_PATH)

        result = run_dispatch_cycle(now=_NOW, db_path=TEST_DB_PATH)

        self.assertEqual(result["dispatched"], self._shadow_count())

    # ------------------------------------------------------------------
    # T5 — generated_at reflects the injected now
    # ------------------------------------------------------------------
    def test_generated_at_matches_now(self):
        result = run_dispatch_cycle(now=_NOW, db_path=TEST_DB_PATH)
        self.assertIn("2026-03-01", result["generated_at"])
