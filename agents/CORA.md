# CORA — Colaberry Outreach & Recommendation Agent

**Role:** Decision engine for student lead outreach. Recommends one action per lead per evaluation cycle.

**Owned by:** Colaberry engineering  
**Runtime:** Deterministic Python (execution/decision/). Not an LLM at runtime.  
**Code:** `execution/decision/get_cora_recommendation.py`

---

## Behavioral Contract

CORA reads lead state from SQLite and returns a single recommended action. It never writes to the database, never calls external APIs, and never makes probabilistic decisions. Every output is reproducible given the same inputs.

---

## Inputs

| Field | Source |
|-------|--------|
| `lead_id` | Caller |
| `invite_sent` | `course_invites` table |
| `completion_pct` | `course_state` table |
| `last_activity_at` | `course_state` table |
| `avg_quiz_score` | `course_state` table |
| `hot_signal` | Derived from `compute_hot_lead_signal` |
| `lifecycle_state` | Derived from `derive_lead_lifecycle_state` |

---

## Output — Recommendation

```json
{
  "lead_id":     "...",
  "event_type":  "SEND_INVITE | NUDGE_PROGRESS | NO_ACTION",
  "priority":    "HIGH | MEDIUM | LOW",
  "reason_codes": ["NOT_INVITED", "STALE_PROGRESS", ...],
  "evaluated_at": "ISO-8601 UTC"
}
```

### Event Types

| Event | When |
|-------|------|
| `SEND_INVITE` | Lead exists but has never received a course invite |
| `NUDGE_PROGRESS` | Lead was invited, started the course, but stalled (stale activity) |
| `NO_ACTION` | Lead is active, completed, or in cooldown |

---

## Safety Rules

- **Read-only.** CORA never writes to any table.
- **Deterministic.** Given the same DB state and `now`, always returns the same output.
- **No LLM calls.** All logic is rule-based Python.
- **Cooldown enforced externally.** The dispatch cycle (`run_dispatch_cycle.py`) checks cooldown before acting on CORA's recommendation. CORA itself does not know about prior dispatches.

---

## Identity Principles

CORA is not a chatbot. It has no personality. It does not communicate with leads directly. All student-facing communication is handled by the student portal (Streamlit) and downstream GHL workflows that CORA triggers by recommendation.

---

## Escalation

When a lead's state is ambiguous or outside CORA's decision rules, it returns `NO_ACTION` rather than guessing. Unresolvable leads are logged with `reason_codes: ["DECISION_DEFERRED"]`.
