# spec/01_requirements.md

## 1. Functional Requirements

### 1.1 Lead Creation & Identification

* System MUST identify a lead using **email (input)** and map it to an internal `lead_id` (UUID)
* System MUST generate `lead_id` as a UUID (backend only)
* System MUST create a lead record on first valid interaction

#### Validation

* `email` MUST be a valid email format
* Email MUST be normalized before processing:

  * `email = email.strip().lower()`
* Requests without `email` MUST be rejected with HTTP 400

#### Security

* Email MUST be encrypted before storage
* Email MUST NOT be used as:

  * primary key
  * foreign key
  * event identifier

---

### 1.2 Progress Event Ingestion

* System MUST accept progress events via API
* Each event MUST contain:

  * `email`
  * `section`

#### Behavior

* System MUST resolve `email → lead_id (UUID)`
* System MUST generate:

  ```
  event_id = lead_id + ":" + section
  ```
* System MUST enforce idempotency:

  * Duplicate events MUST NOT create new records
* System MUST store events as append-only

#### Validation

* Invalid section → HTTP 422
* Missing fields → HTTP 400

---

### 1.3 Section Progression

* System MUST determine next section using explicit list ordering from `course_registry.py`
* System MUST NOT:

  * Sort sections
  * Infer order via string comparison

---

### 1.4 State Computation

System MUST compute the following on every relevant request:

* `completed_sections` = count of unique sections
* `completion_pct` = (completed_sections / TOTAL_SECTIONS) * 100
* `last_activity_at` = max(timestamp)
* `current_section` = next uncompleted section

#### Performance

* State computation latency MUST be < 200ms (p95)

---

### 1.5 Lead Classification

System MUST classify leads deterministically:

IF completion_pct >= 25 AND (now - last_activity_at) <= 48 hours
THEN lead_signal = HOT
ELSE lead_signal = NOT_HOT

#### Requirements

* Classification MUST be recomputed on every event
* Classification MUST be deterministic (same input → same output)

---

### 1.6 Lead State Persistence

* System MUST persist `lead_signal` in `leads` table
* System MUST persist `ghl_synced BOOLEAN DEFAULT FALSE`

#### Constraint

* Persisted state MUST NOT be treated as source of truth
* Derived state MUST override persisted inconsistencies

---

### 1.7 API: Get Lead Status

**Endpoint:** `POST /api/lead/status`

#### Request

```json
{
  "email": "user@example.com"
}
```

---

#### Processing

* System MUST normalize email
* System MUST resolve email → lead_id
* If no lead exists:

  * return `lead_exists = false`

---

#### Response

```json
{
  "lead_exists": true,
  "course_state": {
    "completion_pct": 22.22,
    "current_section": "P1_S3",
    "last_activity_at": "ISO-8601",
    "lead_signal": "NOT_HOT"
  }
}
```

---

#### Requirements

* MUST return computed state (not stale DB values)
* MUST respond within 500ms (p95 < 800ms)

---

### 1.8 API: Progress Update

**Endpoint:** `POST /api/progress/update`

#### Request

```json
{
  "email": "user@example.com",
  "section": "P1_S1"
}
```

---

#### Behavior

* MUST normalize email
* MUST resolve or create `lead_id`
* MUST validate section exists in `COURSE_SECTIONS`
* MUST insert event if not duplicate
* MUST recompute state
* MUST update `lead_signal`
* MUST return explicit success/failure

---

#### Response

```json
{
  "status": "recorded"
}
```

---

### 1.9 GHL Integration Trigger

* System MUST trigger GHL sync when:

  * `lead_signal == HOT`
  * `ghl_synced == FALSE`

#### Behavior

* MUST execute asynchronously (non-blocking)
* After successful sync:

  * Set `ghl_synced = TRUE`

#### Constraint

* System MUST NOT send duplicate GHL requests for same lead

---

### 1.10 User Flow Support

System MUST support:

#### New User

* Create lead (UUID generated)
* Start at first section

---

#### Returning User

* Resolve email → lead_id
* Fetch state
* Resume from `current_section`

---

#### Converted User

* Mark as HOT
* Trigger external integration

---

## 2. Non-Functional Requirements

### 2.1 Performance

* ALL API endpoints MUST respond within:

  * 500ms (p95 < 800ms)

* System MUST avoid:

  * blocking I/O
  * heavy computation in request cycle

---

### 2.2 Availability

* System uptime MUST be ≥ 99.9%

---

### 2.3 Consistency

* State MUST always reflect underlying events
* System MUST be deterministic under concurrency

---

### 2.4 Scalability

ASSUMPTION: MVP scale ≤ 10,000 leads

* System MUST handle:

  * ≥ 50 requests/sec sustained
  * ≥ 100,000 total events

---

### 2.5 Reliability

* Event ingestion MUST be durable
* No data loss on successful API response
* Failures MUST be logged

---

### 2.6 Security

* All endpoints MUST validate input
* System MUST NOT expose database directly
* HTTPS MUST be enforced in production
* API authentication REQUIRED via API key
* Email MUST be encrypted before storage
* Email MUST be normalized before encryption

---

### 2.7 Observability

System MUST log:

* API calls
* Progress events
* Errors
* Authentication results

---

## 3. Database Requirements (PostgreSQL)

### 3.1 Schema Constraints

`progress_events` table MUST have:

* `event_id` PRIMARY KEY
* `lead_id` (UUID) INDEX
* `section` INDEX
* `occurred_at` INDEX

---

### 3.2 Data Rules

* INSERT ONLY (append-only)
* NO UPDATE
* NO DELETE

---

### 3.3 Connection Management

* MUST use connection pooling
* pool_size: 10
* max_overflow: 5

---

## 4. Idempotency Requirements

* ALL progress updates MUST be idempotent

Implementation:

```
event_id = f"{lead_id}:{section}"
```

Enforcement:

* PRIMARY KEY constraint

---

## 5. Rate Limiting

* System MUST enforce rate limiting:

  * Max 10 requests / second / IP

Implementation:

* FastAPI middleware OR nginx

---

## 6. Async Processing Requirements

* External API calls MUST NOT block request cycle
* GHL sync MUST be executed asynchronously (future activation)

---

## 7. Retry & Failure Handling

### Current (MVP)

* API MUST return explicit success/failure
* Failures MUST be logged
* NO retry mechanism

---

### Future (Production)

ASSUMPTION: Redis not required in MVP
Alternative: Introduce Redis queue

* Failed events MUST be retried via queue
* External integrations MUST be retriable

---

## 8. Time Requirements

* ALL timestamps MUST be UTC
* MUST be timezone-aware
* MUST be generated by backend

---

## 9. Constraints

### Must

* Deterministic logic only
* Append-only event model
* Explicit section ordering
* Async external calls
* Indexed DB queries
* UUID-based identity

---

### Must Not

* Use machine learning
* Modify or delete events
* Use client timestamps
* Use email as system identifier
* Block API with external calls

---

### Preferences

* FastAPI (async)
* PostgreSQL
* SQLAlchemy

---

### Trade-offs

* Simplicity over flexibility
* Determinism over adaptability
* Latency control over feature richness
* Security over convenience (UUID + encryption)

---

### Escalation Triggers

* API latency > 800ms p95
* Duplicate event rate > 1%
* GHL duplicate sends detected
* Event ingestion failures > 0.1%

---

## 10. Definition of Done

* [ ] UUID identity implemented
* [ ] Email encryption implemented
* [ ] Email normalization enforced
* [ ] API latency meets 500ms p95 requirement
* [ ] DB indexes implemented
* [ ] Connection pooling configured
* [ ] Idempotency enforced via PK
* [ ] Rate limiting active
* [ ] Async processing ready (non-blocking design)
* [ ] Logs implemented for all critical paths
* [ ] UTC enforced system-wide
* [ ] No blocking operations in request cycle
