"""Kafka topic registry for AI Incident Commander.

All topic names are defined here as module-level constants so that
producers and consumers never hard-code strings.

Topic naming convention
-----------------------
  aic.<domain>.<version>

  * ``aic``     — namespace prefix (all topics belong to this system)
  * ``<domain>``— the logical entity being communicated (alerts, incidents, …)
  * ``<version>``— schema version (v1, v2, …); bump when the schema version
                   in the corresponding Pydantic event model increments.

Partition count guidance (for reference; set in infra/kafka/topics.yml)
-----------------------------------------------------------------------
  aic.alerts.v1     : 12 partitions — high-throughput ingest (1M events/day)
  aic.incidents.v1  :  6 partitions — lower volume, must preserve per-service order
  aic.telemetry.v1  : 12 partitions — unified enriched topic (logs + metrics)

  All topics use:
    replication-factor = 3 (production)
    retention.ms       = 604800000 (7 days)
    cleanup.policy     = delete

Keying strategy (summarised; full detail in event schema docstrings)
--------------------------------------------------------------------
  aic.alerts.v1     → key = service_name
  aic.incidents.v1  → key = service_name
  aic.telemetry.v1  → key = service_name

  Using service_name as the partition key across all topics ensures
  that events for the same service land on the same partition,
  preserving per-service ordering without a global total order.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Topic name constants
# ---------------------------------------------------------------------------

#: Raw, normalised alert events from all ingestion sources.
#: Schema: AlertEvent (common.schemas.alert_event)
TOPIC_ALERTS_V1: str = "aic.alerts.v1"

#: Incident lifecycle state-change events.
#: Schema: IncidentEvent (common.schemas.incident_event)
TOPIC_INCIDENTS_V1: str = "aic.incidents.v1"

#: Unified telemetry stream: enriched logs + metrics snapshots.
#: This replaces the previous separate logs/metrics topics and
#: eliminates the need for a Kafka Streams join.
#: Schema: TelemetryEvent (common.schemas.telemetry_event — Sprint 2)
TOPIC_TELEMETRY_V1: str = "aic.telemetry.v1"


# ---------------------------------------------------------------------------
# Convenience registry (for settings injection and testing)
# ---------------------------------------------------------------------------

class KafkaTopics:
    """Immutable registry of all Kafka topic names.

    Pass an instance of this class to any service that needs to publish or
    consume Kafka events.  This indirection allows integration tests to swap
    topic names without env-var manipulation.

    Attributes
    ----------
    alerts:
        Topic for raw normalised alert events (AlertEvent).
    incidents:
        Topic for incident lifecycle state-change events (IncidentEvent).
    telemetry:
        Topic for unified enriched telemetry stream (TelemetryEvent).

    Example
    -------
    >>> topics = KafkaTopics()
    >>> topics.alerts
    'aic.alerts.v1'
    """

    __slots__ = ("alerts", "incidents", "telemetry")

    def __init__(
        self,
        alerts: str = TOPIC_ALERTS_V1,
        incidents: str = TOPIC_INCIDENTS_V1,
        telemetry: str = TOPIC_TELEMETRY_V1,
    ) -> None:
        object.__setattr__(self, "alerts", alerts)
        object.__setattr__(self, "incidents", incidents)
        object.__setattr__(self, "telemetry", telemetry)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("KafkaTopics is immutable.")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"KafkaTopics("
            f"alerts={self.alerts!r}, "
            f"incidents={self.incidents!r}, "
            f"telemetry={self.telemetry!r})"
        )
