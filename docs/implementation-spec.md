# Technical Implementation Specification: AI Incident Commander

**Author:** Staff Software Engineer  
**Status:** Ready for Coding  
**Version:** 1.0.0  
**Target Runtime:** Python 3.12+ / FastAPI / Confluent Kafka / PostgreSQL 16 / MinIO / Qdrant / Redis  

---

## 1. Ingestion Gateway (Commander Core API Router)

### 1.1 Purpose
Acts as the ingress gateway for all external incoming alerts (webhooks) and frontend queries, providing payload validation, schema normalization, and asynchronous publishing to Kafka.

### 1.2 Responsibilities
*   Exposes public FastAPI REST routes for alert webhook receivers.
*   Enforces Pydantic schema validation mapping third-party alerts into standardized models.
*   Publishes normalized alerts asynchronously to the `alerts-topic` Kafka topic.
*   Provides REST query endpoints for UI state synchronization and configuration views.

### 1.3 Inputs
*   **API Webhooks:** HTTP `POST /api/v1/webhooks/{source}` (Sources: `prometheus`, `datadog`, `pagerduty`).
*   **User Queries:** HTTP `GET /api/v1/incidents`, `/api/v1/incidents/{id}`, `/api/v1/services`.

### 1.4 Outputs
*   **Kafka Events:** Standardized JSON serialized alert models pushed to `alerts-topic`.
*   **HTTP Responses:** REST standard JSON responses (e.g., `202 Accepted` with generated tracking UUIDs).

### 1.5 Dependencies
*   `fastapi` & `uvicorn` (ASGI app stack)
*   `pydantic` (Data schema validation)
*   `confluent-kafka` (High-performance Kafka publisher client)
*   `sqlalchemy` (Relational query mappings)

### 1.6 Database Interactions
*   Reads tables `incidents`, `services`, and `audit_logs` for user dashboard API calls.
*   *Write operations:* None (delegated strictly to the Incident Engine consumer to avoid API lock conflicts).

### 1.7 Kafka Interactions
*   **Producer:** Publishes to `alerts-topic`.
    *   **Partition Key:** `service_name` (forces serial ordering of alerts per service namespace).
    *   **Acks:** `all` (100% durability confirmation).
    *   **Idempotency:** Enabled (`enable.idempotence=True`).

### 1.8 Failure Handling
*   **Kafka Broker Outage:** If Kafka fails to acknowledge message write within `max.in.flight.requests.per.connection`, cache alert locally to memory, log error, and return `503 Service Unavailable`.
*   **Payload Validation Errors:** Catch `ValidationError` exceptions and return `400 Bad Request` with structured JSON errors indicating specific missing fields.

### 1.9 Logging Strategy
*   Structured logging via `structlog`.
*   Inject `X-Request-ID` and correlation headers in every response context.
*   Log signature example: `{"event": "alert_received", "source": "prometheus", "service_name": "payment-auth", "request_id": "uuid-..."}`.

### 1.10 Testing Strategy
*   **Unit Tests:** Pytest using `FastAPI.testclient` mocking the Kafka producer client.
*   **Integration Tests:** Test HTTP endpoints against mock payload inputs, validating correct extraction of `service_name` and `severity`.

---

## 2. Incident Engine (Deduplication & State Machine)

### 2.1 Purpose
Handles real-time alert deduplication, incident session mapping, and incident state transitions in the PostgreSQL database.

### 2.2 Responsibilities
*   Consumes normalized alert payloads from the `alerts-topic`.
*   Runs temporal correlation logic to identify if alerts belong to an active incident session.
*   Updates PostgreSQL incident records and logs audit trails.
*   Publishes lifecycle events (`CREATED`, `ACKNOWLEDGED`, `RESOLVED`) to the `incident-topic`.

### 2.3 Inputs
*   **Kafka Stream:** Consumes events from `alerts-topic`.

### 2.4 Outputs
*   **Kafka Events:** Pushes lifecycle records (`IncidentEvent`) to `incident-topic`.
*   **Database:** Modifies PostgreSQL state tables (`incidents`, `alerts`).

### 2.5 Dependencies
*   `sqlalchemy` (Declarative ORM)
*   `psycopg2-binary` (Postgres driver library)
*   `confluent-kafka` (Consumer client)

### 2.6 Database Interactions
*   **Read:** Queries `incidents` table for active alerts matching `service_id` within a 10-minute window (`created_at > NOW() - INTERVAL '10 minutes'`).
*   **Write:** 
    *   Inserts new records into `incidents` and updates statuses.
    *   Inserts mapping records linking raw `alerts` to the matched `incident_id`.

### 2.7 Kafka Interactions
*   **Consumer:** Subscribes to `alerts-topic`.
    *   **Consumer Group:** `incident-manager`.
*   **Producer:** Publishes to `incident-topic`.
    *   **Partition Key:** `incident_id` (ensures order of status changes per incident session).

### 2.8 Failure Handling
*   **Concurrency Conflicts:** Catch `StaleDataError` or transactional deadlock exceptions. Implement a maximum of 3 retry iterations with incremental backoffs.
*   **Deserialization Failures:** Catch JSON parse errors. Route corrupt payloads directly to an `alerts-dlq` (Dead Letter Queue) topic and commit offset to prevent pipeline blockages.

### 2.9 Logging Strategy
*   Track state machine lifecycle events explicitly:
    *   `{"event": "incident_created", "incident_id": "uuid", "service_name": "payment-auth"}`.
    *   `{"event": "alert_correlated", "incident_id": "uuid", "alert_id": "uuid"}`.

### 2.10 Testing Strategy
*   Mock consumer input streams using pytest.
*   Use an isolated PostgreSQL Docker instance to verify correct behavior of the 10-minute correlation window query under high concurrency.

---

## 3. Telemetry Aggregator

### 3.1 Purpose
Gathers Loki logs, Prometheus metrics, and system tracing summaries for active incidents, masks private credentials, and uploads the snapshots to MinIO.

### 3.2 Responsibilities
*   Listens for `incident-topic` events with state `CREATED`.
*   Queries Prometheus APIs for CPU, RAM, and error-rate query graphs.
*   Queries Loki API for system standard logs snapshots around the incident window.
*   Runs regex masking sweeps to strip PII and secret keys.
*   Writes unified payloads to MinIO and publishes keys to Kafka.

### 3.3 Inputs
*   **Kafka Events:** Consumes `incident-topic` (`CREATED` state).
*   **Telemetry APIs:** API query outputs from Loki, Prometheus, and Jaeger.

### 3.4 Outputs
*   **MinIO Upload:** Pushes consolidated telemetry snapshots to the `telemetry-snapshots` bucket.
*   **Kafka Events:** Publishes snapshot key to `telemetry-enriched-topic`.

### 3.5 Dependencies
*   `httpx` (Asynchronous HTTP library for querying metric/log REST APIs)
*   `aioboto3` (Asynchronous SDK for S3/MinIO integrations)
*   `re` (String regex parsing engines)

### 3.6 Database Interactions
*   **Read:** Queries the `services` table to resolve target service names to specific Kubernetes namespaces and Prometheus label selectors.

### 3.7 Kafka Interactions
*   **Consumer:** Subscribes to `incident-topic`.
    *   **Consumer Group:** `telemetry-gatherer`.
*   **Producer:** Publishes to `telemetry-enriched-topic`.
    *   **Partition Key:** `incident_id`.

### 3.8 Failure Handling
*   **Metric Outage:** If Prometheus or Loki APIs are down/timeout, log warning, skip logs collection, package the metadata that is currently available, and proceed. Do not block the RCA pipeline due to metric API timeouts.
*   **PII Masking Failure:** If the regex module fails to run or throws an exception, intercept the execution, block payload uploads, and publish a failure notification.

### 3.9 Logging Strategy
*   Log metric scraping metrics:
    *   `{"event": "telemetry_collected", "incident_id": "uuid", "log_lines": 450, "duration_ms": 1200}`.
    *   `{"event": "pii_scrubbed", "masked_patterns_count": 14}`.

### 3.10 Testing Strategy
*   Implement integration mocks using HTTP mocks to return pre-configured metric JSON files.
*   Write unit tests asserting regex replacements on database connections strings, keys, and email formats.

---

## 4. MinIO Storage Layer

### 4.1 Purpose
Stores raw, unstructured telemetry metrics, and logs snapshot files, providing durable out-of-band document retrieval for the AI reasoning pipeline.

### 4.2 Responsibilities
*   Exposes secure S3-compatible APIs for uploading and downloading incident JSON payloads.
*   Enforces object-lifecycle bucket rules (auto-expiration of telemetry objects after 30 days).

### 4.3 Inputs
*   **Writes:** Masked telemetry log blocks and metric arrays via S3 Client APIs.
*   **Reads:** S3 Object fetch requests using pre-signed object keys.

### 4.4 Outputs
*   Serialized JSON telemetry payload files.

### 4.5 Dependencies
*   `aioboto3` (Python async Amazon S3 client SDK)
*   MinIO container/service cluster.

### 4.6 Database Interactions
*   None.

### 4.7 Kafka Interactions
*   None.

### 4.8 Failure Handling
*   **MinIO Node Down:** If S3 APIs are unreachable, retry 3 times with exponential backoff. On persistent failure, write context to local host disk backup directories and log warning.

### 4.9 Logging Strategy
*   Log object storage operations:
    *   `{"event": "s3_upload_success", "bucket": "telemetry-snapshots", "key": "incident-uuid.json", "size_bytes": 104523}`.

### 4.10 Testing Strategy
*   Execute tests against an `aioboto3` mock or a lightweight local MinIO container. Validate S3 lifecycle expiration commands.

---

## 5. AI RCA Engine

### 5.1 Purpose
Coordinates vector lookup, evaluates semantic caches, triggers LLM reasoning loops (Gemini), and outputs structured incident hypotheses and remediation steps.

### 5.2 Responsibilities
*   Consumes enriched telemetry events from `telemetry-enriched-topic`.
*   Downloads target telemetry snapshots from MinIO.
*   Sends alert signatures to the Redis Semantic Cache and checks for hits.
*   Queries Qdrant to retrieve matching runbook steps.
*   Assembles context, invokes Gemini API, parses JSON, and filters proposed commands for shell injections.
*   Publishes results to `rca-suggestions-topic`.

### 5.3 Inputs
*   **Kafka Stream:** Consumes from `telemetry-enriched-topic`.
*   **Object Data:** Telemetry JSON snapshot from MinIO.
*   **Search Indices:** Vector outputs from Redis and Qdrant.

### 5.4 Outputs
*   **Kafka Events:** Publishes structured diagnostic reports to `rca-suggestions-topic`.

### 5.5 Dependencies
*   `google-generativeai` (Official Google LLM client library)
*   `qdrant-client` (Vector DB client SDK)
*   `redis` (Cache client SDK)
*   `aioboto3` (MinIO downloader)

### 5.6 Database Interactions
*   **Read:** Queries `incidents` and `services` to check if a service is in a remediation cool-down state (`under_remediation_until > NOW()`). If locked, skip automated suggestion generation.

### 5.7 Kafka Interactions
*   **Consumer:** Subscribes to `telemetry-enriched-topic`.
    *   **Consumer Group:** `rca-processor`.
*   **Producer:** Publishes to `rca-suggestions-topic`.
    *   **Partition Key:** `incident_id`.

### 5.8 Failure Handling
*   **LLM Rate Limits (429):** Catch Google API rate limit exceptions. Wait and retry with jittered exponential backoffs. If failures persist, emit a default warning card to Slack indicating diagnostic failures.
*   **JSON Schema Validation Failures:** If the model outputs broken JSON, retry model invocation with an explicit validation error prompt. Max retries: 2.

### 5.9 Logging Strategy
*   Log LLM metrics:
    *   `{"event": "llm_call_initiated", "incident_id": "uuid"}`.
    *   `{"event": "llm_call_success", "duration_ms": 3400, "input_tokens": 12000, "output_tokens": 520}`.
    *   `{"event": "command_blocked", "incident_id": "uuid", "blocked_command": "kubectl delete ns prod"}`.

### 5.10 Testing Strategy
*   Mock Google Gemini client responses with pre-recorded correct JSON and incorrect validation scripts.
*   Verify safety parser filters against a suite of injection payloads (e.g. commands containing `;`, `|`, or `rm -rf`).

---

## 6. Redis Semantic Cache

### 6.1 Purpose
Maintains a cache of alert embeddings and previous diagnostic outputs to avoid redundant calls to the Gemini API during repetitive alert storms.

### 6.2 Responsibilities
*   Computes embedding vectors for incoming alert symptoms.
*   Queries Redis indexes using cosine similarity parameters.
*   Writes successful Gemini diagnostic payloads to Redis with a 5-minute TTL.

### 6.3 Inputs
*   Symptom text descriptions and query embedding vectors.

### 6.4 Outputs
*   Matched diagnostic JSON payload (on cache hit) or null flag (on cache miss).

### 6.5 Dependencies
*   `redis` (Python client SDK)
*   `google-generativeai` (for generating query embeddings via `text-embedding-004`).

### 6.6 Database / Kafka Interactions
*   None.

### 6.7 Failure Handling
*   **Redis Offline:** If Redis fails to connect or timeouts, log warning, skip cache lookup, and proceed directly to LLM generation. Do not block the RCA pipeline due to cache outages.

### 6.8 Logging Strategy
*   Track hit/miss metrics:
    *   `{"event": "cache_lookup", "status": "HIT", "similarity_score": 0.992, "incident_id": "uuid"}`.
    *   `{"event": "cache_lookup", "status": "MISS", "incident_id": "uuid"}`.

### 6.9 Testing Strategy
*   Use pytest-mock to simulate Redis query returns.
*   Verify that cache expiration logic (5-minute TTL) is set correctly on cache writes.

---

## 7. Qdrant Retrieval Layer

### 7.1 Purpose
Stores and performs HNSW vector similarity searches on system runbooks and historical incident post-mortems.

### 7.2 Responsibilities
*   Indexes markdown documentation chunks and historical incident resolution metadata.
*   Performs metadata-filtered vector searches (pre-filtering search space by `service_name`).

### 7.3 Inputs
*   Query embedding vectors (1536 dimensions) and service tags.

### 7.4 Outputs
*   List of Top-K matched runbook commands and past resolution markdown segments.

### 7.5 Dependencies
*   `qdrant-client` (Vector client SDK)

### 7.6 Database / Kafka Interactions
*   None.

### 7.7 Failure Handling
*   **Search Failures:** If Qdrant is offline or queries timeout (>2 seconds), log error and return an empty context list. The prompt will fallback to default system prompt guidelines.

### 7.8 Logging Strategy
*   `{"event": "vector_search", "collection": "runbooks", "matches_found": 3, "latency_ms": 12}`.

### 7.9 Testing Strategy
*   Configure pytest to execute queries against a local memory-based Qdrant client (`QdrantClient(":memory:")`).

---

## 8. Action Runner

### 8.1 Purpose
Runs Kubernetes and Cloud provider API tasks in response to user approvals, executing within a separate, isolated, high-security container.

### 8.2 Responsibilities
*   Exposes a secure REST route `POST /api/v1/actions/execute`.
*   Validates user identity and RBAC authorization permissions.
*   Captures current Kubernetes resource configuration specs as backup manifest strings.
*   Executes actions strictly using official Python Client SDK libraries.
*   Updates execution audit records in PostgreSQL.

### 8.3 Inputs
*   **HTTP Requests:** HTTP `POST /api/v1/actions/execute` with target command action, parameters, and user auth tokens.

### 8.4 Outputs
*   **API call returns:** HTTP `200 OK` with execution results or `403 Forbidden` if validation checks fail.
*   **K8s Actions:** API operations to target Kubernetes namespaces.

### 8.5 Dependencies
*   `kubernetes` (Official Python Client SDK library)
*   `sqlalchemy` & `psycopg2-binary` (PostgreSQL client integration)
*   `pydantic` (Input parameter validation)

### 8.6 Database Interactions
*   **Read:** Queries `services` to check if a cool-down lock exists (`under_remediation_until`).
*   **Write:** 
    *   Inserts new audit records to `audit_logs` (storing `backup_state_yaml` before execution).
    *   Updates `services` table, setting `under_remediation_until = NOW() + INTERVAL '15 minutes'`.

### 8.7 Kafka Interactions
*   None (Inter-service triggers run over secure internal HTTPS API calls).

### 8.8 Failure Handling
*   **Kubernetes API Failures:** If K8s API throws a timeout or error, capture standard stderr/exception strings, write status `FAILED` to `audit_logs`, and bubble up exception to the REST caller.

### 8.9 Logging Strategy
*   Strict security audit logs:
    *   `{"event": "action_execution_requested", "user": "user-id", "action": "RESTART_POD", "parameters": {"pod": "x", "namespace": "y"}}`.
    *   `{"event": "action_execution_success", "audit_log_id": "uuid", "k8s_response_code": 200}`.
    *   `{"event": "action_execution_unauthorized", "user": "user-id", "action": "RESTART_POD"}`.

### 8.10 Testing Strategy
*   Mock Kubernetes CoreV1Api and AppsV1Api endpoints in pytest tests to prevent making active network calls to live cluster pools.
*   Test namespace boundaries, asserting that requesting namespace parameters outside SRE RBAC triggers a `403 Forbidden` error.

---

## 9. Postmortem Generator

### 9.1 Purpose
Generates post-incident timelines, writes root-cause markdown summaries, updates Jira/Confluence wikis, and writes embeddings back to Qdrant.

### 9.2 Responsibilities
*   Listens for `incident-topic` events with status `RESOLVED`.
*   Gathers incident metadata, alerts history, and execution audit trails.
*   Calls LLM (Gemini) to format timeline arrays and markdown summaries.
*   Pushes reports to Confluence REST APIs.
*   Computes embeddings for the incident summary and stores them in Qdrant.

### 9.3 Inputs
*   **Kafka Events:** Consumes `incident-topic` (`RESOLVED` status).
*   **Database:** Queries PostgreSQL audit trail tables.

### 9.4 Outputs
*   Confluence pages created via HTTP APIs.
*   Vector updates pushed to Qdrant.

### 9.5 Dependencies
*   `confluent-kafka` (Consumer client)
*   `google-generativeai` (Gemini SDK client)
*   `qdrant-client` (Vector client SDK)
*   `httpx` (for Confluence/Jira REST API integrations)

### 9.6 Database Interactions
*   **Read:** Queries `incidents`, `alerts`, and `audit_logs` matching the resolved `incident_id`.

### 9.7 Kafka Interactions
*   **Consumer:** Subscribes to `incident-topic`.
    *   **Consumer Group:** `postmortem-generator`.

### 9.8 Failure Handling
*   **Confluence API Timeout:** If wiki uploads fail, store the generated markdown file locally to a PostgreSQL column in the `post_mortems` table and retry the push in a background task hourly.

### 9.9 Logging Strategy
*   `{"event": "postmortem_generation_triggered", "incident_id": "uuid"}`.
*   `{"event": "confluence_sync_success", "page_id": "1940283", "incident_id": "uuid"}`.

### 9.10 Testing Strategy
*   Mock the Confluence HTTP publishing endpoints using pytest HTTP mocking tools.
*   Verify correct compilation of the incident timeline JSON array.
