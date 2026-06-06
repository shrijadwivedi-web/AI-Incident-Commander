"""IncidentEvent — Kafka event contract for incident lifecycle changes.

Schema version: 1
Topic: aic.incidents.v1
Partition key: service_name

This module defines the canonical shape of an incident state-change event
published by the Incident Engine.  Every transition in an incident's
lifecycle (creation, acknowledgement, resolution, closure) produces one
IncidentEvent on this topic.

Design decisions
----------------
* ``triggering_alert_id`` links back to the ``AlertEvent.event_id`` that
  caused the incident to be created.  This provides a full causal chain:
      webhook → AlertEvent → IncidentEvent → AuditLog / PostMortem

* ``status`` uses the same ``IncidentStatus`` enum as the PostgreSQL
  ``incidents.status`` column.  A consumer can use this value directly to
  update the DB row without re-mapping.

* ``updated_at`` is always present so consumers can build time-series
  views of incident state transitions without querying PostgreSQL.

* ``metadata`` follows the same open-dict pattern as AlertEvent — it carries
  contextual enrichment (Slack channel ID, commander info, RCA summary)
  without polluting the core schema.

Kafka keying strategy
---------------------
  key = service_name (UTF-8 encoded)

  This co-partitions IncidentEvents with AlertEvents for the same service,
  so a consumer reading both topics can join by partition without a shuffle.

Versioning
----------
  Same strategy as AlertEvent.  schema_version=1 is the initial contract.
  See alert_event.py for the full versioning policy.

Example payload (JSON)
-----------------------
See ``IncidentEvent.example()`` class method below.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from common.schemas.enums import IncidentStatus, Severity
from common.schemas.event_envelope import EventEnvelope

# ---------------------------------------------------------------------------
# IncidentEvent
# ---------------------------------------------------------------------------

_CURRENT_SCHEMA_VERSION: int = 1
_EVENT_TYPE: str = "incident.v1"


class IncidentEvent(EventEnvelope):
    """Incident lifecycle event published to ``aic.incidents.v1``.

    One event is emitted per status transition.  Consumers use the
    ``status`` field to drive their own state machines.

    Inherits the standard envelope fields:
      event_id, schema_version, event_type, produced_at, correlation_id.

    Fields
    ------
    incident_id:
        UUID of the incident row in PostgreSQL.  Consumers use this to
        fetch or update the full incident record.

    service_name:
        Canonical service name.  Used as the Kafka partition key.
        Co-partitioned with AlertEvent for the same service.

    severity:
        Severity at the time of this event.  May be upgraded (SEV-3 → SEV-1)
        as more information becomes available.

    status:
        The *new* status after this transition.  Consumers that maintain
        their own incident state machine should treat this as the authoritative
        current state.

    previous_status:
        The status *before* this transition.  Allows consumers to detect
        valid and invalid transitions without querying the DB.  None for
        the initial TRIGGERED event.

    created_at:
        Timestamp when the incident was first created.  Constant across all
        events for the same incident_id.

    updated_at:
        Timestamp of this specific state transition.  Always increases
        monotonically for the same incident_id.

    triggering_alert_id:
        The ``event_id`` of the ``AlertEvent`` that caused this incident to
        be opened.  None for incidents created by other means (e.g. manually
        by an operator).

    commander_id:
        UUID of the ``User`` assigned as incident commander.  None until
        acknowledged.

    slack_channel_id:
        Slack channel created for this incident.  Propagated so notification
        consumers don't need to query PostgreSQL.

    metadata:
        Free-form dict for contextual enrichment.
        Examples:
          - ``rca_summary``: AI-generated root cause (added when available)
          - ``action_taken``: Summary of automated remediation steps
          - ``telemetry_s3_key``: MinIO object key for the telemetry snapshot
    """

    # Override envelope defaults for this event type
    schema_version: int = Field(default=_CURRENT_SCHEMA_VERSION, ge=1)
    event_type: Literal["incident.v1"] = Field(default=_EVENT_TYPE)

    # Core incident fields
    incident_id: uuid.UUID = Field(
        description="UUID of the PostgreSQL incidents row.",
    )
    service_name: str = Field(
        min_length=1,
        max_length=128,
        description="Canonical service name. Used as the Kafka partition key.",
    )
    severity: Severity = Field(
        description="Severity level at the time of this event.",
    )
    status: IncidentStatus = Field(
        description="New lifecycle status after this transition.",
    )
    previous_status: IncidentStatus | None = Field(
        default=None,
        description="Status before this transition. None for TRIGGERED events.",
    )
    created_at: datetime = Field(
        description="When the incident was first created (constant per incident).",
    )
    updated_at: datetime = Field(
        description="When this state transition occurred.",
    )
    triggering_alert_id: uuid.UUID | None = Field(
        default=None,
        description="event_id of the AlertEvent that opened this incident.",
    )
    commander_id: uuid.UUID | None = Field(
        default=None,
        description="UUID of the assigned incident commander. None until acknowledged.",
    )
    slack_channel_id: str | None = Field(
        default=None,
        max_length=64,
        description="Slack channel ID created for this incident.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Contextual enrichment: rca_summary, action_taken, "
            "telemetry_s3_key, etc. Consumers treat as optional."
        ),
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, v: Any) -> datetime:
        """Reject naive datetimes — all timestamps must be timezone-aware."""
        if isinstance(v, datetime) and v.tzinfo is None:
            raise ValueError(
                "Timestamps must be timezone-aware. "
                "Use datetime.now(timezone.utc) or an ISO 8601 string with offset."
            )
        return v

    @field_validator("service_name", mode="before")
    @classmethod
    def normalise_service_name(cls, v: Any) -> str:
        """Strip whitespace and lowercase so names are consistent."""
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @model_validator(mode="after")
    def validate_timestamp_ordering(self) -> "IncidentEvent":
        """updated_at must be >= created_at."""
        if self.updated_at < self.created_at:
            raise ValueError(
                f"updated_at ({self.updated_at.isoformat()}) must not be "
                f"before created_at ({self.created_at.isoformat()})."
            )
        return self

    @model_validator(mode="after")
    def validate_triggered_has_no_previous_status(self) -> "IncidentEvent":
        """TRIGGERED events must not carry a previous_status."""
        if self.status == IncidentStatus.TRIGGERED and self.previous_status is not None:
            raise ValueError(
                "TRIGGERED events represent incident creation and must have "
                "previous_status=None."
            )
        return self

    @model_validator(mode="after")
    def validate_non_triggered_has_previous_status(self) -> "IncidentEvent":
        """All non-TRIGGERED transitions must carry a previous_status."""
        if (
            self.status != IncidentStatus.TRIGGERED
            and self.previous_status is None
        ):
            raise ValueError(
                f"Status transition to {self.status!r} must include "
                "previous_status to enable consumer-side state machine validation."
            )
        return self

    # ------------------------------------------------------------------
    # Example payload
    # ------------------------------------------------------------------

    @classmethod
    def example_triggered(cls) -> "IncidentEvent":
        """Return an example TRIGGERED (incident creation) event."""
        now = datetime(2026, 6, 7, 4, 0, 0, tzinfo=timezone.utc)
        incident_id = uuid.UUID("a1b2c3d4-0000-4000-8000-000000000001")
        alert_event_id = uuid.UUID("f1e2d3c4-0000-4000-8000-000000000001")
        return cls(
            incident_id=incident_id,
            service_name="payment-service",
            severity=Severity.SEV_2,
            status=IncidentStatus.TRIGGERED,
            previous_status=None,
            created_at=now,
            updated_at=now,
            triggering_alert_id=alert_event_id,
            commander_id=None,
            slack_channel_id=None,
            correlation_id=uuid.UUID("cccccccc-0000-4000-8000-000000000001"),
            metadata={
                "telemetry_s3_key": "incidents/a1b2c3d4/telemetry-snapshot.json.gz",
                "alert_title": "HighErrorRate: payment-service error rate >5% for 5m",
            },
        )

    @classmethod
    def example_acknowledged(cls) -> "IncidentEvent":
        """Return an example ACKNOWLEDGED (on-call pickup) event."""
        created = datetime(2026, 6, 7, 4, 0, 0, tzinfo=timezone.utc)
        acknowledged = datetime(2026, 6, 7, 4, 3, 22, tzinfo=timezone.utc)
        return cls(
            incident_id=uuid.UUID("a1b2c3d4-0000-4000-8000-000000000001"),
            service_name="payment-service",
            severity=Severity.SEV_2,
            status=IncidentStatus.ACKNOWLEDGED,
            previous_status=IncidentStatus.TRIGGERED,
            created_at=created,
            updated_at=acknowledged,
            triggering_alert_id=uuid.UUID("f1e2d3c4-0000-4000-8000-000000000001"),
            commander_id=uuid.UUID("bbbbbbbb-0000-4000-8000-000000000001"),
            slack_channel_id="C08ABCXYZ12",
            metadata={
                "telemetry_s3_key": "incidents/a1b2c3d4/telemetry-snapshot.json.gz",
                "commander_name": "Jane Doe",
                "time_to_acknowledge_seconds": 202,
            },
        )

    @classmethod
    def example_resolved(cls) -> "IncidentEvent":
        """Return an example RESOLVED event."""
        created = datetime(2026, 6, 7, 4, 0, 0, tzinfo=timezone.utc)
        resolved = datetime(2026, 6, 7, 4, 47, 10, tzinfo=timezone.utc)
        return cls(
            incident_id=uuid.UUID("a1b2c3d4-0000-4000-8000-000000000001"),
            service_name="payment-service",
            severity=Severity.SEV_2,
            status=IncidentStatus.RESOLVED,
            previous_status=IncidentStatus.MITIGATING,
            created_at=created,
            updated_at=resolved,
            triggering_alert_id=uuid.UUID("f1e2d3c4-0000-4000-8000-000000000001"),
            commander_id=uuid.UUID("bbbbbbbb-0000-4000-8000-000000000001"),
            slack_channel_id="C08ABCXYZ12",
            metadata={
                "rca_summary": (
                    "Root cause: misconfigured rate limiter deployed at 03:45 UTC. "
                    "Fix: rolled back to previous config version."
                ),
                "action_taken": "ROLLBACK_DEPLOYMENT via action-runner",
                "telemetry_s3_key": "incidents/a1b2c3d4/telemetry-snapshot.json.gz",
                "time_to_resolve_seconds": 2830,
            },
        )
