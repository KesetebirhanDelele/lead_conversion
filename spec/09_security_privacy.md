# spec/09_security_privacy.md

## 1. Objective

Define security and privacy requirements to protect:

* Lead data (PII: email)
* System integrity
* External integrations

The system MUST enforce **strict input validation, controlled access, and safe data handling**.

---

## 2. Data Classification

### 2.1 Sensitive Data (PII)

| Data            | Type | Sensitivity |
| --------------- | ---- | ----------- |
| lead_id (email) | PII  | High        |

---

### 2.2 Non-Sensitive Data

* section identifiers (e.g., P1_S1)
* derived metrics (completion_pct)
* system logs (excluding PII leakage)

---

## 3. Security Principles

1. **Minimal Data Collection**

   * Only collect email (MVP)

2. **Zero Trust Input**

   * All client inputs MUST be validated

3. **Backend Authority**

   * All logic and state computed server-side

4. **No Direct Data Exposure**

   * DB MUST never be exposed externally

---

## 4. Input Validation

### 4.1 Lead ID

* MUST be valid email format
* MUST NOT exceed 255 characters
* MUST be sanitized

---

### 4.2 Section

* MUST exist in `COURSE_SECTIONS`
* MUST NOT accept arbitrary values

---

### 4.3 Request Body

* MUST be JSON
* MUST reject unknown fields (strict schema validation)

---

## 5. API Security

### 5.1 Transport Security

* HTTPS REQUIRED in production
* TLS MUST be enforced via Nginx

---

### 5.2 Rate Limiting

* Max 10 requests/sec per IP
* Prevent abuse and brute-force attacks

---

### 5.3 Authentication (Future)

ASSUMPTION: No authentication in MVP
Alternative: Add token-based authentication

Future requirements:

* Bearer token auth
* API key per client
* Role-based access (admin vs user)

---

## 6. Data Protection

### 6.1 Storage

* Emails MUST be encrypted at rest using Fernet (symmetric encryption)
Decryption ONLY allowed in backend layer

ASSUMPTION: Plain storage acceptable for MVP
Alternative: Hash or encrypt emails

---

### 6.2 Encryption (Future)

* Encrypt sensitive fields at rest
* Use managed DB encryption (Postgres-level)

---

### 6.3 Data Exposure

* API MUST only return necessary fields
* MUST NOT expose internal DB structure

### 6.4 Encryption Spec
Algorithm: Fernet (AES-based)
Key source: environment variable
Encryption occurs before DB write
Decryption occurs only when needed

---

## 7. Logging Security

### 7.1 Allowed Logging

* lead_id (email)
* section
* timestamps

---

### 7.2 Restricted Logging

* MUST NOT log:

  * full request payloads blindly
  * sensitive headers
  * internal credentials

---

### 7.3 Log Format

* Structured (JSON preferred)
* Include:

  * timestamp (UTC)
  * event type
  * status

---

## 8. External Integration Security (GHL)

### 8.1 API Key Handling

* MUST store API key securely (env variables)
* MUST NOT hardcode keys

---

### 8.2 Transmission

* HTTPS only
* Validate responses

---

### 8.3 Failure Handling

* Log failures
* Do not expose errors to client

---

## 9. Database Security

### 9.1 Access Control

* DB MUST NOT be publicly accessible
* Access restricted to backend service

---

### 9.2 Credentials

* Stored in environment variables
* Rotated periodically (future)

---

### 9.3 Query Safety

* Use parameterized queries ONLY
* Prevent SQL injection

---

## 10. Infrastructure Security

### 10.1 Server (Hetzner)

* Disable root login (recommended)
* Use SSH keys only
* Keep system updated

---

### 10.2 Nginx

* Enforce HTTPS
* Redirect HTTP → HTTPS

---

### 10.3 Firewall (Recommended)

* Allow:

  * 80 (HTTP)
  * 443 (HTTPS)
  * 22 (SSH, restricted)
* Block all others

---

## 11. Privacy Considerations

### 11.1 Data Minimization

* Only collect required data (email)

---

### 11.2 Retention (Future)

ASSUMPTION: No retention policy in MVP
Alternative:

* Delete inactive leads after X days
* Anonymize old data

---

### 11.3 Compliance (Future)

* GDPR readiness:

  * Right to delete
  * Data export
* CCPA considerations

---

## 12. Threat Model

### 12.1 Threats

| Threat               | Risk   |
| -------------------- | ------ |
| API abuse            | High   |
| Data leakage         | High   |
| Duplicate event spam | Medium |
| External API failure | Medium |
| SQL injection        | High   |

---

### 12.2 Mitigations

| Threat           | Mitigation            |
| ---------------- | --------------------- |
| API abuse        | Rate limiting         |
| Data leakage     | Minimal exposure      |
| Event spam       | Idempotency           |
| SQL injection    | Parameterized queries |
| External failure | Async + logging       |

---

## 13. Security Constraints

### Must

* Validate all inputs
* Enforce HTTPS
* Use parameterized queries
* Store secrets securely

---

### Must Not

* Expose database
* Trust client data
* Log sensitive secrets
* Hardcode credentials

---

### Preferences

* Use environment variables
* Use secure defaults
* Minimize attack surface

---

### Trade-offs

| Decision            | Trade-off                   |
| ------------------- | --------------------------- |
| No auth (MVP)       | Simplicity vs exposure risk |
| Plain email storage | Simplicity vs privacy       |
| Minimal security    | Faster build vs future debt |

---

## 14. Escalation Triggers

Immediate escalation if:

* Unauthorized access detected
* Data leakage occurs
* API abuse exceeds limits
* Secrets exposed in logs/code

---

## 15. Definition of Done

* [ ] Input validation enforced
* [ ] HTTPS enabled
* [ ] Rate limiting active
* [ ] Secrets stored securely
* [ ] No sensitive data leaked in logs
* [ ] DB not publicly accessible
* [ ] Parameterized queries used
* [ ] External API keys secured

---

## 16. Summary

Security is enforced through:

* Strict validation
* Minimal data exposure
* Controlled access
* Safe integration practices

This system prioritizes **simplicity in MVP**, while defining clear paths for **production-grade security upgrades**.
