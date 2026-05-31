# Project Milestones & Engineering Backlog

This document translates the Product Requirements (PRD) and Technical Architecture into structured Epics and granular engineering tasks.

---

## Epic 1: Core Infrastructure Setup

Establish the monorepo structure, local dev containerization, databases, and message bus.

- [ ] **Task 1.1: Monorepo Scaffolding**
  - Setup Python poetry workspaces for shared models, configuration systems, and individual service packages (`ingestion`, `incident`, `telemetry`, `rca`, `runner`, `postmortem`).
- [ ] **Task 1.2: Local Development Docker Setup**
  - Write `docker-compose.yml` for local components: Single-node Kafka + Zookeeper/KRaft, PostgreSQL 16, Qdrant, OpenTelemetry Collector, Prometheus, and Grafana.
- [ ] **Task 1.3: PostgreSQL Schema Migration Configuration**
  - Setup Alembic database migration directories.
  - Write DDL migrations for: `services`, `users`, `incidents`, `alerts`, `logs`, and `post_mortems`.
- [ ] **Task 1.4: Kafka Broker & Topic Initialization Script**
  - Create setup script to provision topics: `alerts-topic` (4 partitions), `logs-topic` (6 partitions), `metrics-topic` (6 partitions), `incident-topic` (3 partitions), and `rca-topic` (3 partitions).

---

## Epic 2: Ingestion & Telemetry Pipeline

Build alert webhooks ingestion, payload normalization, and telemetry metric/log extraction.

- [ ] **Task 2.1: Ingestion API Webhook Receivers**
  - Build FastAPI endpoints for `POST /api/v1/webhooks/prometheus`, `datadog`, and `pagerduty`.
- [ ] **Task 2.2: Payload Normalization & Validation**
  - Implement Pydantic schema validation mapping each third-party format into a standard internal `AlertEvent` schema.
- [ ] **Task 2.3: Alert Kafka Producer**
  - Implement non-blocking Kafka producers in the `ingestion-service` pushing validated alert events to `alerts-topic` keyed by `service_name`.
- [ ] **Task 2.4: PII & Credentials Masking Filter**
  - Build a telemetry sanitization utility using regex patterns and tokenizers to strip passwords, API keys, tokens, emails, and IPs from raw log fields.
- [ ] **Task 2.5: Telemetry Aggregator Consumer**
  - Build `telemetry-aggregator-service` consumer listening to `incident-topic` (`CREATED` events).
  - Write integration drivers to query logs from Loki and metrics from Prometheus for target service boundaries over the incident time-window.
  - Publish sanitized outputs to `logs-topic` and `metrics-topic`.

---

## Epic 3: Incident Logic Engine

Build deduplication rules, active incident tracking, and Slack channel provisioning.

- [ ] **Task 3.1: Alert Deduplication Consumer**
  - Write consumer in `incident-service` subscribing to `alerts-topic`.
- [ ] **Task 3.2: Correlation & Grouping Processor**
  - Implement a sliding-window correlation algorithm: group incoming alerts into a single active `Incident` database record if they share `service_name` within a 10-minute window.
- [ ] **Task 3.3: Incident State Machine Lifecycle**
  - Code the relational state transition checks: `TRIGGERED` -> `ACKNOWLEDGED` -> `RESOLVED`.
  - Ensure state changes publish standardized status events to `incident-topic`.
- [ ] **Task 3.4: Slack Channel Provisioning integration**
  - Write integration with Slack API to create a dedicated incident channel (e.g., `#incident-payment-gateway-102`) upon receiving an `incident-created` event.

---

## Epic 4: AI RCA & Reasoning Engine

Implement semantic chunking, Qdrant search indexing, and LLM reasoning prompts.

- [ ] **Task 4.1: Qdrant Database Client & Embedding Service**
  - Initialize Qdrant collection setup scripts (`historical_incidents` and `runbooks`).
  - Integrate Gemini embedding API client for vectorizing textual metadata.
- [ ] **Task 4.2: Runbook & Post-Mortem Indexing Pipeline**
  - Develop a script to parse repository Markdown runbooks, chunk them semantically, compute embeddings, and load them into Qdrant.
- [ ] **Task 4.3: AI RCA Engine Consumer**
  - Build consumer in `ai-rca-service` reading from `logs-topic` and `metrics-topic` with a co-partition join grouped by `incident_id`.
- [ ] **Task 4.4: Context Constructor (RAG)**
  - Implement semantic search queries to Qdrant using telemetry symptoms to fetch the Top-3 matching runbooks and past incidents.
- [ ] **Task 4.5: Orchestration Prompt & LLM Execution**
  - Write Orchestrator prompts integrating system state, logs, metrics, and RAG data.
  - Call Gemini API requesting strict structured JSON outputs mapping to the `RcaPayload` schema.
- [ ] **Task 4.6: Command Security Syntax Parser**
  - Integrate a shell command syntax lexer to parse LLM-suggested commands and filter out destructive characters or commands. Publish safe commands to `rca-topic`.

---

## Epic 5: Action Runner & Slack Interaction Loop

Create the command executor, security permission checkers, and interactive ChatOps buttons.

- [ ] **Task 5.1: Action Runner Execution Endpoint**
  - Implement `POST /api/v1/actions/execute` in `action-runner-service`.
- [ ] **Task 5.2: Security & RBAC Validator**
  - Build validation check confirming the engineer's OAuth Slack ID matches target Kubernetes namespace execution policies in Vault.
- [ ] **Task 5.3: Safe Kubernetes Subshell Runner**
  - Write Python subprocess wrappers to run safe `kubectl` commands against namespaces and capture standard stdout/stderr outputs.
- [ ] **Task 5.4: Slack Interactive App Connector**
  - Build interactive Block Kit message payload generators to push RCA SitReps and command confirmation buttons to Slack channels.
  - Expose API to handle Slack interactive button callbacks (triggering runner approval actions).

---

## Epic 6: Post-Mortem & Knowledge Base Ingestion

Synthesize incident timelines, publish reports, and ingest them back into Qdrant.

- [ ] **Task 6.1: Post-Mortem Event Aggregator**
  - Build a telemetry collector to pull the incident audit trail, Slack chat histories, and resolved alerts upon receiving an `incident-resolved` signal.
- [ ] **Task 6.2: Timeline & Markdown Post-Mortem LLM Builder**
  - Design prompt structure instructing LLM to generate chronologically correct timeline JSON arrays and detailed root-cause markdown summaries.
- [ ] **Task 6.3: Confluence & Jira Publisher Integration**
  - Write client API drivers to publish drafted post-mortems to Confluence wiki pages and link them to corresponding Jira tickets.
- [ ] **Task 6.4: Post-Mortem Vector Ingestion**
  - Compute embeddings for the resolved incident summary and index the metadata vector back into Qdrant's `historical_incidents` collection for future RAG queries.
