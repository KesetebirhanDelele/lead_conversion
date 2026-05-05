"""
services/worker/scan_scheduler.py

M3 hourly scan → dispatch scheduler.

Runs run_dispatch_cycle() every SCAN_INTERVAL_SECONDS (default 3600 = 1 hour).
Each cycle is fully logged. Exceptions inside a cycle are caught and logged
so the scheduler never exits due to a transient failure.

Usage:
    py -3.12 services/worker/scan_scheduler.py

Environment variables (all optional):
    SCAN_INTERVAL_SECONDS   — override cycle interval (default 3600)
    DISPATCH_COOLDOWN_HOURS — override per-lead cooldown (default 24)
    DISPATCH_LIMIT          — max leads per scan per cycle (default 100)
    DB_PATH                 — SQLite file path (default tmp/app.db)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — supports running as a script from any working directory.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from execution.dispatch.run_dispatch_cycle import run_dispatch_cycle  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [scan_scheduler] %(message)s",
)
logger = logging.getLogger("scan_scheduler")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default


def run_scheduler() -> None:
    interval        = _env_int("SCAN_INTERVAL_SECONDS",   3600)
    cooldown_hours  = _env_int("DISPATCH_COOLDOWN_HOURS", 24)
    limit           = _env_int("DISPATCH_LIMIT",          100)
    db_path         = os.environ.get("DB_PATH") or None

    logger.info(
        "Scheduler starting — interval=%ds cooldown=%dh limit=%d db=%s",
        interval, cooldown_hours, limit, db_path or "default",
    )

    while True:
        now = datetime.now(timezone.utc)
        logger.info("Cycle starting at %s", now.isoformat())
        try:
            result = run_dispatch_cycle(
                now=now,
                cooldown_hours=cooldown_hours,
                limit=limit,
                db_path=db_path,
            )
            logger.info(
                "Cycle complete — scanned=%d dispatched=%d cooldown_skipped=%d "
                "no_action=%d errors=%d ok=%s",
                result["total_scanned"],
                result["dispatched"],
                result["cooldown_skipped"],
                result["no_action"],
                result["errors"],
                result["ok"],
            )
        except Exception as exc:
            logger.error("Cycle failed with unhandled exception: %s", exc, exc_info=True)

        logger.info("Next cycle in %d seconds.", interval)
        time.sleep(interval)


if __name__ == "__main__":
    run_scheduler()
