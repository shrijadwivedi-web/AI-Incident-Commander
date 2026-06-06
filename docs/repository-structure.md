# Technical Specification: Final Repository Structure

**Author:** Principal Systems Architect / Technical Lead  
**Status:** Approved  
**Date:** June 7, 2026

---

## Part 1: Directory Tree Layout

The AI Incident Commander monorepo is structured to enforce strict boundaries between the core monolith engine, the high-security action runner microservice, shared libraries, and local infrastructure configuration.

```text
AI-Incident-Commander/
├── docs/                             # System Design & Specification Documentation
│   ├── PRD.md
│   ├── architecture.md
│   ├── tech-decisions.md
│   ├── milestones.md
│   ├── implementation-spec.md
│   └── repository-structure.md
├── infra/                            # Infrastructure and Deployment Manifests
│   ├── docker/
│   │   └── compose/
│   │       ├── docker-compose.yml
│   │       └── .env.example
│   ├── kafka/
│   │   └── topics/
│   │       └── create-topics.sh
│   ├── kubernetes/
│   │   ├── core-deployment.yaml
│   │   ├── runner-deployment.yaml
│   │   └── network-policies.yaml
│   └── observability/
│       ├── prometheus/
│       │   └── prometheus.yml
│       ├── otel/
│       │   └── otel-collector-config.yaml
│       └── grafana/
│           └── provisioning/
├── services/                         # Service Runtimes
│   ├── incident-commander-core/      # FastAPI Modular Monolith Runtime
│   │   ├── src/
│   │   │   └── incident_commander_core/
│   │   │       ├── api/
│   │   │       │   ├── health.py
│   │   │       │   ├── webhooks.py
│   │   │       │   └── incidents.py
│   │   │       ├── application/
│   │   │       │   ├── use_cases/
│   │   │       │   └── ports/
│   │   │       ├── domain/
│   │   │       │   └── models.py
│   │   │       ├── infrastructure/
│   │   │       │   ├── kafka/
│   │   │       │   ├── storage/
│   │   │       │   ├── vector/
│   │   │       │   └── cache/
│   │   │       └── main.py
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   └── integration/
│   │   └── pyproject.toml
│   │
│   └── action-runner-service/         # High-Security Isolated Microservice
│       ├── src/
│       │   └── action_runner/
│       │       ├── api/
│       │       │   └── execute.py
│       │       ├── application/
│       │       ├── infrastructure/
│       │       │   ├── k8s/
│       │       │   └── vault/
│       │       └── main.py
│       ├── tests/
│       │   ├── unit/
│       │   └── integration/
│       └── pyproject.toml
│
├── shared/                           # Shared Python Workspaces
│   └── python/
│       ├── common/
│       │   ├── schemas/
│       │   │   ├── alert_event.py
│       │   │   ├── incident_event.py
│       │   │   └── rca_event.py
│       │   └── utils/
│       │       ├── pii_scrubber.py
│       │       └── security_parser.py
│       └── pyproject.toml
│
├── scripts/                          # Diagnostic & Setup Automation
│   ├── index-runbooks.py             # Parses & embeds markdown runbooks
│   └── seed-test-data.sh             # Dispatches mock webhooks
│
├── .gitignore
├── pyproject.toml                    # Monorepo Workspace Configuration
└── README.md
```

---

## Part 2: Detailed Directory Mapping

### 1. `docs/`
*   **Purpose:** Houses all system architecture designs, PRDs, database schema mappings, implementation checklists, and repository directories.
*   **Responsibility:** Provides the single source of truth for architectural planning and project milestones.
*   **Major Files:**
    *   `PRD.md` — Product scope, success targets, and personas.
    *   `architecture.md` — Redesigned event-driven modular monolith topology.
    *   `tech-decisions.md` — Relational schema DDL scripts and vector db configurations.
    *   `implementation-spec.md` — Granular technical specification per component.

### 2. `infra/`
*   **Purpose:** Container configurations, Kubernetes manifests, and observability setup templates.
*   **Responsibility:** Configures and boots the local development cluster environment and governs production network policies.
*   **Major Files:**
    *   `docker-compose.yml` — Container definitions for Kafka, PostgreSQL, MinIO, Redis, Qdrant, and Grafana.
    *   `create-topics.sh` — Automates creation of Kafka topics with explicit partition parameters.
    *   `prometheus.yml` / `otel-collector-config.yaml` — Configures system trace and metric collection ports.

### 3. `services/incident-commander-core/`
*   **Purpose:** The central logic runtime of the platform, packaged as a Modular Monolith.
*   **Responsibility:** Handles webhook ingestion, SQL database mapping, temporal deduplication rules, Loki log scraping, MinIO snapshot uploads, Redis cache matches, and Gemini LLM reasoning.
*   **Major Files:**
    *   `main.py` — Boots FastAPI, configures middlewares, and registers lifespan task hooks.
    *   `api/webhooks.py` — Ingestion routes for PagerDuty, Prometheus, and Datadog.
    *   `application/use_cases/correlate_alert.py` — Deduplicates alerts inside SQL sliding windows.
    *   `infrastructure/storage/s3_client.py` — Coordinates log snapshot uploads to MinIO.
    *   `infrastructure/cache/redis_cache.py` — Runs symptoms similarity lookups.

### 4. `services/action-runner-service/`
*   **Purpose:** High-security microservice execution runtime.
*   **Responsibility:** Verifies SRE OAuth identity and RBAC authorization profiles, captures YAML manifest backups of cluster states, and runs parameterized operations against target APIs.
*   **Major Files:**
    *   `main.py` — FastAPI server engine.
    *   `api/execute.py` — REST route exposing the `/actions/execute` executor.
    *   `infrastructure/k8s/k8s_client.py` — Executes actions using the official Kubernetes Python Client SDK (no shell pipelines).

### 5. `shared/python/`
*   **Purpose:** Shared monorepo workspaces package.
*   **Responsibility:** Houses models and sanitization utilities shared between the core monolith and the action runner microservice.
*   **Major Files:**
    *   `common/schemas/alert_event.py` — Standardized schema for Kafka alert transfer.
    *   `common/utils/pii_scrubber.py` — Regex tokenizer scrubbing private keys and credentials.
    *   `common/utils/security_parser.py` — Parses arguments to enforce parameter safety limits.

### 6. `scripts/`
*   **Purpose:** Setup and testing automation.
*   **Responsibility:** Indexes markdown runbooks into Qdrant vectors and runs alert simulations.
*   **Major Files:**
    *   `index-runbooks.py` — Computes embeddings via Gemini API and loads vectors to Qdrant.
    *   `seed-test-data.sh` — Shell script simulating Prometheus error spikes.

---

## Part 3: Architecture Rationale

1.  **Modular Monolith Boundary Enforcements:** Modules are separated into individual Python namespaces (`api`, `application`, `domain`, `infrastructure`) within the same core package directory. They share database models (`domain/models.py`) and connection pooling, completely eliminating inter-service network connection failures and resource consumption overhead.
2.  **Isolated Action Runner:** The `action-runner-service` is separated into its own service folder to enforce strict container isolation. Since it holds high-privilege administrative keys to the target cloud and Kubernetes APIs, it must not run on the same virtual network space or pod as the public-facing API routes of the core monolith.
3.  **Shared Directory Decoupling:** Reusable schemas and utility libraries (like the PII scrubber) are kept in `shared/python/common`. This prevents import cycle dependencies between modules and ensures consistent validation schemas across different microservices.
