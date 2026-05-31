from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from common.schemas.alert_event import AlertEvent


def normalize(payload: dict[str, Any]) -> list[AlertEvent]:
    alerts = payload.get("alerts", [payload])
    events: list[AlertEvent] = []

    for alert in alerts:
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        service_name = labels.get("service") or labels.get("job") or "unknown-service"
        summary = annotations.get("summary") or annotations.get("description") or alert.get("status", "alert")
        severity = labels.get("severity") or payload.get("groupLabels", {}).get("severity", "unknown")

        events.append(
            AlertEvent(
                alert_id=str(uuid4()),
                source="prometheus",
                service_name=service_name,
                severity=str(severity).upper(),
                summary=summary,
                status=alert.get("status", payload.get("status", "firing")),
                raw_payload=alert,
                occurred_at=datetime.now(timezone.utc),
            )
        )

    return events
