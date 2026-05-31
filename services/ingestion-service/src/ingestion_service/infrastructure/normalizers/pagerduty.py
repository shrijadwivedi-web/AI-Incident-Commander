from datetime import datetime, timezone
from typing import Any

from common.schemas.alert_event import AlertEvent


def normalize(payload: dict[str, Any]) -> list[AlertEvent]:
    service_name = payload.get("service_name") or payload.get("service", {}).get("name", "unknown-service")
    details = payload.get("details", {})
    summary = details.get("summary") or payload.get("summary") or "PagerDuty incident"
    severity = details.get("severity") or payload.get("severity", "unknown")
    status = "firing" if payload.get("event", "").endswith("triggered") else payload.get("event", "firing")

    return [
        AlertEvent(
            source="pagerduty",
            service_name=service_name,
            severity=str(severity).upper(),
            summary=summary,
            status=status,
            raw_payload=payload,
            occurred_at=datetime.now(timezone.utc),
        )
    ]
