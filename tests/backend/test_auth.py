"""
tests/backend/test_auth.py

Unit tests for backend/auth.py — no network, no DB, no FastAPI server.

Tests verify:
  - Valid token is accepted.
  - Missing Authorization header → 401.
  - Wrong scheme (Basic) → 401.
  - Token not in set → 401.
  - Empty API_KEYS env var → 403.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend.auth import require_api_key


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="bearer", credentials=token)


class TestRequireApiKey:

    def setup_method(self):
        os.environ["API_KEYS"] = "tok_client1,tok_client2"

    def teardown_method(self):
        os.environ.pop("API_KEYS", None)

    def test_valid_token_accepted(self):
        result = require_api_key(_creds("tok_client1"))
        assert result == "tok_client1"

    def test_second_client_token_accepted(self):
        result = require_api_key(_creds("tok_client2"))
        assert result == "tok_client2"

    def test_missing_credentials_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            require_api_key(None)
        assert exc_info.value.status_code == 401

    def test_wrong_scheme_raises_401(self):
        creds = HTTPAuthorizationCredentials(scheme="Basic", credentials="tok_client1")
        with pytest.raises(HTTPException) as exc_info:
            require_api_key(creds)
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            require_api_key(_creds("not_a_real_token"))
        assert exc_info.value.status_code == 401
        detail = exc_info.value.detail
        assert detail["error"]["code"] == "INVALID_TOKEN"

    def test_empty_api_keys_env_raises_403(self):
        os.environ["API_KEYS"] = ""
        with pytest.raises(HTTPException) as exc_info:
            require_api_key(_creds("tok_client1"))
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail["error"]["code"] == "API_KEYS_NOT_CONFIGURED"

    def test_whitespace_only_api_keys_raises_403(self):
        os.environ["API_KEYS"] = "  ,  "
        with pytest.raises(HTTPException) as exc_info:
            require_api_key(_creds("tok_client1"))
        assert exc_info.value.status_code == 403

    def test_error_detail_shape(self):
        with pytest.raises(HTTPException) as exc_info:
            require_api_key(_creds("bad"))
        detail = exc_info.value.detail
        assert "error" in detail
        assert "code" in detail["error"]
        assert "message" in detail["error"]
