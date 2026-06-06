"""initial_schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-07 00:00:00.000000

Creates the initial database schema for AI Incident Commander v1.

Tables created:
  - services       : Registered microservices monitored by the system.
  - users          : Operators and on-call engineers.
  - incidents      : Active and historical incidents.
  - alerts         : Raw alert payloads that may trigger incidents.
  - audit_logs     : Immutable record of every automated/manual action taken.
  - post_mortems   : Post-incident analysis documents.

Design notes:
  * All primary keys are UUID v4 to avoid sequential ID guessing and to
    support eventual multi-region sharding without key conflicts.
  * JSONB columns (raw_payload, parameters, timeline_json, remediation_items)
    allow schema-free storage of alert payloads and action parameters without
    sacrificing indexability.
  * Every table has at minimum a created_at timestamp with server-side default.
  * Foreign keys use explicit ondelete semantics:
      - RESTRICT  : prevents orphan-creating deletes (services → incidents/alerts)
      - SET NULL  : preserves the child row when the parent is deleted (soft ref)
      - CASCADE   : child follows parent (post_mortems follow incidents)
  * Indexes are created on every foreign key column and on high-cardinality
    filter columns (status, severity, created_at) to support the expected
    query patterns from the incident engine and dashboard.

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "0001_initial_schema"
down_revision = None          # This is the first revision — no parent.
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# upgrade()
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # services                                                             #
    # ------------------------------------------------------------------ #
    # Central registry of every microservice the system monitors.
    # ``remediation_lock`` + ``under_remediation_until`` implement the
    # cool-down mechanism that prevents tight auto-remediation loops.
    op.create_table(
        "services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("repo_url", sa.String(256), nullable=True),
        sa.Column("owner_team", sa.String(128), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default="ACTIVE",
            nullable=False,
            comment="ACTIVE | DEGRADED | CRITICAL | MAINTENANCE",
        ),
        sa.Column("under_remediation_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remediation_lock", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_services_name", "services", ["name"], unique=True)

    # ------------------------------------------------------------------ #
    # users                                                                #
    # ------------------------------------------------------------------ #
    # Operators, on-call engineers, and SREs.  ``slack_user_id`` enables
    # direct Slack notification routing without an extra lookup.
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "role",
            sa.String(32),
            server_default="DEVELOPER",
            nullable=False,
            comment="DEVELOPER | SRE | MANAGER | ADMIN",
        ),
        sa.Column("slack_user_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_slack_user_id", "users", ["slack_user_id"], unique=True)

    # ------------------------------------------------------------------ #
    # incidents                                                            #
    # ------------------------------------------------------------------ #
    # The central entity.  Every alert group, RCA result, and action taken
    # is tied to an incident.
    #
    # ``telemetry_s3_key`` holds the MinIO object key for the full telemetry
    # bundle (logs + metrics snapshot) stored at incident creation time.
    # This keeps the row small while preserving the full signal.
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "commander_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default="TRIGGERED",
            nullable=False,
            comment="TRIGGERED | ACKNOWLEDGED | MITIGATING | RESOLVED | CLOSED",
        ),
        sa.Column(
            "severity",
            sa.String(16),
            server_default="SEV-3",
            nullable=False,
            comment="SEV-1 | SEV-2 | SEV-3 | SEV-4",
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("slack_channel_id", sa.String(64), nullable=True),
        sa.Column("telemetry_s3_key", sa.String(256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    # FK indexes
    op.create_index("ix_incidents_service_id", "incidents", ["service_id"])
    op.create_index("ix_incidents_commander_id", "incidents", ["commander_id"])
    # Filter indexes — the incident engine queries heavily by status + severity
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_severity", "incidents", ["severity"])
    # Time-range queries for dashboards and SLA reports
    op.create_index("ix_incidents_created_at", "incidents", ["created_at"])

    # ------------------------------------------------------------------ #
    # alerts                                                               #
    # ------------------------------------------------------------------ #
    # Raw alert events from Prometheus / Datadog / PagerDuty / webhooks.
    # ``external_alert_id`` must be unique to enable idempotent ingestion
    # (re-delivered webhooks must not create duplicate rows).
    # ``incident_id`` is nullable — alerts arrive before an incident is created.
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("services.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source", sa.String(64), nullable=False, comment="prometheus | datadog | pagerduty | webhook"),
        sa.Column("external_alert_id", sa.String(256), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default="FIRING",
            nullable=False,
            comment="FIRING | RESOLVED | SILENCED",
        ),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_alerts_incident_id", "alerts", ["incident_id"])
    op.create_index("ix_alerts_service_id", "alerts", ["service_id"])
    # Unique index on external_alert_id enables upsert-based idempotent ingestion
    op.create_index("ix_alerts_external_alert_id", "alerts", ["external_alert_id"], unique=True)

    # ------------------------------------------------------------------ #
    # audit_logs                                                           #
    # ------------------------------------------------------------------ #
    # Append-only record of every remediation action taken by the
    # action-runner (or manually by an operator).
    #
    # ``output_hash``     : SHA-256 of the action output for integrity checking.
    # ``backup_state_yaml``: Kubernetes YAML of the resource state before the
    #                        action was taken — used for rollback.
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("operator_user", sa.String(128), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False, comment="RESTART_POD | SCALE_DEPLOYMENT | ROLLBACK | ..."),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default="PENDING",
            nullable=False,
            comment="PENDING | EXECUTED | FAILED | BLOCKED",
        ),
        sa.Column("backup_state_yaml", sa.Text(), nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("output_preview", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_logs_incident_id", "audit_logs", ["incident_id"])

    # ------------------------------------------------------------------ #
    # post_mortems                                                         #
    # ------------------------------------------------------------------ #
    # One post-mortem per incident (enforced by the unique constraint on
    # incident_id).  ``timeline_json`` and ``remediation_items`` are JSONB
    # arrays so the schema can evolve without migrations as the AI generator
    # adds new fields.
    op.create_table(
        "post_mortems",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("timeline_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("remediation_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # One post-mortem per incident
    op.create_index("ix_post_mortems_incident_id", "post_mortems", ["incident_id"], unique=True)
    op.create_index("ix_post_mortems_author_id", "post_mortems", ["author_id"])


# ---------------------------------------------------------------------------
# downgrade()
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop in reverse dependency order to satisfy foreign key constraints.
    op.drop_table("post_mortems")
    op.drop_table("audit_logs")
    op.drop_table("alerts")
    op.drop_table("incidents")
    op.drop_table("users")
    op.drop_table("services")
