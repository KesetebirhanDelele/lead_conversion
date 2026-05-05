"""
tests/progress/test_compute_course_state_quiz.py

Tests that compute_course_state correctly aggregates quiz scores
into avg_quiz_score and avg_quiz_attempts on course_state.
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
from execution.progress.compute_course_state import compute_course_state
from execution.progress.record_progress_event import record_progress_event
from execution.progress.record_quiz_score import record_quiz_score

TEST_DB_PATH = str(REPO_ROOT / "tmp" / "test_compute_state_quiz.db")

_LEAD   = "lead-state-quiz-test"
_NOW    = "2026-03-01T12:00:00+00:00"


def _cs(db_path: str) -> dict | None:
    conn = connect(db_path)
    row = conn.execute(
        "SELECT * FROM course_state WHERE lead_id = ?", (_LEAD,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


class TestCourseStateWithQuizScores(unittest.TestCase):

    def setUp(self) -> None:
        (REPO_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        conn = connect(TEST_DB_PATH)
        init_db(conn)
        conn.commit()
        conn.close()
        upsert_lead(_LEAD, db_path=TEST_DB_PATH)
        record_progress_event(
            event_id="evt-p1s1",
            lead_id=_LEAD,
            section="P1_S1",
            occurred_at=_NOW,
            db_path=TEST_DB_PATH,
        )

    def tearDown(self) -> None:
        gc.collect()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def test_avg_quiz_score_none_when_no_scores(self):
        compute_course_state(_LEAD, db_path=TEST_DB_PATH)
        row = _cs(TEST_DB_PATH)
        self.assertIsNotNone(row)
        self.assertIsNone(row["avg_quiz_score"])

    def test_avg_quiz_score_set_after_recording(self):
        record_quiz_score(_LEAD, section_id="P1_S1", quiz_id="q1", score_pct=80.0, attempts=1, now=_NOW, db_path=TEST_DB_PATH)
        compute_course_state(_LEAD, db_path=TEST_DB_PATH)
        row = _cs(TEST_DB_PATH)
        self.assertAlmostEqual(row["avg_quiz_score"], 80.0)

    def test_avg_quiz_score_averages_multiple_quizzes(self):
        record_quiz_score(_LEAD, section_id="P1_S1", quiz_id="q1", score_pct=60.0, attempts=1, now=_NOW, db_path=TEST_DB_PATH)
        record_quiz_score(_LEAD, section_id="P1_S1", quiz_id="q2", score_pct=100.0, attempts=1, now=_NOW, db_path=TEST_DB_PATH)
        compute_course_state(_LEAD, db_path=TEST_DB_PATH)
        row = _cs(TEST_DB_PATH)
        self.assertAlmostEqual(row["avg_quiz_score"], 80.0)

    def test_avg_quiz_attempts_set_after_recording(self):
        record_quiz_score(_LEAD, section_id="P1_S1", quiz_id="q1", score_pct=80.0, attempts=3, now=_NOW, db_path=TEST_DB_PATH)
        compute_course_state(_LEAD, db_path=TEST_DB_PATH)
        row = _cs(TEST_DB_PATH)
        self.assertAlmostEqual(row["avg_quiz_attempts"], 3.0)

    def test_avg_quiz_score_updates_on_recompute(self):
        record_quiz_score(_LEAD, section_id="P1_S1", quiz_id="q1", score_pct=40.0, attempts=2, now=_NOW, db_path=TEST_DB_PATH)
        compute_course_state(_LEAD, db_path=TEST_DB_PATH)
        # Update score
        record_quiz_score(_LEAD, section_id="P1_S1", quiz_id="q1", score_pct=90.0, attempts=1, now=_NOW, db_path=TEST_DB_PATH)
        compute_course_state(_LEAD, db_path=TEST_DB_PATH)
        row = _cs(TEST_DB_PATH)
        self.assertAlmostEqual(row["avg_quiz_score"], 90.0)


if __name__ == "__main__":
    unittest.main()
