# Sprint 1 Backlog: Ingestion to Correlation Pipeline

**Sprint Goal:** Webhook → Ingestion Gateway → Kafka → Incident Engine → PostgreSQL  
**Target Duration:** 2 Weeks  
**Story Points Total:** 18 SP  

---

### Task 1: Setup Alembic Database Migrations & Relational Models
*   **Task Name:** `TASK-1.1: DB-Migrations-Setup`
*   **Purpose:** Establish the PostgreSQL relational tables and indexes to support service registry and incident state management.
*   **Files To Create:**
    *   `shared/python/common/domain/models.py` (SQLAlchemy model declarations)
    *   `shared/python/alembic.ini` (Alembic configuration)
    *   `shared/python/migrations/env.py` (Alembic environment script)
    *   `shared/python/migrations/versions/` (Directory for Alembic schema scripts)
*   **Dependencies:** Docker PostgreSQL container running locally (`infra/docker/compose`).
*   **Acceptance Criteria:**
    1.  Running `poetry run alembic revision --autogenerate -m "init"` creates migration files.
    2.  Running `poetry run alembic upgrade head` successfully creates tables `services`, `users`, `incidents`, `alerts`, and `audit_logs` in PostgreSQL.
    3.  Database verification confirms active index definitions for `idx_incidents_status_created` and `idx_alerts_external_id`.
*   **Estimated Complexity:** Medium (3 Story Points)

---

### Task 2: Define Kafka Alert Transfer Schemas
*   **Task Name:** `TASK-1.2: Kafka-Alert-Schemas`
*   **Purpose:** Enforce serialization format consistency for alert payloads published across Kafka.
*   **Files To Create:**
    *   `shared/python/common/schemas/alert_event.py` (Standard Pydantic model for alert ingestion)
    *   `shared/python/common/schemas/incident_event.py` (Standard Pydantic model for incident state events)
*   **Dependencies:** None.
*   **Acceptance Criteria:**
    1.  Alert Pydantic schemas successfully parse mock JSON configurations containing `service_name`, `severity`, and `raw_payload` attributes.
    2.  Incorrect payloads lacking mandatory parameters throw standard `ValidationError` errors.
*   **Estimated Complexity:** Low (1 Story Point)

---

### Task 3: Ingestion API Webhook Routers & Normalizers
*   **Task Name:** `TASK-1.3: Webhook-Ingress-Routers`
*   **Purpose:** Expose FastAPI REST endpoints to receive raw third-party webhooks and convert them to internal alert event structures.
*   **Files To Create:**
    *   `services/incident-commander-core/src/incident_commander_core/api/webhooks.py` (FastAPI webhook router)
    *   `services/incident-commander-core/src/incident_commander_core/infrastructure/normalizers/__init__.py`
    *   `services/incident-commander-core/src/incident_commander_core/infrastructure/normalizers/prometheus.py`
    *   `services/incident-commander-core/src/incident_commander_core/infrastructure/normalizers/pagerduty.py`
    *   `services/incident-commander-core/src/incident_commander_core/infrastructure/normalizers/datadog.py`
    *   `services/incident-commander-core/src/incident_commander_core/application/use_cases/ingest_alert.py` (Alert use case coordinator)
*   **Dependencies:** `TASK-1.2: Kafka-Alert-Schemas`.
*   **Acceptance Criteria:**
    1.  `POST /api/v1/webhooks/{source}` validates that `{source}` is one of `prometheus`, `pagerduty`, or `datadog`.
    2.  Adapter classes normalize incoming payloads to standard `AlertEvent` schemas correctly.
    3.  Endpoints return HTTP status `202 Accepted` along with the list of normalized alert IDs.
*   **Estimated Complexity:** Medium (3 Story Points)

---

### Task 4: Ingest Kafka Event Publisher Integration
*   **Task Name:** `TASK-1.4: Ingest-Kafka-Publisher`
*   **Purpose:** Publish normalized alert models to the Kafka `alerts-topic` broker.
*   **Files To Create/Modify:**
    *   `services/incident-commander-core/src/incident_commander_core/infrastructure/kafka/producer.py` (Core event publisher adapter)
*   **Dependencies:** `TASK-1.3: Webhook-Ingress-Routers`, `shared/python/messaging/kafka_producer.py`.
*   **Acceptance Criteria:**
    1.  Upon receiving an ingestion request, the core publisher pushes JSON serialized events to `alerts-topic`.
    2.  Messages are partitioned by `service_name`.
    3.  Kafka client configurations enforce idempotent execution (`enable.idempotence=True`) and complete message acknowledgments (`acks=all`).
*   **Estimated Complexity:** Low (2 Story Points)

---

### Task 5: Incident Correlation & Deduplication Consumer
*   **Task Name:** `TASK-1.5: Incident-Correlation-Consumer`
*   **Purpose:** Read raw alerts from Kafka, evaluate sliding temporal correlation windows, and update active database sessions.
*   **Files To Create:**
    *   `services/incident-commander-core/src/incident_commander_core/infrastructure/kafka/consumers.py` (Kafka alert consumer loops)
    *   `services/incident-commander-core/src/incident_commander_core/application/use_cases/correlate_alert.py` (Deduplication engine)
*   **Dependencies:** `TASK-1.1: DB-Migrations-Setup`, `TASK-1.4: Ingest-Kafka-Publisher`.
*   **Acceptance Criteria:**
    1.  The consumer loop reads from `alerts-topic`.
    2.  If an alert is consumed, checks PostgreSQL database for active incidents on the same service namespace in the last 10 minutes.
    3.  If matched, updates `alerts.incident_id`.
    4.  If unmatched, creates a new record in `incidents` with status `TRIGGERED` and links the alert.
    5.  Performs transactional session commits and commits Kafka partition offsets.
*   **Estimated Complexity:** High (5 Story Points)

---

### Task 6: Incident Lifecycle Event Broker
*   **Task Name:** `TASK-1.6: Incident-Lifecycle-Publisher`
*   **Purpose:** Publish incident state modifications to the `incident-topic` Kafka broker.
*   **Files To Modify:**
    *   `services/incident-commander-core/src/incident_commander_core/infrastructure/kafka/producer.py`
    *   `services/incident-commander-core/src/incident_commander_core/application/use_cases/correlate_alert.py`
*   **Dependencies:** `TASK-1.5: Incident-Correlation-Consumer`.
*   **Acceptance Criteria:**
    1.  Every time the database registers a new incident or updates an incident status, the system pushes an event to `incident-topic`.
    2.  Message payloads include `incident_id`, `service_name`, and `status`.
    3.  Partition key corresponds to `incident_id`.
*   **Estimated Complexity:** Low (1 Story Point)

---

### Task 7: End-to-End Local Ingestion Testing
*   **Task Name:** `TASK-1.7: E2E-Ingest-Test`
*   **Purpose:** Verify the unified workflow: Webhook → Ingestion Core → Kafka → Correlation Consumer → Postgres Database.
*   **Files To Create:**
    *   `services/incident-commander-core/tests/integration/test_alert_flow.py`
    *   `scripts/seed-test-data.sh` (Simulates alert triggers)
*   **Dependencies:** `TASK-1.1` through `TASK-1.6`.
*   **Acceptance Criteria:**
    1.  Boot local environment via `docker-compose up -d`.
    2.  Run `seed-test-data.sh` triggering 5 Prometheus webhook payloads.
    3.  Verify that PostgreSQL databases register 1 new Incident record and 5 Alert records mapped to the same incident ID.
*   **Estimated Complexity:** Medium (3 Story Points)
