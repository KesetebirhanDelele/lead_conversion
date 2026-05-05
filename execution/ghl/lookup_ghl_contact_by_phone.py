"""
execution/ghl/lookup_ghl_contact_by_phone.py

Phone-first contact lookup via the LeadConnector search endpoint.

LeadConnector search API:
    GET {base_url}/contacts/?phone={phone}&locationId={location_id}
    Authorization: Bearer <api_key>
    Version: 2021-07-28

Expected response (JSON):
    Match:    {"contacts": [{"id": "<contact_id>", ...}, ...]}
    No match: {"contacts": []}

Return shapes
-------------
Contact found:
    {"ok": True, "contact_id": "<non-empty string>"}

No match:
    {"ok": True, "contact_id": None, "reason": "NO_MATCH"}

Missing required argument:
    {"ok": False, "reason": "MISSING_PHONE"}
    {"ok": False, "reason": "MISSING_API_KEY"}
    {"ok": False, "reason": "MISSING_LOCATION_ID"}

Raises
------
urllib.error.HTTPError:  Non-2xx response from LeadConnector.
urllib.error.URLError:   Network-level failure (timeout, DNS, refused).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

_API_VERSION = "2021-07-28"


def lookup_ghl_contact_by_phone(
    phone: str,
    *,
    api_key: str,
    location_id: str,
    base_url: str = "https://services.leadconnectorhq.com",
    timeout: int = 10,
) -> dict:
    """Look up a GHL contact by phone via the LeadConnector search endpoint.

    Args:
        phone:       Phone number to search (e.g. "+15550001234").
        api_key:     GHL private integration token (Bearer auth).
        location_id: GHL location / sub-account ID.
        base_url:    LeadConnector API base URL. Defaults to public API.
        timeout:     Socket timeout in seconds. Defaults to 10.

    Returns:
        dict — see module docstring for all return shapes.

    Raises:
        urllib.error.HTTPError: Non-2xx HTTP response from LeadConnector.
        urllib.error.URLError:  Network failure.
    """
    phone       = (phone       or "").strip()
    api_key     = (api_key     or "").strip()
    location_id = (location_id or "").strip()

    if not phone:
        return {"ok": False, "reason": "MISSING_PHONE"}
    if not api_key:
        return {"ok": False, "reason": "MISSING_API_KEY"}
    if not location_id:
        return {"ok": False, "reason": "MISSING_LOCATION_ID"}

    params = urllib.parse.urlencode({"phone": phone, "locationId": location_id})
    url = f"{str(base_url).rstrip('/')}/contacts/?{params}"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
            "Version":       _API_VERSION,
        },
        method="GET",
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read())

    contacts = body.get("contacts") or []
    if not contacts:
        return {"ok": True, "contact_id": None, "reason": "NO_MATCH"}

    contact_id = (contacts[0].get("id") or "").strip() or None
    if not contact_id:
        return {"ok": True, "contact_id": None, "reason": "NO_MATCH"}

    return {"ok": True, "contact_id": contact_id}
