# Technical Decisions, ADRs, & Database Schema Design (Redesigned)

This document details the updated key architectural design decisions (ADRs) and the formal relational database schema design for the AI Incident Commander platform.

---

## Part 1: Architecture Decision Records (ADRs)

### ADR 01: Core Programming Language & Service Boundary Style
* **Context:** We need a programming language and framework style that minimizes operational overhead, is easy to test locally, and simplifies inter-service communication under the target scale of 1M events/day.
* **Decision:** **Modular Monolith** using **Python (FastAPI)** for core processing, plus **one** isolated microservice for the high-security **Action Runner Service**. FastAPI runs internal Celery/Async task loops for ingestion, incident mapping, telemetry gathering, and AI RCA processing.
* **Status:** Approved (Replaces multiple backend microservices).

### ADR 02: LLM Reasoning Engine & Semantic Cache
* **Context:** We require high reasoning capacity, structured JSON responses, and protection against API rate limits and high token costs during alert storms.
* **Decision:** Google Gemini 2.5 Flash / Pro, fronted by a **Redis Semantic Cache** mapping alert embeddings (using cosine similarity threshold > 0.98) to skip redundant LLM invocations.
* **Status:** Approved.

### ADR 03: Storage Strategy for Telemetry snapshots
* **Context:** Storing raw log snapshots in PostgreSQL causes database bloat, indexing lag, and high write amplification.
* **Decision:** Store unstructured raw log block files and Prometheus metrics JSON collections in an **S3-Compatible Object Store (MinIO)**, saving only the S3 pre-signed keys/URLs inside the PostgreSQL `incidents` table.
* **Status:** Approved (Replaces PostgreSQL `logs` table storage).

### ADR 04: Command Execution Interface
* **Context:** Executing arbitrary shell script commands recommended by LLMs opens critical security vulnerabilities.
* **Decision:** The `action-runner-service` executes only strictly typed, parameterized API calls using the official Kubernetes Python Client SDK. No raw shell subprocess executions (`shell=True`) are permitted.
* **Status:** Approved.

---

## Part 2: PostgreSQL Database Schema Design

### 2.1 Entity Relationship (ER) Diagram

```mermaid
erDiagram
    SERVICES ||--o{ INCIDENTS : "monitors"
    SERVICES ||--o{ ALERTS : "triggers"
    
    USERS ||--o{ INCIDENTS : "commands"
    USERS ||--o{ POSTMORTEMS : "authors"
    
    INCIDENTS ||--o{ ALERTS : "groups"
    INCIDENTS ||--|| POSTMORTEMS : "documents"
    INCIDENTS ||--o{ AUDIT_LOGS : "records"

    SERVICES {
        uuid id PK
        varchar name UK
        varchar repo_url
        varchar owner_team
        varchar status
        timestamp under_remediation_until
        boolean remediation_lock
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
        varchar telemetry_s3_key
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

    AUDIT_LOGS {
        uuid id PK
        uuid incident_id FK
        varchar operator_user
        varchar action_type
        jsonb parameters
        varchar status
        text backup_state_yaml
        timestamp executed_at
        varchar output_hash
        text output_preview
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
    under_remediation_until TIMESTAMP WITH TIME ZONE, -- Anti-loop cool-down timestamp
    remediation_lock BOOLEAN NOT NULL DEFAULT FALSE,   -- Flag to manually pause auto-remediations
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
    telemetry_s3_key VARCHAR(256),                   -- Pointer to MinIO/S3 logs/metrics JSON snapshot object
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- 4. Alerts Table
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    service_id UUID NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    source VARCHAR(64) NOT NULL,
    external_alert_id VARCHAR(256) UNIQUE NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'FIRING',   -- FIRING, RESOLVED
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Command Execution Audit Trail (Redesigned for Parameterized Actions + Rollbacks)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    operator_user VARCHAR(128) NOT NULL,            -- Slack / Auth User
    action_type VARCHAR(64) NOT NULL,               -- e.g., RESTART_POD, SCALE_DEPLOYMENT, ROLLBACK
    parameters JSONB NOT NULL,                      -- Parameter arguments for SDK (e.g., {"pod_name": "x"})
    status VARCHAR(32) NOT NULL,                    -- PENDING, APPROVED, EXECUTED, FAILED, BLOCKED
    backup_state_yaml TEXT,                         -- Snapshot of Kubernetes resource manifest before modification
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    output_hash VARCHAR(64) NOT NULL,
    output_preview TEXT
);

-- 6. Post-Mortems Table
CREATE TABLE post_mortems (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID UNIQUE NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    author_id UUID REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(256) NOT NULL,
    summary TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    timeline_json JSONB NOT NULL,
    remediation_items JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

### 2.3 Indexing Strategy

```sql
-- A. Foreign Key Indexes (Optimize Joins & Cascade Deletions)
CREATE INDEX idx_incidents_service_id ON incidents(service_id);
CREATE INDEX idx_incidents_commander_id ON incidents(commander_id);
CREATE INDEX idx_alerts_incident_id ON alerts(incident_id);
CREATE INDEX idx_alerts_service_id ON alerts(service_id);
CREATE INDEX idx_audit_logs_incident_id ON audit_logs(incident_id);
CREATE INDEX idx_post_mortems_author_id ON post_mortems(author_id);

-- B. Composite Indexes for Dashboard and Lifecycle Management
CREATE INDEX idx_incidents_status_created ON incidents(status, created_at DESC);
CREATE INDEX idx_incidents_severity_created ON incidents(severity, created_at DESC);

-- C. Search & Correlation Optimization
CREATE INDEX idx_alerts_external_id ON alerts(external_alert_id);

-- D. JSONB GIN Indexes (Indexing Unstructured Telemetry Fields)
CREATE INDEX idx_alerts_payload_gin ON alerts USING GIN (raw_payload);
CREATE INDEX idx_audit_logs_params_gin ON audit_logs USING GIN (parameters);
```

---

## Part 3: Deprecated Schema Designs
1.  **Deprecated Table: `logs`:** Completely removed. Raw text lines and log streams from Loki/Jaeger are no longer stored in PostgreSQL. They are bundled and written to the MinIO object store.
2.  **Deprecated Column: `audit_logs.command`:** Removed in favor of `audit_logs.action_type` and `audit_logs.parameters` (JSONB) to enforce parameterized API invocations and block shell injections.
