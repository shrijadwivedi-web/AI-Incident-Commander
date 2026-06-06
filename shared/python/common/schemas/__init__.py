"""Public API for the common.schemas package.

Import event contracts from here — never import directly from submodules.
This insulates consumers from internal file renames.

Available schemas
-----------------
  AlertEvent      — normalised alert from any ingestion source
  IncidentEvent   — incident lifecycle state-change event
  EventEnvelope   — base envelope (event_id, schema_version, produced_at, …)
  LogEntry        — a single log line (used inside LogEvent)
  LogEvent        — enriched log event (retained for backward compatibility)
  LogIngestRequest— HTTP ingest request body (retained for backward compatibility)

Available enums
---------------
  Severity, AlertStatus, IncidentStatus, EventSource
"""

from common.schemas.alert_event import AlertEvent
from common.schemas.enums import AlertStatus, EventSource, IncidentStatus, Severity
from common.schemas.event_envelope import EventEnvelope
from common.schemas.incident_event import IncidentEvent
from common.schemas.log_event import LogEntry, LogEvent, LogIngestRequest

__all__ = [
    # Event contracts
    "AlertEvent",
    "IncidentEvent",
    "EventEnvelope",
    # Log schemas (backward compat)
    "LogEntry",
    "LogEvent",
    "LogIngestRequest",
    # Enums
    "Severity",
    "AlertStatus",
    "IncidentStatus",
    "EventSource",
]
