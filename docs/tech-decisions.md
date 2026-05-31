# Technical Decisions, ADRs, & Database Schema Design

This document details the key architectural design decisions (ADRs) and the formal relational database schema design for the AI Incident Commander platform.

---

## Part 1: Architecture Decision Records (ADRs)

### ADR 01: Core Programming Language
* **Context:** We need a language with robust asynchronous library support, speed for API and event consumption, and a mature ecosystem for AI (LLMs, embeddings, RAG).
* **Decision:** Python (FastAPI). FastAPI provides excellent performance, automatic OpenAPI documentation, and asynchronous I/O loops that integrate cleanly with Python-native AI SDKs.
* **Status:** Approved.

### ADR 02: LLM reasoning Engine
* **Context:** We require high reasoning capacity, a large context window for log dumps, fast JSON-mode formatting, and affordable inference.
* **Decision:** Google Gemini 2.5 Flash / Pro.
* **Status:** Approved.

### ADR 03: Primary Database Engine
* **Context:** We need structured relational consistency for incidents, timelines, and audit logs, combined with vector search features for historical runbook mapping.
* **Decision:** PostgreSQL for transactional relational storage + Qdrant for dedicated semantic vector storage.
* **Status:** Approved.

---

## Part 2: PostgreSQL Database Schema Design

### 2.1 Entity Relationship (ER) Diagram

```mermaid
erDiagram
    SERVICES ||--o{ INCIDENTS : "monitors"
    SERVICES ||--o{ ALERTS : "triggers"
    SERVICES ||--o{ LOGS : "generates"
    
    USERS ||--o{ INCIDENTS : "commands"
    USERS ||--o{ POSTMORTEMS : "authors"
    
    INCIDENTS ||--o{ ALERTS : "groups"
    INCIDENTS ||--o{ LOGS : "snapshots"
    INCIDENTS ||--|| POSTMORTEMS : "documents"

    SERVICES {
        uuid id PK
        varchar name UK
        varchar repo_url
        varchar owner_team
        varchar status
        timestamp created_at
        timestamp updated_at
    }

    USERS {
        uuid id PK
        varchar email UK
        varchar name
        varchar role
        varchar slack_user_id UK
        timestamp created_at
    }

    INCIDENTS {
        uuid id PK
        uuid service_id FK
        uuid commander_id FK
        varchar title
        varchar status
        varchar severity
        text summary
        varchar slack_channel_id
        timestamp created_at
        timestamp acknowledged_at
        timestamp resolved_at
    }

    ALERTS {
        uuid id PK
        uuid incident_id FK
        uuid service_id FK
        varchar source
        varchar external_alert_id UK
        varchar status
        jsonb raw_payload
        timestamp created_at
    }

    LOGS {
        uuid id PK
        uuid incident_id FK
        uuid service_id FK
        timestamp timestamp
        varchar log_level
        text message
        jsonb masked_payload
        timestamp created_at
    }

    POSTMORTEMS {
        uuid id PK
        uuid incident_id FK UK
        uuid author_id FK
        varchar title
        text summary
        text root_cause
        jsonb timeline_json
        jsonb remediation_items
        timestamp created_at
        timestamp updated_at
    }
```

---

### 2.2 Table Definitions (DDL)

```sql
-- 1. Services Table
CREATE TABLE services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) UNIQUE NOT NULL,
    repo_url VARCHAR(256),
    owner_team VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, INACTIVE, DECOMMISSIONED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Users Table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'DEVELOPER', -- ADMIN, SRE, DEVELOPER
    slack_user_id VARCHAR(64) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Incidents Table
CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id UUID NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    commander_id UUID REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(256) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'TRIGGERED', -- TRIGGERED, ACKNOWLEDGED, TRIAGING, MITIGATED, RESOLVED
    severity VARCHAR(16) NOT NULL DEFAULT 'SEV-3',   -- SEV-1, SEV-2, SEV-3
    summary TEXT,
    slack_channel_id VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- 4. Alerts Table
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL, -- Nullable to allow alert correlation post-trigger
    service_id UUID NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    source VARCHAR(64) NOT NULL,                    -- prometheus, datadog, pagerduty
    external_alert_id VARCHAR(256) UNIQUE NOT NULL, -- ID generated by the alerting source
    status VARCHAR(32) NOT NULL DEFAULT 'FIRING',   -- FIRING, RESOLVED
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Logs Snapshot Table (Captured troubleshooting log streams)
CREATE TABLE logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    service_id UUID NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    log_level VARCHAR(16) NOT NULL,
    message TEXT NOT NULL,
    masked_payload JSONB,                           -- Metadata payload with stripped PII
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Post-Mortems Table
CREATE TABLE post_mortems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID UNIQUE NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    author_id UUID REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(256) NOT NULL,
    summary TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    timeline_json JSONB NOT NULL,                   -- List of chronological incident events
    remediation_items JSONB NOT NULL,               -- List of action-item objects
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

### 2.3 Key Relationships

1. **Service to Incidents/Alerts/Logs (1:N):** A service defines the telemetry boundary. Changes or failures in a service can trigger multiple alerts, result in multiple incidents over time, and yield system log streams.
2. **User to Incident (1:N):** An active incident has one Incident Commander (a `User` representing an SRE on-call). A user can command multiple incidents over time.
3. **Incident to Alerts (1:N):** A single incident is often triggered by a primary alert and grouped with subsequent alert events. The `incident_id` in the `alerts` table is nullable initially to let the ingestion engine store firing alarms before the deduplication engine correlates them to an incident session.
4. **Incident to Logs (1:N):** The system takes a context snapshot of relevant log outputs for analysis. These records cascade-delete if the incident is removed.
5. **Incident to Post-Mortem (1:1):** Every incident has at most one detailed post-mortem. This relationship is enforced via a `UNIQUE` constraint on the `post_mortems.incident_id` column.

---

### 2.4 Indexing Strategy

To maintain sub-second query performance as incident histories and logs snapshots scale, the following indexing strategy is implemented:

```sql
-- A. Foreign Key Indexes (Optimize Joins & Cascade Deletions)
CREATE INDEX idx_incidents_service_id ON incidents(service_id);
CREATE INDEX idx_incidents_commander_id ON incidents(commander_id);
CREATE INDEX idx_alerts_incident_id ON alerts(incident_id);
CREATE INDEX idx_alerts_service_id ON alerts(service_id);
CREATE INDEX idx_logs_incident_id ON logs(incident_id);
CREATE INDEX idx_logs_service_id ON logs(service_id);
CREATE INDEX idx_post_mortems_author_id ON post_mortems(author_id);

-- B. Composite Indexes for Active Triage & State Machine Queries
-- Optimizes Dashboard rendering of active incidents by state and age
CREATE INDEX idx_incidents_status_created ON incidents(status, created_at DESC);
-- Optimizes severity filters for critical alert listings
CREATE INDEX idx_incidents_severity_created ON incidents(severity, created_at DESC);

-- C. Search & Correlation Optimization
-- Speeds up deduplication checks against existing firing webhooks
CREATE INDEX idx_alerts_external_id ON alerts(external_alert_id);
-- Speeds up log timeline queries inside the AI Context retrieval loop
CREATE INDEX idx_logs_incident_time ON logs(incident_id, timestamp DESC);

-- D. JSONB GIN Indexes (Indexing Unstructured Telemetry Fields)
-- Speeds up search queries inside raw alerts JSON configurations
CREATE INDEX idx_alerts_payload_gin ON alerts USING GIN (raw_payload);
-- Enables querying log properties (e.g., matching K8s container labels or exception classes)
CREATE INDEX idx_logs_payload_gin ON logs USING GIN (masked_payload);
```
