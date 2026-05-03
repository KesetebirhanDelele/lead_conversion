# spec/02_acceptance_criteria.md

## 1. Lead Creation

### 1.1 Valid Lead Creation

**Given**

* A request with a valid `lead_id` (email)

**When**

* The system receives the first `/api/progress/update` request

**Then**

* A new lead record MUST be created
* The event MUST be stored
* Response MUST be `{ "status": "recorded" }`

---

### 1.2 Missing Lead ID

**Given**

* A request without `lead_id`

**When**

* `/api/progress/update` is called

**Then**

* System MUST return HTTP 400
* No data MUST be written

---

## 2. Progress Event Handling

### 2.1 Valid Event Recording

**Given**

* A valid `lead_id`
* A valid `section` in `COURSE_SECTIONS`

**When**

* `/api/progress/update` is called

**Then**

* Event MUST be inserted into `progress_events`
* `event_id = lead_id:section`
* Response MUST be `{ "status": "recorded" }`

---

### 2.2 Duplicate Event (Idempotency)

**Given**

* Event already exists for:

  * `lead_id = X`
  * `section = P1_S1`

**When**

* Same request is sent again

**Then**

* No new row MUST be inserted
* System MUST return `{ "status": "recorded" }`
* System state MUST remain unchanged

---

### 2.3 Invalid Section

**Given**

* A `section` not present in `COURSE_SECTIONS`

**When**

* `/api/progress/update` is called

**Then**

* System MUST return HTTP 422
* No event MUST be stored

---

## 3. State Computation

### 3.1 Completion Percentage

**Given**

* TOTAL_SECTIONS = 9
* Lead completed: P1_S1, P1_S2, P1_S3

**When**

* `/api/lead/status` is called

**Then**

* `completion_pct = 33.33`

---

### 3.2 Current Section Progression

**Given**

* Completed sections:

  * P1_S1, P1_S2

**When**

* State is computed

**Then**

* `current_section = P1_S3`

---

### 3.3 Last Activity Calculation

**Given**

* Events with timestamps:

  * T1, T2, T3

**When**

* State is computed

**Then**

* `last_activity_at = max(T1, T2, T3)`

---

## 4. Lead Classification

### 4.1 NOT_HOT (Low Completion)

**Given**

* `completion_pct = 20`
* `last_activity_at` within 48 hours

**When**

* State is computed

**Then**

* `lead_signal = NOT_HOT`

---

### 4.2 NOT_HOT (Stale Activity)

**Given**

* `completion_pct = 40`
* `last_activity_at > 48 hours`

**When**

* State is computed

**Then**

* `lead_signal = NOT_HOT`

---

### 4.3 HOT Lead

**Given**

* `completion_pct = 30`
* `last_activity_at <= 48 hours`

**When**

* State is computed

**Then**

* `lead_signal = HOT`

---

## 5. API Behavior

### 5.1 Status API Response

**Given**

* A valid lead exists

**When**

* `/api/lead/status` is called

**Then**

* System MUST return:

  * `completion_pct`
  * `current_section`
  * `last_activity_at`
  * `lead_signal`

---

### 5.2 Non-Existent Lead

**Given**

* `lead_id` does not exist

**When**

* `/api/lead/status` is called

**Then**

* `lead_exists = false`
* No error MUST be thrown

---

### 5.3 API Performance

**Given**

* Normal system load

**When**

* Any API endpoint is called

**Then**

* Response time MUST be:

  * ≤ 500ms (p95)
  * ≤ 800ms (max acceptable)

---

## 6. GHL Integration

### 6.1 Trigger on HOT

**Given**

* Lead becomes HOT
* `ghl_synced = FALSE`

**When**

* State is computed

**Then**

* System MUST trigger GHL API call asynchronously

---

### 6.2 Prevent Duplicate Sync

**Given**

* `ghl_synced = TRUE`

**When**

* Lead remains HOT

**Then**

* System MUST NOT send another GHL request

---

## 7. Concurrency & Idempotency

### 7.1 Rapid Duplicate Requests

**Given**

* Multiple identical requests sent simultaneously

**When**

* `/api/progress/update` is called

**Then**

* Only one event MUST be stored
* No duplicates MUST exist
* System MUST remain consistent

---

### 7.2 Out-of-Order Events

**Given**

* Events received in non-sequential order

**When**

* State is computed

**Then**

* Correct completion MUST be derived
* Ordering MUST NOT affect correctness

---

## 8. Time Consistency

### 8.1 UTC Enforcement

**Given**

* Events are stored

**When**

* Timestamps are recorded

**Then**

* All timestamps MUST be UTC
* No timezone ambiguity allowed

---

## 9. Rate Limiting

### 9.1 Excess Requests

**Given**

* More than 10 requests/sec from same IP

**When**

* Requests exceed threshold

**Then**

* System MUST reject requests (HTTP 429)

---

## 10. Failure Handling

### 10.1 API Failure Response

**Given**

* Internal error occurs

**When**

* API is called

**Then**

* System MUST return explicit failure response
* Error MUST be logged

---

### 10.2 Event Durability

**Given**

* API returns `{ "status": "recorded" }`

**When**

* Request completes

**Then**

* Event MUST exist in database
* No data loss allowed

---

## 11. Logging

### 11.1 Progress Logging

**Given**

* A valid progress event is recorded

**When**

* Event is processed

**Then**

* System MUST log:

  * lead_id
  * section

---

### 11.2 Error Logging

**Given**

* An error occurs

**When**

* System handles failure

**Then**

* Error MUST be logged with context

---

## 12. Determinism Guarantee

### 12.1 Same Input → Same Output

**Given**

* Same set of progress events

**When**

* State is computed multiple times

**Then**

* Output MUST be identical every time

---

## 13. Definition of Done (Acceptance)

* [ ] All scenarios above pass
* [ ] No duplicate events observed
* [ ] Lead classification always correct
* [ ] API latency within defined thresholds
* [ ] GHL triggered exactly once per HOT lead
* [ ] All timestamps are UTC
* [ ] Rate limiting enforced
* [ ] Logs generated for all critical operations
