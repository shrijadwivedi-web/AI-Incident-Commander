from datetime import datetime, timezone
from typing import Any

from common.schemas.alert_event import AlertEvent


def normalize(payload: dict[str, Any]) -> list[AlertEvent]:
    title = payload.get("title") or payload.get("event_title") or "Datadog alert"
    service_name = payload.get("service_name") or payload.get("host") or "unknown-service"
    severity = payload.get("alert_priority") or payload.get("severity") or "unknown"

    return [
        AlertEvent(
            source="datadog",
            service_name=service_name,
            severity=str(severity).upper(),
            summary=title,
            status=payload.get("status", "firing"),
            raw_payload=payload,
            occurred_at=datetime.now(timezone.utc),
        )
    ]
