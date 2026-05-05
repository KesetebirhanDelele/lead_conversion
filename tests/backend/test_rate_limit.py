"""
tests/backend/test_rate_limit.py

Unit tests for backend/rate_limit.py — pure Python, no FastAPI, no DB.

Tests verify:
  - Requests within the limit are allowed.
  - Requests that exceed the limit are denied.
  - Lead-key and IP-key buckets are independent.
  - Remaining count decrements correctly.
  - Window expiry allows requests again (uses monkeypatch on time.monotonic).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import backend.rate_limit as rl


def _fresh_key() -> str:
    """Return a unique bucket key for each test to avoid cross-test bleed."""
    import uuid
    return f"test:{uuid.uuid4().hex}"


class TestCheckRateLimit:

    def test_first_request_allowed(self):
        key = _fresh_key()
        allowed, remaining = rl.check_rate_limit(key, limit=5)
        assert allowed is True
        assert remaining == 4

    def test_requests_within_limit_all_allowed(self):
        key = _fresh_key()
        for i in range(5):
            allowed, remaining = rl.check_rate_limit(key, limit=5)
            assert allowed is True, f"Request {i+1} should be allowed"

    def test_request_at_limit_denied(self):
        key = _fresh_key()
        for _ in range(5):
            rl.check_rate_limit(key, limit=5)
        allowed, remaining = rl.check_rate_limit(key, limit=5)
        assert allowed is False
        assert remaining == 0

    def test_remaining_decrements(self):
        key = _fresh_key()
        _, r1 = rl.check_rate_limit(key, limit=10)
        _, r2 = rl.check_rate_limit(key, limit=10)
        assert r1 == 9
        assert r2 == 8

    def test_independent_buckets_do_not_interfere(self):
        key_a = _fresh_key()
        key_b = _fresh_key()
        for _ in range(5):
            rl.check_rate_limit(key_a, limit=5)
        # key_a is exhausted; key_b is unaffected.
        allowed, _ = rl.check_rate_limit(key_b, limit=5)
        assert allowed is True

    def test_window_expiry_resets_bucket(self, monkeypatch):
        key = _fresh_key()

        # Fill the bucket using real time.
        t0 = time.monotonic()
        monkeypatch.setattr(rl, "time", type("_T", (), {
            "monotonic": staticmethod(lambda: t0)
        })())

        import importlib
        import backend.rate_limit as fresh_rl  # re-import to pick up monkeypatch

        # Exhaust bucket at t=0.
        for _ in range(3):
            rl.check_rate_limit(key, limit=3)
        allowed, _ = rl.check_rate_limit(key, limit=3)
        assert allowed is False

        # Advance time past the window (default 60s).
        import backend.rate_limit as _rl_module
        monkeypatch.setattr(_rl_module, "time", type("_T", (), {
            "monotonic": staticmethod(lambda: t0 + 61)
        })())

        allowed, _ = _rl_module.check_rate_limit(key, limit=3)
        assert allowed is True


class TestKeyHelpers:

    def test_lead_id_key_prefix(self):
        assert rl.lead_id_key("abc123").startswith("lead:")

    def test_ip_key_prefix(self):
        assert rl.ip_key("192.168.1.1").startswith("ip:")

    def test_keys_are_distinct(self):
        assert rl.lead_id_key("x") != rl.ip_key("x")
