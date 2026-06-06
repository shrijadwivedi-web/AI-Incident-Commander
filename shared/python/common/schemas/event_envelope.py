"""Shared event envelope metadata.

Every Kafka event in AIC wraps its domain payload inside a standard
envelope that carries:

  * **Versioning**  — ``schema_version`` allows consumers to branch on
    payload shape without redeploying.  We use a monotonic integer
    (not SemVer) because Kafka has no schema registry in this stack;
    the integer is cheap to compare and trivially sortable.

  * **Tracing**     — ``event_id`` and ``correlation_id`` provide end-to-end
    observability from the incoming webhook through to the incident row.

  * **Routing**     — ``schema_version`` + ``event_type`` let a single
    consumer fan-out to the right handler without deserialising the full
    payload.

  * **Replay safety** — ``produced_at`` records the wall-clock time the
    event was *created*, not when it was consumed, so replayed events
    don't corrupt time-series views.

Keying strategy (documented here; enforced at producer call site)
-----------------------------------------------------------------
  AlertEvent   → key = ``service_name``
  IncidentEvent → key = ``service_name``

Using ``service_name`` as the Kafka partition key guarantees that all
events for a given service land on the same partition, preserving
per-service ordering without requiring a global total order.

Serialisation format
--------------------
  JSON encoded as UTF-8.  ``model_dump(mode="json")`` on any Pydantic v2
  model produces a JSON-compatible dict (UUIDs → str, datetimes → ISO 8601
  with timezone).  No Avro / Protobuf in Sprint 1; the schema_version field
  gives us a migration path if we add a schema registry later.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """Standard metadata wrapper for every AIC Kafka event.

    Fields
    ------
    event_id:
        UUID v4 assigned at event creation.  Consumers must use this as
        the idempotency key — re-delivered events with the same ``event_id``
        must be deduplicated.

    schema_version:
        Monotonic integer.  Consumers check this before deserialising the
        payload.  Increment when adding required fields or changing types.
        Adding optional fields is backward-compatible and does NOT require
        a version bump.

    event_type:
        Literal discriminator used for fan-out routing (e.g.
        ``"alert.v1"`` or ``"incident.v1"``).  Format: ``<domain>.<version>``.

    produced_at:
        UTC timestamp of when the event object was created.  Always
        timezone-aware.  Never mutated after creation.

    correlation_id:
        Optional trace ID inherited from the upstream HTTP request
        (X-Correlation-ID header).  Propagated through the pipeline so
        every Kafka message, DB row, and log line share the same ID.
    """

    event_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Globally unique event identifier (idempotency key).",
    )
    schema_version: int = Field(
        default=1,
        ge=1,
        description="Monotonic schema version. Increment on breaking changes.",
    )
    event_type: str = Field(
        description="Dot-separated event type discriminator, e.g. 'alert.v1'.",
    )
    produced_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC wall-clock time the event was produced.",
    )
    correlation_id: uuid.UUID | None = Field(
        default=None,
        description="Upstream trace/request ID for end-to-end observability.",
    )

    model_config = {
        # Validate on assignment so mutations are caught immediately.
        "validate_assignment": True,
        # Serialize UUIDs as strings, datetimes as ISO 8601.
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
            uuid.UUID: str,
        },
    }
