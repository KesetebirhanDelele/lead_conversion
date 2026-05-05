"""
tests/ghl/test_lookup_ghl_contact_by_phone.py

Unit tests for execution/ghl/lookup_ghl_contact_by_phone.py.
HTTP calls are mocked via unittest.mock — no real network traffic.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
import unittest.mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.ghl.lookup_ghl_contact_by_phone import lookup_ghl_contact_by_phone


def _mock_response(body: dict, status: int = 200):
    """Build a minimal mock http.client.HTTPResponse-like object."""
    raw = json.dumps(body).encode()
    mock_resp = unittest.mock.MagicMock()
    mock_resp.read.return_value = raw
    mock_resp.status = status
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = unittest.mock.MagicMock(return_value=False)
    return mock_resp


class TestMissingArgs(unittest.TestCase):

    def test_missing_phone(self):
        result = lookup_ghl_contact_by_phone(
            "", api_key="key", location_id="loc"
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "MISSING_PHONE")

    def test_missing_api_key(self):
        result = lookup_ghl_contact_by_phone(
            "+15550001234", api_key="", location_id="loc"
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "MISSING_API_KEY")

    def test_missing_location_id(self):
        result = lookup_ghl_contact_by_phone(
            "+15550001234", api_key="key", location_id=""
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "MISSING_LOCATION_ID")


class TestSuccessfulLookup(unittest.TestCase):

    def _call(self, body: dict) -> dict:
        mock_resp = _mock_response(body)
        with unittest.mock.patch(
            "urllib.request.urlopen", return_value=mock_resp
        ):
            return lookup_ghl_contact_by_phone(
                "+15550001234",
                api_key="test_key",
                location_id="loc123",
            )

    def test_contact_found_returns_ok_true(self):
        result = self._call({"contacts": [{"id": "abc123"}]})
        self.assertTrue(result["ok"])

    def test_contact_found_returns_contact_id(self):
        result = self._call({"contacts": [{"id": "abc123"}]})
        self.assertEqual(result["contact_id"], "abc123")

    def test_empty_contacts_returns_no_match(self):
        result = self._call({"contacts": []})
        self.assertTrue(result["ok"])
        self.assertIsNone(result["contact_id"])
        self.assertEqual(result["reason"], "NO_MATCH")

    def test_contacts_key_absent_returns_no_match(self):
        result = self._call({})
        self.assertTrue(result["ok"])
        self.assertIsNone(result["contact_id"])
        self.assertEqual(result["reason"], "NO_MATCH")

    def test_contact_id_blank_returns_no_match(self):
        result = self._call({"contacts": [{"id": ""}]})
        self.assertTrue(result["ok"])
        self.assertIsNone(result["contact_id"])
        self.assertEqual(result["reason"], "NO_MATCH")

    def test_first_contact_is_used_when_multiple(self):
        result = self._call({"contacts": [{"id": "first"}, {"id": "second"}]})
        self.assertEqual(result["contact_id"], "first")

    def test_request_includes_bearer_auth(self):
        mock_resp = _mock_response({"contacts": [{"id": "cid"}]})
        captured = {}
        orig_urlopen = __import__("urllib.request", fromlist=["urlopen"]).urlopen

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return mock_resp

        with unittest.mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            lookup_ghl_contact_by_phone(
                "+15550001234",
                api_key="my_token",
                location_id="loc",
            )

        auth = captured["headers"].get("Authorization") or captured["headers"].get("authorization")
        self.assertIsNotNone(auth)
        self.assertIn("my_token", auth)


if __name__ == "__main__":
    unittest.main()
