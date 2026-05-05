"""
execution/dispatch/run_dispatch_cycle.py

M3 dispatch orchestrator: run all scans, check cooldown, shadow-dispatch.

One cycle:
  1. Run all 5 read-only scans → collect unique lead_ids that need attention.
  2. For each unique lead, call get_cora_recommendation → authoritative event_type.
  3. Check cooldown (24h default) for that lead + event_type.
  4. If eligible: write SHADOW record to sync_records.
  5. Return a summary dict.

Shadow mode is intentional for M3 — no outbound requests are made.
When Cory / GHL endpoints are live the shadow writes become real dispatches.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from execution.decision.get_cora_recommendation import get_cora_recommendation
from execution.dispatch.check_cooldown import is_on_cooldown
from execution.dispatch.write_dispatch_record import write_shadow_record
from services.worker.run_all_scans import run_all_scans

logger = logging.getLogger(__name__)


def run_dispatch_cycle(
    *,
    now: datetime | None = None,
    cooldown_hours: int = 24,
    limit: int = 100,
    db_path: str | None = None,
) -> dict:
    """Run one full scan → shadow-dispatch cycle.

    Args:
        now:            Reference UTC datetime for all time calculations.
                        Defaults to real UTC now when None (production path).
                        Tests must always supply this.
        cooldown_hours: Hours after a SENT/SHADOW record before re-dispatching.
        limit:          Max leads per scan.
        db_path:        SQLite path; defaults to tmp/app.db.

    Returns:
        {
            "ok":               bool,
            "generated_at":     ISO-8601 UTC,
            "total_scanned":    int,   # unique leads across all scans
            "dispatched":       int,   # new SHADOW records written
            "cooldown_skipped": int,   # leads within cooldown window
            "errors":           int,   # leads that raised an exception
            "no_action":        int,   # recommendation was NO_ACTION
        }
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # 1. SCAN — collect unique lead_ids across all scan results.
    scan_output = run_all_scans(limit=limit, db_path=db_path)
    lead_ids: set[str] = set()
    for result in scan_output["results"]:
        lead_ids.update(result.get("lead_ids", []))

    logger.info("run_dispatch_cycle: %d unique lead(s) surfaced by scans.", len(lead_ids))

    dispatched       = 0
    cooldown_skipped = 0
    no_action        = 0
    errors           = 0

    # 2. PER-LEAD DISPATCH
    for lead_id in lead_ids:
        try:
            rec = get_cora_recommendation(lead_id, now=now, db_path=db_path)
        except ValueError:
            logger.warning("run_dispatch_cycle: lead %s not found — skipping.", lead_id)
            errors += 1
            continue
        except Exception as exc:
            logger.error("run_dispatch_cycle: error fetching recommendation for %s: %s", lead_id, exc)
            errors += 1
            continue

        event_type = rec["event_type"]

        if event_type == "NO_ACTION":
            no_action += 1
            continue

        # 3. COOLDOWN CHECK
        if is_on_cooldown(lead_id, event_type, cooldown_hours=cooldown_hours, now=now, db_path=db_path):
            logger.debug("run_dispatch_cycle: %s [%s] — within cooldown, skipping.", lead_id, event_type)
            cooldown_skipped += 1
            continue

        # 4. SHADOW DISPATCH
        try:
            write_shadow_record(lead_id, event_type, rec, now=now, db_path=db_path)
            logger.info("run_dispatch_cycle: SHADOW dispatched %s → %s.", lead_id, event_type)
            dispatched += 1
        except Exception as exc:
            logger.error("run_dispatch_cycle: failed writing shadow record for %s: %s", lead_id, exc)
            errors += 1

    logger.info(
        "run_dispatch_cycle complete: dispatched=%d cooldown_skipped=%d no_action=%d errors=%d",
        dispatched, cooldown_skipped, no_action, errors,
    )
    return {
        "ok":               errors == 0,
        "generated_at":     now.isoformat(),
        "total_scanned":    len(lead_ids),
        "dispatched":       dispatched,
        "cooldown_skipped": cooldown_skipped,
        "no_action":        no_action,
        "errors":           errors,
    }
