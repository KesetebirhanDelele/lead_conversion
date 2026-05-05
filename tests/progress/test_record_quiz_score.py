"""
tests/progress/test_record_quiz_score.py

Unit tests for execution/progress/record_quiz_score.py.
Uses an isolated SQLite DB; never touches tmp/app.db.
"""

from __future__ import annotations

import gc
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.db.sqlite import connect, init_db
from execution.leads.upsert_lead import upsert_lead
from execution.progress.record_quiz_score import record_quiz_score

TEST_DB_PATH = str(REPO_ROOT / "tmp" / "test_record_quiz_score.db")

_NOW     = "2026-03-01T12:00:00+00:00"
_LEAD    = "lead-quiz-score-test"
_SECTION = "P1_S1"
_QUIZ    = "p1_s1_quiz_1"


class TestRecordQuizScore(unittest.TestCase):

    def setUp(self) -> None:
        (REPO_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        conn = connect(TEST_DB_PATH)
        init_db(conn)
        conn.commit()
        conn.close()
        upsert_lead(_LEAD, db_path=TEST_DB_PATH)

    def tearDown(self) -> None:
        gc.collect()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def _call(self, score_pct=80.0, attempts=2) -> dict:
        return record_quiz_score(
            _LEAD,
            section_id=_SECTION,
            quiz_id=_QUIZ,
            score_pct=score_pct,
            attempts=attempts,
            now=_NOW,
            db_path=TEST_DB_PATH,
        )

    def _fetch(self):
        conn = connect(TEST_DB_PATH)
        row = conn.execute(
            "SELECT * FROM quiz_scores WHERE lead_id = ? AND section_id = ? AND quiz_id = ?",
            (_LEAD, _SECTION, _QUIZ),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_returns_ok_true(self):
        self.assertTrue(self._call()["ok"])

    def test_first_insert_upserted_true(self):
        self.assertTrue(self._call()["upserted"])

    def test_row_written(self):
        self._call()
        self.assertIsNotNone(self._fetch())

    def test_score_pct_stored(self):
        self._call(score_pct=75.0)
        self.assertAlmostEqual(self._fetch()["score_pct"], 75.0)

    def test_attempts_stored(self):
        self._call(attempts=3)
        self.assertEqual(self._fetch()["attempts"], 3)

    def test_recorded_at_stored(self):
        self._call()
        self.assertIn("2026-03-01", self._fetch()["recorded_at"])

    def test_second_write_upserts(self):
        self._call(score_pct=60.0)
        result = self._call(score_pct=90.0)
        self.assertTrue(result["ok"])
        self.assertFalse(result["upserted"])
        self.assertAlmostEqual(self._fetch()["score_pct"], 90.0)

    def test_second_write_no_duplicate_row(self):
        self._call()
        self._call()
        conn = connect(TEST_DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM quiz_scores WHERE lead_id = ? AND section_id = ? AND quiz_id = ?",
            (_LEAD, _SECTION, _QUIZ),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_different_quizzes_create_separate_rows(self):
        record_quiz_score(_LEAD, section_id=_SECTION, quiz_id="quiz_a", score_pct=70.0, attempts=1, now=_NOW, db_path=TEST_DB_PATH)
        record_quiz_score(_LEAD, section_id=_SECTION, quiz_id="quiz_b", score_pct=90.0, attempts=2, now=_NOW, db_path=TEST_DB_PATH)
        conn = connect(TEST_DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM quiz_scores WHERE lead_id = ?", (_LEAD,)).fetchone()[0]
        conn.close()
        self.assertEqual(count, 2)

    def test_zero_score_allowed(self):
        result = self._call(score_pct=0.0)
        self.assertTrue(result["ok"])

    def test_perfect_score_allowed(self):
        result = self._call(score_pct=100.0)
        self.assertTrue(result["ok"])

    # ------------------------------------------------------------------
    # Validation failures
    # ------------------------------------------------------------------

    def test_empty_lead_id_fails(self):
        result = record_quiz_score("", section_id=_SECTION, quiz_id=_QUIZ, score_pct=80.0, attempts=1, now=_NOW, db_path=TEST_DB_PATH)
        self.assertFalse(result["ok"])

    def test_empty_section_id_fails(self):
        result = record_quiz_score(_LEAD, section_id="", quiz_id=_QUIZ, score_pct=80.0, attempts=1, now=_NOW, db_path=TEST_DB_PATH)
        self.assertFalse(result["ok"])

    def test_empty_quiz_id_fails(self):
        result = record_quiz_score(_LEAD, section_id=_SECTION, quiz_id="", score_pct=80.0, attempts=1, now=_NOW, db_path=TEST_DB_PATH)
        self.assertFalse(result["ok"])

    def test_score_above_100_fails(self):
        result = self._call(score_pct=101.0)
        self.assertFalse(result["ok"])

    def test_negative_score_fails(self):
        result = self._call(score_pct=-1.0)
        self.assertFalse(result["ok"])

    def test_zero_attempts_fails(self):
        result = self._call(attempts=0)
        self.assertFalse(result["ok"])

    def test_empty_now_fails(self):
        result = record_quiz_score(_LEAD, section_id=_SECTION, quiz_id=_QUIZ, score_pct=80.0, attempts=1, now="", db_path=TEST_DB_PATH)
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
