# spec/07_api_contracts.md

## 1. Objective

Define strict, implementation-ready API contracts for all exposed endpoints.

All APIs MUST be:

* Deterministic
* Stateless
* Idempotent (where applicable)
* Authenticated
* Validated
* Performance-bound (<500ms p95)

---

## 2. Global API Rules

### 2.1 Protocol

* HTTPS ONLY (production)
* JSON request/response format

---

### 2.2 Headers

#### REQUIRED

```id="hdr_req"
Content-Type: application/json
Authorization: Bearer <API_KEY>
```

---

### 2.3 Authentication (REQUIRED)

#### Rule

* ALL API requests MUST include:

  * `Authorization: Bearer <API_KEY>`

---

#### Validation

* API key MUST be validated on every request
* Validation MUST occur via middleware before request processing

---

#### Failure Behavior

If header is missing or invalid:

**Response (401)**

```json id="auth_err"
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing API key"
  }
}
```

---

#### Implementation Constraints

* API key MUST be stored in environment variable
* Comparison MUST be constant-time
* MUST NOT query database for API key validation (MVP)

ASSUMPTION: Single API key for MVP
Alternative: Per-client API keys stored in secure store

---

### 2.4 Time

* All timestamps MUST be ISO-8601 UTC
* Example: `2026-01-01T10:00:00Z`

---

### 2.5 Error Format

All errors MUST follow:

```json id="errfmt"
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message"
  }
}
```

---

### 2.6 Status Codes

| Code | Meaning          |
| ---- | ---------------- |
| 200  | Success          |
| 400  | Bad request      |
| 401  | Unauthorized     |
| 422  | Validation error |
| 429  | Rate limited     |
| 500  | Internal error   |

---

## 3. Endpoint: Progress Update

### 3.1 Definition

**POST** `/api/progress/update`

---

### 3.2 Request

```json id="req_progress"
{
  "lead_id": "user@example.com",
  "section": "P1_S1"
}
```

---

### 3.3 Validation Rules

* `lead_id`

  * REQUIRED
  * MUST be valid email

* `section`

  * REQUIRED
  * MUST exist in `COURSE_SECTIONS`

---

### 3.4 Processing Logic

1. Authenticate request
2. Validate request body
3. Generate:

   ```
   event_id = lead_id + ":" + section
   ```
4. Insert into `progress_events` (idempotent)
5. Create lead if not exists
6. Recompute state
7. Update `lead_signal`
8. Trigger async GHL (if applicable, future)
9. Return response

---

### 3.5 Response (Success)

```json id="res_progress"
{
  "status": "recorded"
}
```

---

### 3.6 Response Time

* p95 ≤ 500ms
* max ≤ 800ms

---

### 3.7 Error Cases

#### Missing Fields

**Response (400)**

```json id="err_missing"
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "lead_id and section are required"
  }
}
```

---

#### Invalid Section

**Response (422)**

```json id="err_section"
{
  "error": {
    "code": "INVALID_SECTION",
    "message": "Section not found in course registry"
  }
}
```

---

#### Unauthorized

**Response (401)**

```json id="err_unauth"
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing API key"
  }
}
```

---

#### Rate Limit Exceeded

**Response (429)**

```json id="err_rate"
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests"
  }
}
```

---

#### Internal Error

**Response (500)**

```json id="err_internal"
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "Unexpected server error"
  }
}
```

---

## 4. Endpoint: Lead Status

### 4.1 Definition

**POST** `/api/lead/status`

---

### 4.2 Request

```json id="req_status"
{
  "lead_id": "user@example.com"
}
```

---

### 4.3 Validation Rules

* `lead_id`

  * REQUIRED
  * MUST be valid email

---

### 4.4 Processing Logic

1. Authenticate request
2. Validate request
3. Query events by `lead_id`
4. If no events:

   * return `lead_exists = false`
5. Else:

   * compute state
   * return derived values

---

### 4.5 Response (Lead Exists)

```json id="res_status_exists"
{
  "lead_exists": true,
  "course_state": {
    "completion_pct": 33.33,
    "current_section": "P2_S1",
    "last_activity_at": "2026-01-01T10:00:00Z",
    "lead_signal": "HOT"
  }
}
```

---

### 4.6 Response (Lead Not Found)

```json id="res_status_not_found"
{
  "lead_exists": false
}
```

---

### 4.7 Response Time

* p95 ≤ 500ms
* max ≤ 800ms

---

### 4.8 Error Cases

#### Missing lead_id

**Response (400)**

```json id="err_missing_lead"
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "lead_id is required"
  }
}
```

---

#### Unauthorized

**Response (401)**

```json id="err_unauth2"
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing API key"
  }
}
```

---

## 5. Idempotency Contract

### Applicable Endpoint

* `/api/progress/update`

---

### Guarantee

* Multiple identical requests MUST produce:

  * Same system state
  * No duplicate DB records

---

### Enforcement

* `event_id` as PRIMARY KEY
* Duplicate inserts ignored or handled gracefully

---

## 6. Rate Limiting Contract

### Rule

* Max 10 requests/sec per IP

---

### Behavior

* Excess requests MUST return HTTP 429
* No partial processing allowed

---

## 7. Async Processing Contract

### Applicable Operations

* External integrations (GHL)

---

### MVP Behavior

* GHL NOT active
* No async queue required

---

### Future Behavior

* MUST NOT block API response
* MUST execute after event commit

---

## 8. Consistency Guarantees

### Read-After-Write

* After successful `/progress/update`:

  * `/lead/status` MUST reflect updated state immediately

---

### Determinism

* Same events → same API response

---

## 9. Logging Requirements

Each API call MUST log:

* timestamp (UTC)
* endpoint
* lead_id (if present)
* status (success/failure)
* authentication result

---

## 10. Versioning (Future)

ASSUMPTION: v1 only

Future:

* `/v1/api/...` prefix
* Backward compatibility maintained

---

## 11. Security Considerations

* Authentication REQUIRED for all endpoints
* Input validation REQUIRED
* No direct DB exposure
* HTTPS enforced in production
* API key stored securely (env variable)

---

## 12. Definition of Done

* [ ] Authentication enforced via middleware
* [ ] All endpoints validate API key
* [ ] Error responses consistent
* [ ] Idempotency guaranteed
* [ ] Rate limiting active
* [ ] No blocking operations
* [ ] Response times within limits
* [ ] Logging includes auth outcomes

---

## 13. Summary

These API contracts ensure:

* Secure access control
* Deterministic behavior
* High performance
* Safe concurrency

Authentication is now a **hard requirement**, not optional, and enforced at every request boundary.
