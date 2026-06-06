"""Domain enumerations for Kafka event contracts.

All enums inherit from ``str`` so that:
  * Values serialize to plain JSON strings (no extra serialisation step).
  * Pydantic v2 validates them as string literals at runtime.
  * They can be compared directly to string literals without `.value`.

Design note — these enums are the *single source of truth* for status
vocabularies across producers and consumers.  Never hard-code these
strings in application code; import from here.
"""

from __future__ import annotations

from enum import unique
from typing import ClassVar

# Python 3.11+ ships StrEnum in stdlib; for 3.10 compatibility we derive
# from both str and Enum.
import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Backport of stdlib StrEnum for Python < 3.11."""


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

@unique
class Severity(StrEnum):
    """Unified severity scale used across alerts and incidents.

    Mapping to common tooling:
      SEV_1  ↔  PagerDuty P1 / Prometheus critical
      SEV_2  ↔  PagerDuty P2 / Prometheus critical
      SEV_3  ↔  PagerDuty P3 / Prometheus warning
      SEV_4  ↔  PagerDuty P4 / Prometheus info
    """

    SEV_1 = "SEV-1"  # Total outage — customer-facing revenue impact
    SEV_2 = "SEV-2"  # Significant degradation — partial user impact
    SEV_3 = "SEV-3"  # Minor degradation — limited user impact
    SEV_4 = "SEV-4"  # Informational — no user impact yet

    # Convenience class-var so callers can do Severity.CRITICAL_LEVELS
    CRITICAL_LEVELS: ClassVar[frozenset[str]] = frozenset({"SEV-1", "SEV-2"})


# ---------------------------------------------------------------------------
# Alert status
# ---------------------------------------------------------------------------

@unique
class AlertStatus(StrEnum):
    """Lifecycle states of a raw alert payload."""

    FIRING = "FIRING"        # Alert is currently active
    RESOLVED = "RESOLVED"   # Alert has been resolved at source
    SILENCED = "SILENCED"   # Alert is suppressed by a silence rule


# ---------------------------------------------------------------------------
# Incident status
# ---------------------------------------------------------------------------

@unique
class IncidentStatus(StrEnum):
    """Lifecycle states of an incident.

    State machine:
        TRIGGERED → ACKNOWLEDGED → MITIGATING → RESOLVED → CLOSED
                                              ↘ RESOLVED (skip mitigating)
    """

    TRIGGERED = "TRIGGERED"         # Created, no human acknowledgement yet
    ACKNOWLEDGED = "ACKNOWLEDGED"   # On-call engineer has acknowledged
    MITIGATING = "MITIGATING"       # Active remediation in progress
    RESOLVED = "RESOLVED"           # Service restored; monitoring period
    CLOSED = "CLOSED"               # Post-mortem complete, ticket closed


# ---------------------------------------------------------------------------
# Event source (alert origin system)
# ---------------------------------------------------------------------------

@unique
class EventSource(StrEnum):
    """Identifies the system that produced the alert event.

    This value drives webhook parsing in the ingestion layer — each source
    has a dedicated normaliser that maps its payload shape to ``AlertEvent``.
    """

    PROMETHEUS = "prometheus"
    DATADOG = "datadog"
    PAGERDUTY = "pagerduty"
    GRAFANA = "grafana"
    WEBHOOK = "webhook"       # Generic / unknown external webhook
    INTERNAL = "internal"     # Events produced by AIC itself (e.g. watchdog)
