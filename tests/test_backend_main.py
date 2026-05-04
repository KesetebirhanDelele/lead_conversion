"""
tests/test_backend_main.py

API-layer tests for backend/main.py.

These tests verify HTTP routing, request validation, response serialisation,
and error handling.  All execution-layer functions are mocked — their own
correctness is covered by their respective unit tests in tests/progress/
and tests/leads/.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from backend.main import app               # noqa: E402

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared mock return values — match the full shape returned by get_lead_status
# ---------------------------------------------------------------------------

_STATUS_NOT_FOUND = {
    "lead_exists": False,
    "invite_sent": False,
    "course_state": {
        "current_section": None,
        "completion_pct": None,
        "last_activity_at": None,
        "started_at": None,
    },
    "hot_lead": {"signal": None, "score": None, "reason": None},
}

_STATUS_EXISTS = {
    "lead_exists": True,
    "invite_sent": True,
    "course_state": {
        "current_section": "P2_S1",
        "completion_pct": 33.33,
        "last_activity_at": "2026-01-01T10:00:00+00:00",
        "started_at": "2026-01-01T09:00:00+00:00",
    },
    "hot_lead": {"signal": "HOT", "score": 80.0, "reason": "completion_and_recency"},
}


# ---------------------------------------------------------------------------
# POST /api/lead/status
# ---------------------------------------------------------------------------

class TestLeadStatusEndpoint(unittest.TestCase):

    def test_missing_lead_returns_lead_exists_false(self):
        """Unknown lead_id returns 200 with lead_exists=false."""
        with patch("backend.main.get_lead_status", return_value=_STATUS_NOT_FOUND):
            resp = client.post("/api/lead/status", json={"lead_id": "nobody@example.com"})

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["lead_exists"])
        self.assertIsNone(body["course_state"]["current_section"])
        self.assertIsNone(body["course_state"]["completion_pct"])
        self.assertIsNone(body["course_state"]["last_activity_at"])
        self.assertIsNone(body["course_state"]["lead_signal"])
        self.assertIsNone(body["hot_lead"]["signal"])

    def test_existing_lead_returns_course_state(self):
        """Known lead_id returns 200 with populated course_state and hot_lead."""
        with patch("backend.main.get_lead_status", return_value=_STATUS_EXISTS):
            resp = client.post("/api/lead/status", json={"lead_id": "user@example.com"})

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["lead_exists"])
        self.assertEqual(body["course_state"]["current_section"], "P2_S1")
        self.assertAlmostEqual(body["course_state"]["completion_pct"], 33.33, places=2)
        self.assertEqual(body["course_state"]["last_activity_at"], "2026-01-01T10:00:00+00:00")
        self.assertEqual(body["course_state"]["lead_signal"], "HOT")
        self.assertEqual(body["hot_lead"]["signal"], "HOT")
        self.assertAlmostEqual(body["hot_lead"]["score"], 80.0, places=1)
        self.assertEqual(body["hot_lead"]["reason"], "completion_and_recency")

    def test_missing_lead_id_returns_422(self):
        """Request with no body returns 422 (Pydantic validation failure)."""
        resp = client.post("/api/lead/status", json={})
        self.assertEqual(resp.status_code, 422)

    def test_empty_string_lead_id_accepted(self):
        """Empty lead_id is a string — Pydantic accepts it; confirm no 500."""
        with patch("backend.main.get_lead_status", return_value=_STATUS_NOT_FOUND):
            resp = client.post("/api/lead/status", json={"lead_id": ""})
        self.assertIn(resp.status_code, (200, 422))

    def test_wrong_content_type_returns_422(self):
        """Non-JSON body returns 422."""
        resp = client.post(
            "/api/lead/status",
            content="lead_id=user@example.com",
            headers={"Content-Type": "text/plain"},
        )
        self.assertEqual(resp.status_code, 422)


# ---------------------------------------------------------------------------
# POST /api/progress/update
# ---------------------------------------------------------------------------

class TestProgressUpdateEndpoint(unittest.TestCase):

    def _mock_all(self, status_return=None):
        """Return a tuple of context managers that mock all execution calls."""
        if status_return is None:
            status_return = _STATUS_EXISTS
        return (
            patch("backend.main.upsert_lead"),
            patch("backend.main.mark_course_invite_sent"),
            patch("backend.main.record_progress_event"),
            patch("backend.main.compute_course_state"),
            patch("backend.main.get_lead_status", return_value=status_return),
        )

    def test_valid_request_returns_event_id(self):
        """Valid lead_id + section returns 200 with correct event_id."""
        p1, p2, p3, p4, p5 = self._mock_all()
        with p1, p2, p3, p4, p5:
            resp = client.post(
                "/api/progress/update",
                json={"lead_id": "user@example.com", "section": "P1_S1"},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["event_id"], "user@example.com:P1_S1")

    def test_valid_request_returns_course_state(self):
        """Response includes full course_state with lead_signal."""
        p1, p2, p3, p4, p5 = self._mock_all()
        with p1, p2, p3, p4, p5:
            resp = client.post(
                "/api/progress/update",
                json={"lead_id": "user@example.com", "section": "P2_S1"},
            )

        body = resp.json()
        self.assertEqual(body["course_state"]["current_section"], "P2_S1")
        self.assertAlmostEqual(body["course_state"]["completion_pct"], 33.33, places=2)
        self.assertEqual(body["course_state"]["lead_signal"], "HOT")

    def test_valid_request_returns_hot_lead(self):
        """Response includes hot_lead signal, score, and reason."""
        p1, p2, p3, p4, p5 = self._mock_all()
        with p1, p2, p3, p4, p5:
            resp = client.post(
                "/api/progress/update",
                json={"lead_id": "user@example.com", "section": "P1_S1"},
            )

        body = resp.json()
        self.assertEqual(body["hot_lead"]["signal"], "HOT")
        self.assertAlmostEqual(body["hot_lead"]["score"], 80.0, places=1)
        self.assertEqual(body["hot_lead"]["reason"], "completion_and_recency")

    def test_invalid_section_returns_422(self):
        """record_progress_event raising ValueError propagates as HTTP 422."""
        with patch("backend.main.upsert_lead"), \
             patch("backend.main.mark_course_invite_sent"), \
             patch("backend.main.record_progress_event",
                   side_effect=ValueError("Section not found in course registry")):
            resp = client.post(
                "/api/progress/update",
                json={"lead_id": "user@example.com", "section": "BOGUS_SECTION"},
            )

        self.assertEqual(resp.status_code, 422)

    def test_missing_lead_id_returns_422(self):
        resp = client.post("/api/progress/update", json={"section": "P1_S1"})
        self.assertEqual(resp.status_code, 422)

    def test_missing_section_returns_422(self):
        resp = client.post("/api/progress/update", json={"lead_id": "user@example.com"})
        self.assertEqual(resp.status_code, 422)

    def test_empty_body_returns_422(self):
        resp = client.post("/api/progress/update", json={})
        self.assertEqual(resp.status_code, 422)

    def test_event_id_format(self):
        """event_id is always '<lead_id>:<section>'."""
        lead_id, section = "student@colaberry.com", "P3_S3"
        p1, p2, p3, p4, p5 = self._mock_all()
        with p1, p2, p3, p4, p5:
            resp = client.post(
                "/api/progress/update",
                json={"lead_id": lead_id, "section": section},
            )
        self.assertEqual(resp.json()["event_id"], f"{lead_id}:{section}")

    def test_upsert_lead_called_before_record(self):
        """upsert_lead is called before record_progress_event."""
        call_order = []

        def fake_upsert(lead_id, **_):
            call_order.append("upsert")

        def fake_record(**_):
            call_order.append("record")

        with patch("backend.main.upsert_lead", side_effect=fake_upsert), \
             patch("backend.main.mark_course_invite_sent"), \
             patch("backend.main.record_progress_event", side_effect=fake_record), \
             patch("backend.main.compute_course_state"), \
             patch("backend.main.get_lead_status", return_value=_STATUS_EXISTS):
            client.post(
                "/api/progress/update",
                json={"lead_id": "user@example.com", "section": "P1_S1"},
            )

        self.assertEqual(call_order, ["upsert", "record"])


# ---------------------------------------------------------------------------
# Route sanity checks
# ---------------------------------------------------------------------------

class TestRouteSanity(unittest.TestCase):

    def test_get_on_lead_status_returns_405(self):
        resp = client.get("/api/lead/status")
        self.assertEqual(resp.status_code, 405)

    def test_get_on_progress_update_returns_405(self):
        resp = client.get("/api/progress/update")
        self.assertEqual(resp.status_code, 405)

    def test_unknown_route_returns_404(self):
        resp = client.post("/api/nonexistent")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
