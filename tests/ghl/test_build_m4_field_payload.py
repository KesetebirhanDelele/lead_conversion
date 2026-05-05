"""
tests/ghl/test_build_m4_field_payload.py

Unit tests for execution/ghl/build_m4_field_payload.py.
No I/O, no DB, no network.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.ghl.build_m4_field_payload import build_m4_field_payload

_PAYLOAD = {
    "final_confidence_score": 82,
    "last_activity_at":       "2026-03-01T11:00:00+00:00",
    "lead_state":             "BOOKING_READY",
}


class TestBuildM4FieldPayload(unittest.TestCase):

    def setUp(self) -> None:
        # Clear any custom field env vars so tests use defaults.
        for v in (
            "GHL_FIELD_AI_CAMPAIGN",
            "GHL_FIELD_AI_CAMPAIGN_NAME",
            "GHL_FIELD_AI_CAMPAIGN_VALUE",
            "GHL_FIELD_LAST_AI_INTERACTION",
            "GHL_FIELD_LEAD_STATUS",
            "GHL_CAMPAIGN_ID",
            "GHL_CAMPAIGN_NAME",
        ):
            os.environ.pop(v, None)

    def test_returns_custom_fields_key(self):
        result = build_m4_field_payload(_PAYLOAD)
        self.assertIn("customFields", result)
        self.assertIsInstance(result["customFields"], list)

    def test_has_exactly_five_fields(self):
        result = build_m4_field_payload(_PAYLOAD)
        self.assertEqual(len(result["customFields"]), 5)

    def test_all_entries_have_key_and_field_value(self):
        for entry in build_m4_field_payload(_PAYLOAD)["customFields"]:
            self.assertIn("key", entry)
            self.assertIn("field_value", entry)

    def test_default_ai_campaign_key(self):
        fields = {e["key"]: e["field_value"] for e in build_m4_field_payload(_PAYLOAD)["customFields"]}
        self.assertIn("ai_campaign", fields)

    def test_default_campaign_id_value(self):
        fields = {e["key"]: e["field_value"] for e in build_m4_field_payload(_PAYLOAD)["customFields"]}
        self.assertEqual(fields["ai_campaign"], "FREE_INTRO_AI_V0")

    def test_default_campaign_name_value(self):
        fields = {e["key"]: e["field_value"] for e in build_m4_field_payload(_PAYLOAD)["customFields"]}
        self.assertEqual(fields["ai_campaign_name"], "Free Intro to AI")

    def test_campaign_value_is_score_string(self):
        fields = {e["key"]: e["field_value"] for e in build_m4_field_payload(_PAYLOAD)["customFields"]}
        self.assertEqual(fields["ai_campaign_value"], "82")

    def test_last_ai_interaction_is_timestamp(self):
        fields = {e["key"]: e["field_value"] for e in build_m4_field_payload(_PAYLOAD)["customFields"]}
        self.assertEqual(fields["last_ai_interaction"], "2026-03-01T11:00:00+00:00")

    def test_lead_status_is_lifecycle_state(self):
        fields = {e["key"]: e["field_value"] for e in build_m4_field_payload(_PAYLOAD)["customFields"]}
        self.assertEqual(fields["lead_status"], "BOOKING_READY")

    def test_none_score_becomes_empty_string(self):
        payload = {**_PAYLOAD, "final_confidence_score": None}
        fields = {e["key"]: e["field_value"] for e in build_m4_field_payload(payload)["customFields"]}
        self.assertEqual(fields["ai_campaign_value"], "")

    def test_none_last_activity_becomes_empty_string(self):
        payload = {**_PAYLOAD, "last_activity_at": None}
        fields = {e["key"]: e["field_value"] for e in build_m4_field_payload(payload)["customFields"]}
        self.assertEqual(fields["last_ai_interaction"], "")

    def test_env_var_overrides_field_key(self):
        os.environ["GHL_FIELD_LEAD_STATUS"] = "custom_lead_status"
        try:
            keys = [e["key"] for e in build_m4_field_payload(_PAYLOAD)["customFields"]]
            self.assertIn("custom_lead_status", keys)
            self.assertNotIn("lead_status", keys)
        finally:
            os.environ.pop("GHL_FIELD_LEAD_STATUS", None)

    def test_env_var_overrides_campaign_id(self):
        os.environ["GHL_CAMPAIGN_ID"] = "MY_CUSTOM_CAMPAIGN"
        try:
            fields = {e["key"]: e["field_value"] for e in build_m4_field_payload(_PAYLOAD)["customFields"]}
            self.assertEqual(fields["ai_campaign"], "MY_CUSTOM_CAMPAIGN")
        finally:
            os.environ.pop("GHL_CAMPAIGN_ID", None)


if __name__ == "__main__":
    unittest.main()
