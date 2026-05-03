spec/08_data_model.md
1. Objective

Define the complete data model, schema, constraints, and data access patterns for the system.

The data model is optimized for:

Determinism
Idempotency
High read/write performance
Append-only event sourcing
Secure handling of PII (encrypted email)
2. Design Principles
Single Source of Truth
progress_events is the ONLY authoritative dataset
Append-Only
Events are immutable
Derived State
All computed values MUST be derived, not stored
Idempotency
Enforced via primary keys
Secure Identity Separation
System identity (lead_id) MUST be separate from PII (email)
3. Entities Overview
Entity	Type	Purpose
leads	Table	Lead metadata + encrypted identity
progress_events	Table	Immutable event store
4. Table: leads
4.1 Schema
CREATE TABLE leads (
    lead_id UUID PRIMARY KEY,
    email_encrypted TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    lead_signal TEXT NOT NULL DEFAULT 'NOT_HOT',
    ghl_synced BOOLEAN NOT NULL DEFAULT FALSE
);
4.2 Field Definitions
Field	Type	Description
lead_id	UUID	System-generated unique identifier
email_encrypted	TEXT	Fernet-encrypted email
created_at	TIMESTAMPTZ	UTC timestamp
lead_signal	TEXT	Cached classification
ghl_synced	BOOLEAN	External sync flag
4.3 Constraints
lead_id MUST be UUID (system-generated)
email_encrypted MUST NOT be null
lead_signal MUST be:
HOT
NOT_HOT
created_at MUST be UTC
4.4 Indexing
CREATE INDEX idx_leads_signal ON leads(lead_signal);
4.5 Critical Rules
Email MUST be encrypted before insert
Email MUST NEVER be used as primary key
Email MUST NEVER be used in joins or event IDs
5. Table: progress_events
5.1 Schema
CREATE TABLE progress_events (
    event_id TEXT PRIMARY KEY,
    lead_id UUID NOT NULL,
    section TEXT NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_lead
        FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
);
5.2 Field Definitions
Field	Type	Description
event_id	TEXT	Unique id: lead_id:section
lead_id	UUID	FK reference to leads
section	TEXT	Course section
occurred_at	TIMESTAMPTZ	UTC timestamp
5.3 Constraints
event_id MUST be unique
lead_id MUST exist in leads
section MUST be valid (app-level)
occurred_at MUST be UTC
5.4 Indexes (REQUIRED)
CREATE INDEX idx_events_lead_id ON progress_events(lead_id);
CREATE INDEX idx_events_section ON progress_events(section);
CREATE INDEX idx_events_occurred_at ON progress_events(occurred_at);
5.5 Data Rules
INSERT ONLY
NO UPDATE
NO DELETE
6. Relationships
leads (1) ──── (N) progress_events
FK constraint is REQUIRED
Referential integrity MUST be enforced
7. Derived State Model
7.1 Computed Fields
completed_sections
completion_pct
last_activity_at
current_section
lead_signal
7.2 Core Query
SELECT 
    COUNT(DISTINCT section) AS completed_sections,
    MAX(occurred_at) AS last_activity_at
FROM progress_events
WHERE lead_id = $1;
7.3 Completion Formula
completion_pct = completed_sections / TOTAL_SECTIONS * 100
7.4 Classification Logic
is_recent = (now - last_activity_at) <= 48 hours

IF completion_pct >= 25 AND is_recent:
    lead_signal = HOT
ELSE:
    lead_signal = NOT_HOT
8. Idempotency Model
Event ID
event_id = lead_id + ":" + section
Guarantees
Same event cannot be inserted twice
Duplicate requests are safe
No race condition creates duplicates
Future-Safe Alternative

ASSUMPTION: Single course system
Alternative:

event_id = lead_id + ":" + course_id + ":" + section
9. Data Access Patterns
9.1 Write Pattern
Insert event
Create lead (if first interaction)
9.2 Read Pattern
Query events by lead_id
Compute state in application
9.3 Admin Query
SELECT lead_id, lead_signal
FROM leads
WHERE lead_signal = 'HOT';
10. Encryption Specification
Algorithm
Fernet (symmetric encryption)
Rules
Email MUST be encrypted before DB insert
Email MUST be decrypted only in backend when needed
Encryption key MUST be stored in environment variable
Plaintext email MUST NOT be persisted
Constraint
Encryption MUST be reversible
Encryption MUST NOT affect system identity
11. Connection Management
MUST use connection pooling
pool_size = 10
max_overflow = 5
12. Performance Considerations
MUST
Use indexes for all queries
Query by lead_id only
Keep queries O(n per lead), not global
MUST NOT
Scan entire table
Join large datasets unnecessarily
13. Data Integrity Guarantees
Idempotency
Enforced via event_id PK
Consistency
Derived state MUST match events
Referential Integrity
FK MUST always hold
Durability
Event MUST exist if API returns success
14. Migration Strategy
MVP → Production
SQLite → PostgreSQL
Required Adjustments
Ensure UUID support
Add FK constraints
Validate encrypted data integrity
15. Risks & Mitigations
Risk: Broken identity due to encryption

Mitigation: Separate UUID from email

Risk: Duplicate events

Mitigation: PRIMARY KEY

Risk: FK violations

Mitigation: enforce insert order (lead first)

16. Definition of Done
 UUID-based identity implemented
 Email encrypted before storage
 FK constraint enforced
 Idempotency verified
 Insert-only model validated
 Queries optimized
 UTC timestamps enforced
17. Summary

This data model ensures:

Deterministic computation
Secure PII handling
Strong referential integrity
Idempotent event processing

This is now production-safe at the data layer, while remaining aligned with MVP-first discipline.