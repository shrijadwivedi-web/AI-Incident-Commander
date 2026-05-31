from typing import Any

from common.schemas.alert_event import AlertEvent

from ingestion_service.application.ports.event_publisher import EventPublisher
from ingestion_service.infrastructure.normalizers import NORMALIZERS


class IngestAlertUseCase:
    def __init__(self, publisher: EventPublisher) -> None:
        self._publisher = publisher

    def execute(self, source: str, payload: dict[str, Any]) -> list[str]:
        normalizer = NORMALIZERS.get(source)
        if normalizer is None:
            raise ValueError(f"Unsupported alert source: {source}")

        events: list[AlertEvent] = normalizer(payload)
        alert_ids: list[str] = []

        for event in events:
            self._publisher.publish_alert(event)
            alert_ids.append(event.alert_id)

        self._publisher.flush()
        return alert_ids
