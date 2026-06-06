"""AlertEvent — Kafka event contract for incoming alert payloads.

Schema version: 1
Topic: aic.alerts.v1
Partition key: service_name

This module defines the canonical shape of an alert as it flows through
the Kafka pipeline.  Every alert source (Prometheus, Datadog, PagerDuty,
generic webhooks) MUST be normalised into this schema by the ingestion
layer before being published.

Design decisions
----------------
* ``correlation_key`` is the de-duplication and grouping handle.  The
  ingestion layer computes it as:
      sha256(service_name + ":" + alert_fingerprint)
  This allows the Incident Engine to:
    1. Detect duplicate firings of the same alert within a time window.
    2. Group related alerts into a single incident without a Kafka stream join.

* ``metadata`` is an open-ended JSONB dict for source-specific fields that
  don't belong in the core schema (e.g. Prometheus labels, Datadog tags).
  Consumers MUST treat it as optional and schema-less.

* ``occurred_at`` is the timestamp reported by the *source system*, not the
  ingestion timestamp.  This preserves the true event timeline even when
  events are batched or delayed.

* ``external_alert_id`` is the source system's own identifier.  It maps
  directly to ``alerts.external_alert_id`` in PostgreSQL and is used as the
  idempotency key when persisting alerts.

Versioning
----------
  This schema is schema_version=1.  If a breaking field change is needed:
    1. Bump schema_version to 2.
    2. Create AlertEventV2 in a new file.
    3. Update the producer to publish V2 events.
    4. Update consumers to handle both V1 and V2 during the rollover window.
    5. Remove V1 handling after all consumers are on V2.

Example payload (JSON)
-----------------------
See ``AlertEvent.example()`` class method below.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from common.schemas.enums import AlertStatus, EventSource, Severity
from common.schemas.event_envelope import EventEnvelope

# ---------------------------------------------------------------------------
# AlertEvent
# ---------------------------------------------------------------------------

_CURRENT_SCHEMA_VERSION: int = 1
_EVENT_TYPE: str = "alert.v1"


class AlertEvent(EventEnvelope):
    """Normalised alert event published to ``aic.alerts.v1``.

    Inherits the standard envelope fields:
      event_id, schema_version, event_type, produced_at, correlation_id.

    Kafka keying strategy
    ---------------------
      key = service_name (UTF-8 encoded)

      This routes all alerts for a given service to the same partition,
      preserving per-service ordering for the Incident Engine.

    Fields
    ------
    event_id:
        Inherited from EventEnvelope.  This is the idempotency key — the
        ingestion layer must set this to a deterministic UUID derived from
        ``external_alert_id`` so that duplicate webhook deliveries produce
        the same event_id and can be deduplicated downstream.

    source:
        The system that generated the alert.  Used by the ingestion layer
        to select the correct payload normaliser.

    service_name:
        The canonical name of the monitored service.  Must match a row in
        the ``services`` table.  Used as the Kafka partition key.

    severity:
        Normalised severity.  Source-specific severity strings (e.g.
        Prometheus ``critical``, Datadog ``high``) are mapped to this enum
        during ingestion.

    title:
        Short, human-readable alert title.  Max 256 chars.

    description:
        Full alert description or runbook excerpt.  May contain markdown.

    occurred_at:
        Timestamp from the *source system* (not ingestion time).  Must be
        timezone-aware.  If the source doesn't provide a timestamp, the
        ingestion layer uses the webhook receipt time.

    correlation_key:
        Deterministic grouping key computed as:
            sha256(service_name + ":" + external_alert_id)[:16]
        The Incident Engine uses this to correlate related alerts into a
        single incident without a Kafka stream join.

    external_alert_id:
        The source system's own identifier (e.g. Prometheus fingerprint,
        PagerDuty incident key).  Used for idempotent PostgreSQL upserts.

    alert_status:
        Current state of the alert at the source system.

    metadata:
        Free-form dict for source-specific fields that don't fit the core
        schema.  Consumers must treat this as optional and schema-less.
        Examples: Prometheus labels, Datadog tags, runbook URLs.
    """

    # Override envelope defaults for this event type
    schema_version: int = Field(default=_CURRENT_SCHEMA_VERSION, ge=1)
    event_type: Literal["alert.v1"] = Field(default=_EVENT_TYPE)

    # Core alert fields
    source: EventSource = Field(
        description="Origin system that produced this alert.",
    )
    service_name: str = Field(
        min_length=1,
        max_length=128,
        description="Canonical service name. Used as the Kafka partition key.",
    )
    severity: Severity = Field(
        description="Normalised severity level.",
    )
    title: str = Field(
        min_length=1,
        max_length=256,
        description="Short human-readable alert title.",
    )
    description: str = Field(
        default="",
        description="Full alert description. May contain markdown.",
    )
    occurred_at: datetime = Field(
        description="Event timestamp from the source system (timezone-aware).",
    )
    correlation_key: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "Deterministic grouping key: sha256(service_name:external_alert_id)[:16]. "
            "Used by the Incident Engine to correlate related alerts."
        ),
    )
    external_alert_id: str = Field(
        min_length=1,
        max_length=256,
        description="Source system's own alert identifier. Idempotency key for DB upserts.",
    )
    alert_status: AlertStatus = Field(
        default=AlertStatus.FIRING,
        description="Current state of the alert at the source system.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific extra fields. Consumers must treat as optional.",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("occurred_at", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, v: Any) -> datetime:
        """Reject naive datetimes — all timestamps must be timezone-aware."""
        if isinstance(v, datetime) and v.tzinfo is None:
            raise ValueError(
                "occurred_at must be timezone-aware. "
                "Use datetime.now(timezone.utc) or pass an ISO 8601 string with offset."
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
    def validate_correlation_key_format(self) -> AlertEvent:
        """Verify that correlation_key is a hex string (sanity check)."""
        try:
            int(self.correlation_key, 16)
        except ValueError:
            raise ValueError(
                f"correlation_key must be a hex string. Got: {self.correlation_key!r}"
            )
        return self

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def compute_correlation_key(
        cls,
        service_name: str,
        external_alert_id: str,
        length: int = 16,
    ) -> str:
        """Compute a deterministic correlation key.

        Args:
            service_name: Canonical service name (will be lowercased).
            external_alert_id: Source system's alert identifier.
            length: Hex character length of the output (default 16 = 64 bits).

        Returns:
            Lowercase hex string of ``length`` characters.
        """
        raw = f"{service_name.lower()}:{external_alert_id}"
        return hashlib.sha256(raw.encode()).hexdigest()[:length]

    @classmethod
    def compute_event_id(cls, external_alert_id: str) -> uuid.UUID:
        """Derive a deterministic UUID from the external alert ID.

        Using UUID v5 (SHA-1 namespace) so that duplicate webhook deliveries
        of the same alert always produce the same event_id, enabling
        idempotent processing downstream.
        """
        return uuid.uuid5(uuid.NAMESPACE_URL, f"aic:alert:{external_alert_id}")

    # ------------------------------------------------------------------
    # Example payload
    # ------------------------------------------------------------------

    @classmethod
    def example(cls) -> "AlertEvent":
        """Return a realistic example AlertEvent instance for documentation."""
        external_id = "prometheus-alertmanager-1234abcd"
        svc = "payment-service"
        return cls(
            event_id=cls.compute_event_id(external_id),
            source=EventSource.PROMETHEUS,
            service_name=svc,
            severity=Severity.SEV_2,
            title="HighErrorRate: payment-service error rate >5% for 5m",
            description=(
                "The 5-minute error rate for `payment-service` has exceeded 5%.\n\n"
                "**Runbook**: https://wiki.internal/runbooks/payment-high-error-rate\n"
                "**Dashboard**: https://grafana.internal/d/payment-service"
            ),
            occurred_at=datetime(2026, 6, 7, 4, 0, 0, tzinfo=timezone.utc),
            correlation_key=cls.compute_correlation_key(svc, external_id),
            external_alert_id=external_id,
            alert_status=AlertStatus.FIRING,
            metadata={
                "labels": {
                    "alertname": "HighErrorRate",
                    "env": "production",
                    "namespace": "payments",
                    "pod": "payment-service-7d9f8c-xk2pq",
                },
                "annotations": {
                    "summary": "High error rate on payment-service",
                    "description": "Error rate is 7.3% over the last 5 minutes.",
                },
                "generator_url": "https://prometheus.internal/graph?...",
            },
        )
