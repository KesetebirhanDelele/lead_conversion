"""
backend/auth.py

Bearer token authentication for the API.

Reads valid tokens from the environment variable API_KEYS as a
comma-separated list of opaque tokens, one per client:

    API_KEYS=token_client_ui,token_client_scripts

Any request to a protected endpoint must include:
    Authorization: Bearer <token>

Raises HTTP 401 if the header is missing or the token is not in the set.
Raises HTTP 403 if the key set is empty (misconfiguration guard).
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def _load_valid_tokens() -> frozenset[str]:
    raw = os.environ.get("API_KEYS", "")
    tokens = {t.strip() for t in raw.split(",") if t.strip()}
    return frozenset(tokens)


def require_api_key(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(_bearer)
    ] = None,
) -> str:
    """FastAPI dependency — returns the token on success, raises on failure."""
    valid = _load_valid_tokens()
    if not valid:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "API_KEYS_NOT_CONFIGURED", "message": "Server has no API keys configured."}},
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "MISSING_TOKEN", "message": "Authorization: Bearer <token> header is required."}},
        )
    if credentials.credentials not in valid:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Token is not valid."}},
        )
    return credentials.credentials
