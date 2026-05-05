"""
execution/progress/record_quiz_score.py

Persist a quiz score (per quiz per section per lead) to the quiz_scores table.

Score granularity: one row per (lead_id, course_id, section_id, quiz_id).
Repeated calls for the same quiz upsert in-place — the latest attempt wins.

score_pct:  0.0–100.0 — percentage of questions answered correctly.
attempts:   total answer submissions made across all questions in the quiz
            (minimum 1; max = questions × 3 due to retry cap).

Return shape
------------
ok=True:
    {"ok": True, "upserted": bool}   — upserted=True if a new row was inserted,
                                        False if an existing row was updated.

ok=False (validation failure):
    {"ok": False, "message": str}
"""

from __future__ import annotations

from execution.db.sqlite import connect, init_db


def record_quiz_score(
    lead_id: str,
    *,
    course_id: str = "FREE_INTRO_AI_V0",
    section_id: str,
    quiz_id: str,
    score_pct: float,
    attempts: int,
    now: str,
    db_path: str | None = None,
) -> dict:
    """Upsert a quiz score for one quiz attempt.

    Args:
        lead_id:    Internal lead identifier.
        course_id:  Course the quiz belongs to. Defaults to FREE_INTRO_AI_V0.
        section_id: Section identifier (e.g. "P1_S1").
        quiz_id:    Quiz identifier (e.g. "p1_s1_quiz_1").
        score_pct:  Percentage correct (0.0 – 100.0).
        attempts:   Total submissions made (all questions combined).
        now:        ISO-8601 UTC string; used as recorded_at.
        db_path:    Path to the SQLite file; defaults to tmp/app.db.

    Returns:
        {"ok": True, "upserted": bool}  on success.
        {"ok": False, "message": str}   on validation failure.
    """
    if not lead_id or not lead_id.strip():
        return {"ok": False, "message": "lead_id must be non-empty."}
    if not section_id or not section_id.strip():
        return {"ok": False, "message": "section_id must be non-empty."}
    if not quiz_id or not quiz_id.strip():
        return {"ok": False, "message": "quiz_id must be non-empty."}
    if not (0.0 <= score_pct <= 100.0):
        return {"ok": False, "message": f"score_pct must be 0.0–100.0; got {score_pct}."}
    if attempts < 1:
        return {"ok": False, "message": f"attempts must be >= 1; got {attempts}."}
    if not now:
        return {"ok": False, "message": "now must be a non-empty ISO-8601 string."}

    conn = connect(db_path)
    try:
        init_db(conn)

        before = conn.execute(
            "SELECT COUNT(*) FROM quiz_scores WHERE lead_id = ? AND course_id = ? AND section_id = ? AND quiz_id = ?",
            (lead_id, course_id, section_id, quiz_id),
        ).fetchone()[0]

        conn.execute(
            """
            INSERT INTO quiz_scores
                (lead_id, course_id, section_id, quiz_id, score_pct, attempts, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lead_id, course_id, section_id, quiz_id) DO UPDATE SET
                score_pct   = excluded.score_pct,
                attempts    = excluded.attempts,
                recorded_at = excluded.recorded_at
            """,
            (lead_id, course_id, section_id, quiz_id, float(score_pct), int(attempts), now),
        )
        conn.commit()
        upserted = before == 0
    finally:
        conn.close()

    return {"ok": True, "upserted": upserted}
