"""
execution/ghl/build_m4_field_payload.py

Builds the LeadConnector custom-field body for the 5 M4 target fields.

Fields pushed to GHL:
    AI Campaign           — campaign identifier (e.g. "FREE_INTRO_AI_V0")
    AI Campaign Name      — human-readable name  (e.g. "Free Intro to AI")
    AI Campaign Value     — lead confidence score 0-100 (string form)
    Last AI Interaction   — ISO-8601 UTC timestamp of last course activity
    Lead Status           — lifecycle state (e.g. "BOOKING_READY")

GHL custom field key names are configurable via environment variables to
accommodate different GHL account setups. Env vars and their defaults:

    GHL_FIELD_AI_CAMPAIGN           = "ai_campaign"
    GHL_FIELD_AI_CAMPAIGN_NAME      = "ai_campaign_name"
    GHL_FIELD_AI_CAMPAIGN_VALUE     = "ai_campaign_value"
    GHL_FIELD_LAST_AI_INTERACTION   = "last_ai_interaction"
    GHL_FIELD_LEAD_STATUS           = "lead_status"

Campaign metadata:
    GHL_CAMPAIGN_ID    = "FREE_INTRO_AI_V0"     (default)
    GHL_CAMPAIGN_NAME  = "Free Intro to AI"     (default)

Input: the internal payload dict (the "payload" key from build_ghl_full_field_payload).

Return shape:
    {
        "customFields": [
            {"key": "<ghl_field_key>", "field_value": "<value>"},
            ...  (5 entries; None values become empty string "")
        ]
    }
"""

from __future__ import annotations

import os

_FIELD_ENV_DEFAULTS: dict[str, str] = {
    "GHL_FIELD_AI_CAMPAIGN":         "ai_campaign",
    "GHL_FIELD_AI_CAMPAIGN_NAME":    "ai_campaign_name",
    "GHL_FIELD_AI_CAMPAIGN_VALUE":   "ai_campaign_value",
    "GHL_FIELD_LAST_AI_INTERACTION": "last_ai_interaction",
    "GHL_FIELD_LEAD_STATUS":         "lead_status",
}


def _ghl_key(env_var: str) -> str:
    return os.environ.get(env_var) or _FIELD_ENV_DEFAULTS[env_var]


def build_m4_field_payload(internal_payload: dict) -> dict:
    """Map internal lead payload to a LeadConnector custom-field body.

    Args:
        internal_payload: The dict from build_ghl_full_field_payload
                          (the "payload" value inside the ok=True result).

    Returns:
        {"customFields": [...]} ready to merge into a LeadConnector PUT body.
    """
    campaign_id   = os.environ.get("GHL_CAMPAIGN_ID")   or "FREE_INTRO_AI_V0"
    campaign_name = os.environ.get("GHL_CAMPAIGN_NAME") or "Free Intro to AI"

    score = internal_payload.get("final_confidence_score")
    score_str        = str(score) if score is not None else ""
    last_interaction = internal_payload.get("last_activity_at") or ""
    lead_status      = internal_payload.get("lead_state")       or ""

    return {
        "customFields": [
            {
                "key":         _ghl_key("GHL_FIELD_AI_CAMPAIGN"),
                "field_value": campaign_id,
            },
            {
                "key":         _ghl_key("GHL_FIELD_AI_CAMPAIGN_NAME"),
                "field_value": campaign_name,
            },
            {
                "key":         _ghl_key("GHL_FIELD_AI_CAMPAIGN_VALUE"),
                "field_value": score_str,
            },
            {
                "key":         _ghl_key("GHL_FIELD_LAST_AI_INTERACTION"),
                "field_value": last_interaction,
            },
            {
                "key":         _ghl_key("GHL_FIELD_LEAD_STATUS"),
                "field_value": lead_status,
            },
        ]
    }
