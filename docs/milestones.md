# Project Milestones & Implementation Roadmap (Redesigned)

This document maps out the redesigned modular monolith engineering tasks, milestones, and deployment phases.

---

## Epic 1: Core Infrastructure & Local Environment Setup

Setup local environment services, database schemas, and object storage buckets.

- [ ] **Task 1.1: Multi-Container Local Scaffold**
  - Update `docker-compose.yml` to run: Single-node Kafka, PostgreSQL 16, MinIO (S3 clone), Qdrant, Redis, Prometheus, Grafana, and OpenTelemetry Collector.
- [ ] **Task 1.2: Alembic Migrations Setup**
  - Initialize Alembic within the shared python directory.
  - Implement relational DDL migrations for: `services` (with cool-down timestamp columns), `users`, `incidents` (with S3 telemetry key), `alerts`, and `audit_logs` (with parameterized variables and rollback YAML snapshot storage).
- [ ] **Task 1.3: Object Storage Initialization**
  - Configure automatic local bucket creation (`telemetry-snapshots`) in MinIO on container boot.
- [ ] **Task 1.4: Kafka Topic Creation Script**
  - Update KRaft broker topics: `alerts-topic` (3 partitions), `incident-topic` (2 partitions), `telemetry-enriched-topic` (3 partitions), and `rca-suggestions-topic` (2 partitions).

---

## Epic 2: Core Ingestion Module

Expose FastAPI webhook APIs, normalize payloads, and test local Kafka publication.

- [ ] **Task 2.1: FastAPI Webhook Receivers**
  - Build endpoints: `POST /api/v1/webhooks/prometheus`, `/webhooks/datadog`, `/webhooks/pagerduty` in `incident-commander-core`.
- [ ] **Task 2.2: Event Normalizers**
  - Write validation schemas converting webhook inputs into a standard Pydantic `AlertEvent`.
- [ ] **Task 2.3: Idempotent Alert Producer**
  - Publish normalized alerts to `alerts-topic` keyed by `service_name`. Ensure producer idempotence is enabled.

---

## Epic 3: Incident Engine Module

Track alert sessions, update PostgreSQL states, and deploy Slack connectors.

- [ ] **Task 3.1: Alert Correlation Consumer**
  - Implement consumer loop reading from `alerts-topic`.
- [ ] **Task 3.2: Temporal Deduplication Rules**
  - If a service alert triggers, check database for an active incident on the same service within a 10-minute sliding window. Group incoming alerts into the matched incident or spawn a new incident session with status `TRIGGERED`.
- [ ] **Task 3.3: Slack Channel Provisioning**
  - Connect to Slack workspace API to create dedicated channels upon receipt of an `incident-created` event.

---

## Epic 4: Telemetry Aggregator Module

Query logs/metrics, sanitize variables, and write blocks to MinIO object storage.

- [ ] **Task 4.1: Telemetry Fetcher Worker**
  - Build consumer listening to `incident-topic` (filtering for `CREATED` states).
- [ ] **Task 4.2: Loki / Prometheus Drivers**
  - Execute API queries to Loki (logs) and Prometheus (metrics time-series) mapping the service network namespace over the outage window (T-15m to T).
- [ ] **Task 4.3: Masking & Scrubbing Middleware**
  - Run regex sanitization loops to obfuscate auth tokens, passwords, database credentials, emails, and IPs.
- [ ] **Task 4.4: MinIO S3 Object Upload**
  - Bundle scrubbed logs and metric schemas into a single JSON snapshot payload.
  - Upload snapshot to MinIO bucket and publish the S3 object key to `telemetry-enriched-topic`.

---

## Epic 5: AI RCA & Redis Semantic Cache

Compute embeddings, search Qdrant vector databases, evaluate Redis caches, and run LLM reasoning loops.

- [ ] **Task 5.1: Qdrant Runbook Indexer Script**
  - Build ingestion job to chunk Markdown runbooks, compute embeddings via Gemini API (`text-embedding-004`), and write vectors to Qdrant collections.
- [ ] **Task 5.2: Redis Semantic Cache Integration**
  - Connect to Redis cluster. Generate symptom embedding from alert metadata and query Redis for similar symptoms (similarity threshold > 0.98). If cached, return the diagnostic suggestion immediately.
- [ ] **Task 5.3: Gemini API Orchestration Engine**
  - On cache miss, retrieve telemetry JSON from MinIO, get top runbooks from Qdrant, construct the prompt template, and execute the Gemini LLM reasoning loop.
  - Enforce JSON schemas to validate returned keys (`root_cause`, `confidence_score`, `evidence_chain`, `remediation_steps`).
- [ ] **Task 5.4: Command Validation Parser**
  - Parse LLM-recommended remediation commands, verify syntax blocks, strip unsafe symbols, and publish parameterized actions to `rca-suggestions-topic`.

---

## Epic 6: Secure Action-Runner Service

Build the Kubernetes client runner, verify user RBAC scopes, back up manifests, and lock remediation loops.

- [ ] **Task 6.1: Secure Action-Runner Endpoint**
  - Implement `POST /api/v1/actions/execute` router in the isolated `action-runner-service`.
- [ ] **Task 6.2: Identity Context Resolver**
  - Map incoming Slack user tokens to LDAP/Kubernetes namespaces RBAC rules.
- [ ] **Task 6.3: Kubernetes Python Client Integration**
  - Implement parameterized SDK execution logic (no shell subprocesses). Support actions like `RESTART_POD`, `SCALE_DEPLOYMENT`, `ROLLBACK`.
- [ ] **Task 6.4: Resource Backup Manifest Snapshot**
  - Before applying any cluster modifications, query current resource specs, parse them to YAML strings, and save them to `audit_logs.backup_state_yaml` to support SRE one-click rollbacks.
- [ ] **Task 6.5: Remediation Cool-down Locks**
  - Upon executing remediation, set `under_remediation_until = NOW() + 15m` on the database `services` record. Block automated reasoning execution loops for this service until the timestamp expires.

---

## Epic 7: Post-Mortems, Slack UI, and Frontend Dashboard

- [ ] **Task 7.1: Post-Mortem Compilation Service**
  - Generate Confluence markdown reviews and timelines on incident resolution.
- [ ] **Task 7.2: Slack Block Kit Interactive Cards**
  - Code Slack API payload cards displaying diagnostic summaries and approval actions.
- [ ] **Task 7.3: Next.js Frontend Dashboard**
  - Build unified SRE dashboard displaying ongoing incidents, active Slack channels, telemetry snapshot URLs, audit records, and action logs.
