"""
backend/rate_limit.py

In-memory sliding-window rate limiter.

Two tiers:
  1. Per lead_id  — keyed on the lead_id field from the request body.
  2. Per IP       — fallback when lead_id is absent (e.g. /health, unknown body).

Limits (configurable via env vars, defaults shown):
  RATE_LIMIT_LEAD   — max requests per lead_id per window   (default 60)
  RATE_LIMIT_IP     — max requests per IP per window         (default 120)
  RATE_LIMIT_WINDOW — window length in seconds               (default 60)

Thread-safety: a single threading.Lock guards the shared deque map.
This is adequate for a single-process uvicorn worker. If you scale to
multiple workers later, swap for Redis-backed counters.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_windows: dict[str, deque[float]] = defaultdict(deque)


def _limit(key: str) -> int:
    """Read per-key default from env, falling back to provided default."""
    if key == "RATE_LIMIT_LEAD":
        return int(os.environ.get("RATE_LIMIT_LEAD", "60"))
    if key == "RATE_LIMIT_IP":
        return int(os.environ.get("RATE_LIMIT_IP", "120"))
    return 60


def _window_seconds() -> int:
    return int(os.environ.get("RATE_LIMIT_WINDOW", "60"))


def check_rate_limit(bucket_key: str, limit: int) -> tuple[bool, int]:
    """
    Check whether *bucket_key* has exceeded *limit* in the current window.

    Returns:
        (allowed, remaining)
        allowed   — True if the request may proceed
        remaining — requests still allowed in this window
    """
    now = time.monotonic()
    window = _window_seconds()
    cutoff = now - window

    with _lock:
        dq = _windows[bucket_key]
        # Drop timestamps outside the window.
        while dq and dq[0] <= cutoff:
            dq.popleft()

        count = len(dq)
        if count >= limit:
            return False, 0

        dq.append(now)
        return True, limit - count - 1


def lead_id_key(lead_id: str) -> str:
    return f"lead:{lead_id}"


def ip_key(ip: str) -> str:
    return f"ip:{ip}"
