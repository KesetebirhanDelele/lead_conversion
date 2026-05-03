# spec/06_architecture.md

## 1. Objective

Define the system architecture, components, data flow, and boundaries for the deterministic lead conversion system.

---

## 2. Architecture Overview

The system follows a **layered, event-driven architecture**:

```
GPT Interface
    ↓
FastAPI Backend (Async, Rate-Limited)
    ↓
Application Layer (Deterministic Logic)
    ↓
PostgreSQL (Event Store)
    ↓
Async Processing Layer (Future: Redis Queue)
    ↓
External Systems (GHL)
```

---

## 3. Core Components

### 3.1 GPT Interface

**Role**

* User interaction layer
* Collects inputs (email, responses)
* Calls backend APIs

**Constraints**

* Stateless
* No business logic
* No persistence

---

### 3.2 FastAPI Backend

**Role**

* Entry point for all requests
* Input validation
* Routing
* Response formatting

**Requirements**

* Async execution
* Rate-limited (10 req/sec/IP)
* Response time < 500ms (p95)

---

### 3.3 Application Layer

**Role**

* Core deterministic engine

**Modules**

1. **Progress Service**

   * Handles event ingestion
   * Enforces idempotency

2. **State Engine**

   * Computes:

     * completion %
     * current section
     * last activity
     * lead classification

3. **Lead Service**

   * Manages lead records
   * Updates `lead_signal`
   * Handles GHL trigger logic

---

### 3.4 Database (PostgreSQL)

**Role**

* Persistent storage

**Tables**

* `leads`
* `progress_events`

**Characteristics**

* Append-only event store
* Indexed for performance
* Connection pooled

---

### 3.5 Async Processing Layer (Future)

**Role**

* Offload non-blocking work

**Use Cases**

* GHL API calls
* Retry failed operations

**Implementation (Future)**

* Redis + Celery or RQ

---

### 3.6 External System (GHL)

**Role**

* Receives HOT leads

**Constraints**

* Must be called asynchronously
* Must receive each lead exactly once

---

## 4. Data Flow

### 4.1 Progress Update Flow

```
Client (GPT)
   ↓
POST /api/progress/update
   ↓
Validate Input
   ↓
Generate event_id
   ↓
Insert into progress_events (idempotent)
   ↓
Fetch events for lead
   ↓
Compute state
   ↓
Update lead_signal
   ↓
Trigger async GHL (if HOT)
   ↓
Return response
```

---

### 4.2 Status Retrieval Flow

```
Client (GPT)
   ↓
POST /api/lead/status
   ↓
Validate Input
   ↓
Fetch events
   ↓
Compute state
   ↓
Return response
```

---

## 5. Data Boundaries

### 5.1 Source of Truth

* **ONLY source of truth:** `progress_events`

---

### 5.2 Derived Data

Computed on demand:

* completion_pct
* current_section
* last_activity_at
* lead_signal (authoritative = derived, stored = cache)

---

### 5.3 Restricted Data

* No direct DB access from client
* No client-provided timestamps

---

## 6. Component Interactions

| Component         | Interacts With    | Purpose           |
| ----------------- | ----------------- | ----------------- |
| GPT               | FastAPI           | Send/receive data |
| FastAPI           | Application Layer | Execute logic     |
| Application Layer | DB                | Read/write events |
| Application Layer | GHL               | Send HOT leads    |
| Async Layer       | GHL               | Offload calls     |

---

## 7. Key Architectural Decisions

### 7.1 Event-Driven Design

**Decision**

* Use append-only event store

**Reason**

* Ensures determinism
* Enables replayability

---

### 7.2 Derived State Model

**Decision**

* Do not store computed state as truth

**Reason**

* Prevents drift
* Guarantees consistency

---

### 7.3 Async External Calls

**Decision**

* Offload GHL calls

**Reason**

* Maintain API latency requirements

---

### 7.4 Explicit Section Registry

**Decision**

* Define sections in single module

**Reason**

* Prevent ordering bugs
* Avoid duplication

---

## 8. Performance Design

### 8.1 Query Strategy

* Indexed lookups by `lead_id`
* Avoid joins
* Use aggregation queries only

---

### 8.2 API Design

* Stateless endpoints
* Minimal computation
* Async execution

---

### 8.3 Scaling Strategy

ASSUMPTION: Initial scale ≤ 10k leads

Future scaling:

* Read replicas
* Caching layer (optional)
* Queue-based processing

---

## 9. Failure Handling

### 9.1 DB Failure

* API returns error
* No partial writes allowed

---

### 9.2 External Failure (GHL)

* Log failure
* Do not block request
* Retry (future via queue)

---

### 9.3 Duplicate Requests

* Safely ignored via idempotency

---

## 10. Security Boundaries

* API is only entry point
* DB not publicly accessible
* Input validation enforced
* HTTPS required in production

---

## 11. Risks & Mitigations

### Risk: Latency degradation

Mitigation:

* indexing
* async processing

---

### Risk: Event duplication

Mitigation:

* PRIMARY KEY constraint

---

### Risk: State inconsistency

Mitigation:

* derive state always

---

### Risk: External API delays

Mitigation:

* async execution

---

## 12. Trade-offs

| Decision          | Trade-off           |
| ----------------- | ------------------- |
| No ML             | No predictive power |
| Derived state     | Compute overhead    |
| Async integration | Added complexity    |
| Append-only       | Storage growth      |

---

## 13. Observability Hooks

System MUST expose:

* API latency metrics
* Event ingestion logs
* Error logs
* GHL trigger logs

---

## 14. Definition of Done

* [ ] All components implemented
* [ ] Data flow verified end-to-end
* [ ] Deterministic behavior confirmed
* [ ] API latency within limits
* [ ] No blocking operations
* [ ] Async processing implemented
* [ ] External integration isolated

---

## 15. Summary

This architecture ensures:

* Determinism
* Performance
* Reliability
* Simplicity

It is intentionally minimal and rule-based, avoiding unnecessary complexity while maintaining production readiness.
