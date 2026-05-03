# spec/10_observability_ops.md

## 1. Objective

Define observability, logging, monitoring, and operational requirements to ensure:

* System reliability
* Fast debugging
* Performance visibility
* Failure detection

---

## 2. Observability Principles

1. **Everything critical is logged including Authentication failures MUST be logged**
2. **Metrics are measurable and actionable**
3. **Failures are visible immediately**
4. **No silent errors allowed**

---

## 3. Logging Requirements

### 3.1 Logging Scope

System MUST log:

* API requests
* Progress events
* Errors
* External API calls (GHL)

---

### 3.2 Log Format

Logs MUST be structured:

```json id="log_format"
{
  "timestamp": "UTC ISO-8601",
  "level": "INFO | ERROR",
  "event": "event_type",
  "lead_id": "email@example.com",
  "details": {}
}
```

---

### 3.3 Required Log Events

#### API Request

```json id="log_api"
{
  "event": "api_request",
  "endpoint": "/api/progress/update",
  "status": "success"
}
```

---

#### Progress Event

```json id="log_progress"
{
  "event": "progress_recorded",
  "lead_id": "user@example.com",
  "section": "P1_S1"
}
```

---

#### Error

```json id="log_error"
{
  "event": "error",
  "error_code": "INTERNAL_ERROR",
  "message": "DB connection failed"
}
```

---

#### GHL Trigger

```json id="log_ghl"
{
  "event": "ghl_triggered",
  "lead_id": "user@example.com"
}
```

---

### 3.4 Logging Constraints

#### Must

* All logs MUST include UTC timestamp
* Errors MUST include context
* Logs MUST be written synchronously (non-blocking)

#### Must Not

* Log secrets (API keys, DB credentials)
* Log full payloads blindly

---

## 4. Metrics

### 4.1 Core Metrics

| Metric               | Description          | Target  |
| -------------------- | -------------------- | ------- |
| API latency (p95)    | Response time        | < 500ms |
| API latency (max)    | Worst-case           | < 800ms |
| Error rate           | % failed requests    | < 1%    |
| Duplicate event rate | Idempotency failures | 0%      |

---

### 4.2 Business Metrics

| Metric          | Description                 |
| --------------- | --------------------------- |
| Completion rate | % users completing sections |
| HOT lead rate   | % leads classified HOT      |
| Drop-off rate   | Per section                 |

---

### 4.3 Reliability Metrics

| Metric                  | Description                 |
| ----------------------- | --------------------------- |
| GHL success rate        | % successful external calls |
| Failed API calls        | Count per interval          |
| Event ingestion success | % events stored             |

---

## 5. Monitoring

### 5.1 What to Monitor

* API latency
* Error rate
* DB performance
* GHL integration status

---

### 5.2 Alerts (Required)

Trigger alerts when:

* API latency > 800ms p95
* Error rate > 2%
* GHL failures > 5%
* DB connection errors detected

---

### 5.3 Alert Channels

ASSUMPTION: Basic logging only in MVP
Alternative:

* Email alerts
* Slack notifications
* Monitoring tools (Prometheus, Grafana)

---

## 6. Health Checks

### 6.1 Endpoint

**GET /health**

---

### 6.2 Response

```json id="health_resp"
{
  "status": "ok"
}
```

---

### 6.3 Checks

* API is running
* DB connection is alive

---

## 7. Error Handling

### 7.1 Requirements

* All errors MUST be:

  * logged
  * returned with proper status code

---

### 7.2 Categories

| Type       | Example         |
| ---------- | --------------- |
| Validation | invalid section |
| System     | DB failure      |
| External   | GHL failure     |

---

### 7.3 Behavior

* No silent failures
* No partial writes
* External failures MUST NOT crash API

---

## 8. Operational Requirements

### 8.1 Deployment

* System MUST run on:

  * FastAPI (Uvicorn)
  * Nginx (reverse proxy)
  * PostgreSQL

---

### 8.2 Process Management

ASSUMPTION: Single instance for MVP
Alternative:

* Use systemd or Docker for process control

---

### 8.3 Restart Behavior

* System restart MUST NOT affect correctness
* State MUST be recoverable from DB

---

## 9. Log Storage

### 9.1 MVP

* Logs stored locally (file or stdout)

---

### 9.2 Future

* Centralized logging system:

  * ELK stack
  * Cloud logging

---

## 10. Debugging Support

System MUST enable:

* Trace API calls by lead_id
* Reconstruct state from events
* Identify failure points via logs

---

## 11. Performance Monitoring

### 11.1 DB Monitoring

* Query latency
* Index usage (via EXPLAIN)

---

### 11.2 API Monitoring

* Endpoint-level latency
* Throughput

---

## 12. Async Processing Monitoring

### Future (Redis Queue)

Track:

* Queue size
* Job failures
* Retry counts

---

## 13. Constraints

### Must

* Log all critical actions
* Monitor latency and errors
* Provide health endpoint

---

### Must Not

* Allow silent failures
* Ignore error conditions
* Block API for logging

---

### Preferences

* Structured logging
* JSON logs
* Centralized monitoring (future)

---

### Trade-offs

| Decision                 | Trade-off                   |
| ------------------------ | --------------------------- |
| Minimal monitoring (MVP) | Less visibility             |
| Local logs               | Simpler but harder to scale |
| No alerting (initial)    | Risk of delayed detection   |

---

## 14. Escalation Triggers

Immediate escalation if:

* API latency > 800ms p95
* Error rate > 2%
* Duplicate events detected
* GHL failures spike
* DB connectivity issues

---

## 15. Definition of Done

* [ ] Logging implemented for all critical paths
* [ ] Metrics defined and trackable
* [ ] Health endpoint implemented
* [ ] Error handling complete
* [ ] No silent failures
* [ ] API latency measurable
* [ ] Logs structured and readable

---

## 16. Summary

Observability ensures:

* System transparency
* Fast debugging
* Performance control

Without observability, the system cannot be reliably operated or scaled.
