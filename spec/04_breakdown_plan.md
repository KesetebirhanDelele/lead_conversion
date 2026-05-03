# spec/04_breakdown_plan.md

## 1. Objective

Define a step-by-step implementation plan to build the Lead Conversion System with minimal drift, ensuring all deterministic constraints are preserved.

---

## 2. Execution Strategy

* Build **from core invariants outward**
* Validate **deterministic behavior early**
* Ship **vertical slices** (API + DB + logic together)
* Avoid parallel feature development until core is stable

---

## 3. Phase Breakdown

---

## Phase 1 — Core Domain Setup (FOUNDATION)

### Goal

Establish deterministic core primitives

### Tasks

1. Create `course_registry.py`

   * Define `COURSE_SECTIONS`
   * Define `TOTAL_SECTIONS`

2. Implement section utilities

   * `get_next_section(section)`
   * `is_valid_section(section)`

3. Define core constants

   * HOT threshold (25%)
   * Activity window (48h)

---

### Deliverables

* Section registry (single source of truth)
* Section progression logic

---

### Acceptance Criteria

* Section ordering works via list index only
* Invalid section is rejected
* TOTAL_SECTIONS matches registry length

---

## Phase 2 — Database Layer

### Goal

Implement append-only event store

### Tasks

1. Create `leads` table

   * `lead_id (PK)`
   * `created_at`
   * `lead_signal`
   * `ghl_synced`

2. Create `progress_events` table

   * `event_id (PK)`
   * `lead_id`
   * `section`
   * `occurred_at`

3. Add indexes

   * lead_id
   * section
   * occurred_at

4. Enforce constraints

   * PRIMARY KEY (event_id)
   * INSERT-only behavior (application enforced)

---

### Deliverables

* PostgreSQL schema
* Indexed event table
* Connection pooling config

---

### Acceptance Criteria

* Duplicate insert fails gracefully
* Queries use indexes (verified via EXPLAIN)
* No update/delete operations allowed

---

## Phase 3 — Event Ingestion API

### Goal

Enable safe progress tracking

### Tasks

1. Implement `/api/progress/update`
2. Validate inputs:

   * email format
   * valid section
3. Generate `event_id`
4. Insert event (handle duplicates)
5. Create lead if not exists

---

### Deliverables

* Working ingestion endpoint
* Idempotent event handling

---

### Acceptance Criteria

* Duplicate events do not create new rows
* Invalid inputs rejected (400 / 422)
* Response always explicit (`recorded` or error)
* API latency < 500ms p95

---

## Phase 4 — State Computation Engine

### Goal

Derive accurate lead state

### Tasks

1. Query progress events by lead_id
2. Compute:

   * completed_sections
   * completion_pct
   * last_activity_at
3. Determine:

   * current_section (via registry)
4. Classify lead:

   * HOT / NOT_HOT

---

### Deliverables

* Pure function: `compute_state(events)`

---

### Acceptance Criteria

* Same input → same output (deterministic)
* Correct percentage calculation
* Correct next section
* Correct HOT classification

---

## Phase 5 — Status API

### Goal

Expose computed state

### Tasks

1. Implement `/api/lead/status`
2. Fetch events
3. Compute state
4. Return structured response

---

### Deliverables

* Status endpoint

---

### Acceptance Criteria

* Returns correct state
* Handles non-existent leads
* Response < 500ms p95

---

## Phase 6 — Lead Signal Persistence

### Goal

Persist classification for querying

### Tasks

1. Update `lead_signal` after computation
2. Ensure consistency with derived state

---

### Deliverables

* Persisted lead signal

---

### Acceptance Criteria

* DB value matches computed value
* No stale signal allowed

---

## Phase 7 — Async GHL Integration

### Goal

Trigger external system without blocking

### Tasks

1. Add async job trigger
2. Check:

   * lead_signal == HOT
   * ghl_synced == FALSE
3. Send API request to GHL
4. Update `ghl_synced = TRUE`

---

### Deliverables

* Async integration logic

---

### Acceptance Criteria

* Trigger fires once per lead
* No blocking in API request
* Duplicate prevention verified

---

## Phase 8 — Rate Limiting & Middleware

### Goal

Protect system under load

### Tasks

1. Implement rate limiting (10 req/sec/IP)
2. Add request logging middleware
3. Add error handling middleware

---

### Deliverables

* Middleware layer

---

### Acceptance Criteria

* Excess requests return 429
* Logs generated for all requests
* Errors logged with context

---

## Phase 9 — Observability

### Goal

Ensure system visibility

### Tasks

1. Implement structured logging
2. Log:

   * API calls
   * events
   * errors
3. Add basic metrics tracking

---

### Deliverables

* Logging system

---

### Acceptance Criteria

* Logs readable and structured
* All critical actions logged

---

## Phase 10 — Deployment (Production)

### Goal

Run system on real infrastructure

### Tasks

1. Provision VM (Hetzner)
2. Install:

   * Python
   * PostgreSQL
   * Nginx
3. Deploy FastAPI app
4. Configure reverse proxy
5. Enable HTTPS (certbot)

---

### Deliverables

* Live backend (`https://yourdomain.com`)

---

### Acceptance Criteria

* API reachable via HTTPS
* Stable under test load
* No ngrok dependency

---

## Phase 11 — Dashboards (Minimal)

### Goal

Expose system visibility to users/admin

### Tasks

1. User dashboard (Streamlit)

   * completion %
   * current section

2. Admin dashboard

   * list leads
   * filter HOT leads

---

### Deliverables

* Basic dashboards

---

### Acceptance Criteria

* Data matches API output
* HOT leads visible

---

## Phase 12 — Future Enhancements (Deferred)

### Redis + Queue

* Retry failed events
* Async GHL processing

### Data Pipeline

* Analytics warehouse
* Cohort analysis

### Multi-Course Support

* Dynamic registry

---

## 4. Dependencies

| Component       | Depends On          |
| --------------- | ------------------- |
| State engine    | course_registry, DB |
| APIs            | DB + state engine   |
| GHL integration | state + API         |
| Dashboards      | APIs                |

---

## 5. Risks & Mitigations

### Risk: Event duplication

Mitigation: PRIMARY KEY constraint

---

### Risk: Latency spikes

Mitigation:

* indexing
* async processing

---

### Risk: Incorrect section progression

Mitigation:

* registry-only logic

---

### Risk: External API failure

Mitigation:

* async + future retry queue

---

## 6. Definition of Done

* [ ] All phases implemented sequentially
* [ ] No constraint violations
* [ ] Deterministic outputs verified
* [ ] API latency within limits
* [ ] No duplicate events
* [ ] GHL triggered exactly once
* [ ] Deployment stable under load

---

## 7. Summary

This plan ensures:

* Controlled implementation
* Minimal architectural drift
* Early validation of core invariants

The system MUST be built in this order to preserve correctness.
