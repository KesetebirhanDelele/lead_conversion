# spec/05_eval_plan.md

## 1. Objective

Define a rigorous evaluation framework to verify that the system:

* Behaves deterministically
* Meets performance requirements
* Correctly classifies leads
* Maintains data integrity under load

---

## 2. Evaluation Principles

* Determinism over approximation
* Measurable metrics only
* Test against real scenarios and edge cases
* Continuous validation (not one-time testing)

---

## 3. Core Evaluation Areas

1. Functional correctness
2. Determinism
3. Performance
4. Data integrity
5. Concurrency safety
6. External integration reliability

---

## 4. Functional Evaluation

### 4.1 Progress Tracking Accuracy

**Test**

Given:

* Lead completes 3 out of 9 sections

Expect:

* `completion_pct = 33.33`

---

### 4.2 Section Progression

**Test**

Given:

* Completed: P1_S1, P1_S2

Expect:

* `current_section = P1_S3`

---

### 4.3 Lead Classification

**Test Matrix**

| completion_pct | last_activity | Expected |
| -------------- | ------------- | -------- |
| <25%           | recent        | NOT_HOT  |
| ≥25%           | stale         | NOT_HOT  |
| ≥25%           | recent        | HOT      |

---

### 4.4 Invalid Input Handling

* Missing lead_id → 400
* Invalid section → 422
* Duplicate event → accepted, no duplication

---

## 5. Determinism Evaluation

### 5.1 Repeatability Test

**Procedure**

* Run same event set 10 times

**Expectation**

* Output MUST be identical every time

---

### 5.2 Order Independence

**Test**

Given:

* Events inserted in random order

Expect:

* Same final state

---

### 5.3 No Hidden State

**Test**

* Restart system
* Recompute state

Expect:

* Same result from DB events only

---

## 6. Performance Evaluation

### 6.1 API Latency

**Target**

* p50 < 200ms
* p95 < 500ms
* max acceptable < 800ms

---

### 6.2 Load Test

**Scenario**

* 50 requests/sec sustained
* 5,000 concurrent users (simulated)

**Expectation**

* No failures
* Latency within thresholds

---

### 6.3 State Computation Time

* Must remain < 200ms per request

---

## 7. Data Integrity Evaluation

### 7.1 Idempotency

**Test**

* Send same request 10 times

Expect:

* Only 1 event stored

---

### 7.2 Append-Only Enforcement

**Test**

* Attempt update/delete

Expect:

* Operation rejected

---

### 7.3 Event Accuracy

* Stored event MUST match request data exactly

---

## 8. Concurrency Evaluation

### 8.1 Parallel Requests

**Test**

* Send 20 concurrent identical requests

Expect:

* 1 event stored
* No race conditions

---

### 8.2 Rapid Sequence Events

**Test**

Send:

* P1_S1
* P1_S2
* P1_S3

Within milliseconds

Expect:

* All events stored
* Correct final state

---

## 9. GHL Integration Evaluation

### 9.1 Single Trigger

**Test**

* Lead becomes HOT

Expect:

* Exactly 1 API call to GHL

---

### 9.2 Duplicate Prevention

**Test**

* Lead remains HOT

Expect:

* No additional calls

---

### 9.3 Failure Scenario

**Test**

* GHL API fails

Expect:

* Failure logged
* No system crash

---

## 10. Rate Limiting Evaluation

### 10.1 Excess Requests

**Test**

* Send >10 req/sec from same IP

Expect:

* HTTP 429 responses

---

## 11. Logging Evaluation

### 11.1 Coverage

Verify logs exist for:

* API calls
* Progress events
* Errors

---

### 11.2 Structure

Logs MUST include:

* timestamp (UTC)
* lead_id (if applicable)
* event context

---

## 12. Time Consistency Evaluation

### 12.1 UTC Enforcement

**Test**

* Inspect DB timestamps

Expect:

* All timestamps are UTC

---

### 12.2 Activity Window

**Test**

* last_activity_at exactly 48h boundary

Expect:

* Correct classification

---

## 13. Failure Handling Evaluation

### 13.1 API Failure

**Test**

* Simulate DB failure

Expect:

* Error returned
* Logged

---

### 13.2 Partial Failures

**Test**

* Event insert succeeds
* GHL fails

Expect:

* Event remains stored
* System continues

---

## 14. Metrics to Track

### Core Metrics

* % HOT leads
* Completion rate
* Drop-off per section

---

### System Metrics

* API latency (p50, p95)
* Error rate
* Duplicate event rate

---

### Reliability Metrics

* Failed requests
* GHL sync success rate

---

## 15. Tooling

### Load Testing

* k6 or Locust

### DB Analysis

* EXPLAIN ANALYZE

### Logging

* Structured logs (JSON preferred)

---

## 16. Pass/Fail Criteria

System passes evaluation if:

* All functional tests succeed
* Determinism confirmed (0 variance)
* API latency within thresholds
* No duplicate events
* GHL triggered exactly once per lead
* No data loss observed

---

## 17. Escalation Conditions

Immediate escalation if:

* Any nondeterministic behavior observed
* API latency > 800ms p95
* Duplicate events detected
* GHL duplicate calls occur
* Data inconsistency detected

---

## 18. Definition of Done

* [ ] All evaluation tests executed
* [ ] All metrics within thresholds
* [ ] Determinism validated
* [ ] Concurrency safety verified
* [ ] External integrations tested
* [ ] Logging verified
* [ ] No critical defects remain

---

## 19. Summary

This evaluation plan ensures the system is:

* Correct
* Deterministic
* Performant
* Reliable

No deployment to production is allowed unless all evaluation criteria pass.
