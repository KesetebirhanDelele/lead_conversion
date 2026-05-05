# MILESTONES — Lead Conversion System
**Last updated:** 2026-05-04  
**Assessed by:** Full repo audit  

---

## Milestone 0 — Foundation
**Status: COMPLETE**

| Component | Status | Key Files |
|-----------|--------|-----------|
| SQLite schema (8 tables) | ✅ | `execution/db/sqlite.py` |
| Lead upsert + invite | ✅ | `execution/leads/upsert_lead.py`, `mark_course_invite_sent.py` |
| Progress recording + course state | ✅ | `execution/progress/record_progress_event.py`, `compute_course_state.py` |
| HOT Lead Signal (3-gate rule engine, 48h window) | ✅ | `execution/leads/compute_hot_lead_signal.py` |
| FastAPI backend (2 endpoints) | ✅ | `backend/main.py` |
| Student Portal (Streamlit, 3 portals) | ✅ | `ui/student_portal/`, `ui/instructor_portal/`, `ui/dev_portal/` |
| DB init script | ✅ | `scripts/init_db.py` |
| Core unit tests (40+ files) | ✅ | `tests/` |

---

## Milestone 1 — Correctness
**Status: PARTIAL**  
**Blocking:** 3 gaps must close before any production use.

| # | Gap | File | Action |
|---|-----|------|--------|
| 1.1 | `finalize_on_completion` not called from student portal | `ui/student_portal/pages/1_Student_Course_Player.py` | Wire call at section complete step |
| 1.2 | Reflection scoring override uses wrong values (lines 339–346) | `execution/leads/compute_lead_temperature.py` | Remove override block; trust `_reflection_points()` |
| 1.3 | `invite_generated_at` never persisted | `execution/leads/mark_course_invite_sent.py` | Write timestamp to column on insert |

---

## Milestone 2 — API Hardening
**Status: NOT STARTED**  
**Callers:** UI + internal scripts only. No GPT direct calls. No Cory webhook.  
**Auth:** Bearer token, separate keys per client (stored in env vars).  
**Rate limiting:** Per `lead_id` primary; fallback per IP.

| # | Item | File | Notes |
|---|------|------|-------|
| 2.1 | Bearer token auth middleware | `backend/main.py` | Separate key per client; reject 401 if missing/invalid |
| 2.2 | Standardized error responses | `backend/main.py` | `{"error": {"code": "...", "message": "..."}}` |
| 2.3 | `/health` endpoint | `backend/main.py` | Returns 200 + `{"status": "ok"}` |
| 2.4 | Request logging | `backend/main.py` | Log method, path, lead_id, response code, duration |
| 2.5 | Rate limiting per lead_id + IP | `backend/main.py` | Per lead_id primary; per IP fallback |

---

## Milestone 3 — Scan → Action Dispatch
**Status: PARTIAL** — Scans implemented (read-only); dispatch not wired.  
**Scan schedule:** Every 1 hour.  
**Dispatch mode:** Auto (no human approval step).  
**Cooldown:** 24h per lead per event type.  
**Cory:** Shadow mode until endpoint provided.

| # | Item | File | Notes |
|---|------|------|-------|
| 3.1 | Scan workers wired to dispatch functions | `execution/orchestration/` | Map scan result → Cora event type |
| 3.2 | Cooldown check (24h per lead per event) | `execution/leads/check_dispatch_cooldown.py` (new) | Query sync_records; block re-dispatch within 24h |
| 3.3 | Cory dispatch (shadow mode) | `execution/events/dispatch_cory_webhook.py` | Log event; skip HTTP POST until endpoint provided |
| 3.4 | Hourly scheduler | `services/worker/scan_scheduler.py` (new) | Run all scans every 60 min; configurable via env |
| 3.5 | Scan → GHL dispatch | `execution/ghl/write_ghl_contact_fields.py` | Trigger GHL writeback when scan flags NEEDS_SYNC |

---

## Milestone 4 — GHL Lead Status Push
**Status: CODE COMPLETE; LIVE TEST PENDING**  
**Shadow mode active** — build/log payloads, do not POST to GHL until shadow mode is lifted.  
**GHL API:** LeadConnector endpoint.  
**Contact lookup:** By phone number.  
**Fields to push:** AI Campaign, AI Campaign Name, AI Campaign Value, Last AI Interaction, Lead Status.

| # | Item | File | Notes |
|---|------|------|-------|
| 4.1 | Shadow mode flag + behavior | `execution/ghl/write_ghl_contact_fields.py` | ✅ `GHL_SHADOW_MODE` env var; writes SHADOW to sync_records, skips HTTP POST |
| 4.2 | Shadow mode env var | `.env` + `.env.example` | ✅ `GHL_SHADOW_MODE=true` + `GHL_LOCATION_ID`, `GHL_CAMPAIGN_ID`, `GHL_CAMPAIGN_NAME`, field key overrides |
| 4.3 | Phone-based contact lookup | `execution/ghl/lookup_ghl_contact_by_phone.py` | ✅ Phone-first LeadConnector search; falls back to stored ID + legacy lookup URL |
| 4.4 | Field mapping to LeadConnector schema | `execution/ghl/build_m4_field_payload.py` | ✅ 5-field customFields payload; field keys configurable via env vars |
| 4.5 | Shadow log viewer | `ui/dev_portal/pages/2_Sync_Outbox_Viewer.py` | ✅ SHADOW added to status filter dropdown |
| 4.6 | Bearer auth header | `execution/ghl/write_ghl_contact_fields.py` | ✅ Already wired |
| 4.7 | Live GHL sandbox test | Manual | Requires GHL_API_KEY + GHL_LOCATION_ID + GHL_API_URL + test contact with phone; set GHL_SHADOW_MODE=false |

---

## Milestone 5 — Advanced Scoring / Instrumentation
**Status: COMPLETE**  
**Quiz granularity:** Per quiz + per section (not per question).  
**Reflection confidence:** Student self-rated via UI dropdown (not AI-derived).  
**DB:** Migrate from SQLite to PostgreSQL — implement locally first, then Hetzner.  
**Course content:** Use existing repo structure; real content added by user later.

| # | Item | File | Notes |
|---|------|------|-------|
| 5.1 | Quiz score persistence (per quiz + section) | `execution/progress/record_quiz_score.py` | ✅ quiz_scores table; upsert per quiz per section per lead |
| 5.2 | Avg quiz score wired into course state | `execution/progress/compute_course_state.py` | ✅ avg_quiz_score + avg_quiz_attempts computed and stored on every recompute |
| 5.3 | Reflection confidence UI (student self-rated) | `ui/student_portal/pages/1_Student_Course_Player.py` | ✅ 1-5 selectbox already in place; `_resolve_reflection_confidence` converts to H/M/L |
| 5.4 | Temperature score uses real quiz + reflection | `execution/leads/get_lead_status.py` | ✅ `get_lead_status` returns `temperature` dict with real quiz + lifecycle signals |
| 5.5 | PostgreSQL migration (local first) | `execution/db/postgres.py` | ✅ psycopg2 backend with ?→%s adapter; env-switched via DATABASE_URL in sqlite.connect() |
| 5.6 | Course content structure ready | `course_content/FREE_INTRO_AI_V0/` | ✅ 9 sections, 5 quiz files, course_map.json — placeholder content in place |
| 5.7 | Agent personas defined | `agents/CORA.md` | ✅ Behavioral spec: inputs, outputs, event types, safety rules |

---

## Milestone 6 — Production Readiness
**Status: NOT STARTED**  
**Deployment target:** Hetzner VPS.  
**Domain:** TBD.  
**DB + Course content:** Moved to M5.

| # | Item | Notes |
|---|------|-------|
| 6.1 | E2E browser tests (Playwright) | Cover student portal: login → section → quiz → complete |
| 6.2 | Instructor Dashboard (real views) | Current page is skeleton only |
| 6.3 | Docker + docker-compose | Backend (FastAPI) + Student portal (Streamlit) as separate services |
| 6.4 | CI pipeline | GitHub Actions: lint → test → build on PR |
| 6.5 | Hetzner VPS deploy config | Systemd units or docker-compose up -d; env file injection |
| 6.6 | Domain + TLS (TBD) | HTTPS via Caddy or nginx reverse proxy; CORS config |
| 6.7 | Production smoke test | Hit /health, run one full lead flow, verify DB + GHL shadow log |

---

## Progress Snapshot

```
M0 Foundation      ████████████ COMPLETE
M1 Correctness     ████████░░░░ 3 gaps remaining
M2 API Hardening   ░░░░░░░░░░░░ NOT STARTED
M3 Scan→Dispatch   ████░░░░░░░░ Scans done, dispatch missing
M4 GHL Push        ████████████ COMPLETE (shadow mode; live test pending)
M5 Instrumentation ████████████ COMPLETE
M6 Production      ░░░░░░░░░░░░ NOT STARTED
```

---

## Decision Log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-05-04 | HOT signal activity window set to 48h (not 7 days per original directive) | User instruction: "Use 48 hrs" |
| 2026-05-04 | GHL send in shadow mode | Build + log payload; do not POST until shadow mode lifted |
| 2026-05-04 | No GHL/Cory in MVP backend | User instruction: local tests only, no external calls |
| 2026-05-04 | GPT Actions replaced by Streamlit UI | Eliminates confirmation popups; UI calls OpenAI SDK directly |
| 2026-05-04 | GHL lookup by phone number | LeadConnector endpoint; fields: AI Campaign, AI Campaign Name, AI Campaign Value, Last AI Interaction, Lead Status |
| 2026-05-04 | M3 scan schedule: 1h, auto-dispatch, 24h cooldown | User confirmed |
| 2026-05-04 | M5 quiz granularity: per quiz + section | Not per question |
| 2026-05-04 | M5 reflection confidence: student self-rated dropdown | Not AI-derived |
| 2026-05-04 | M5 Postgres: local first, then Hetzner | Moved from M6 |
| 2026-05-04 | M6 deployment: Hetzner VPS | Domain TBD |
