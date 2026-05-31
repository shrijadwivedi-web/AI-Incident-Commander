from common.schemas.log_event import LogEvent, LogIngestRequest
from common.sanitization.pii_masker import mask_pii

from ingestion_service.application.ports.event_publisher import EventPublisher


class IngestLogsUseCase:
    def __init__(self, publisher: EventPublisher) -> None:
        self._publisher = publisher

    def execute(self, request: LogIngestRequest) -> list[str]:
        log_ids: list[str] = []
        partition_key = request.incident_id or request.service_name

        for entry in request.logs:
            masked_message = mask_pii(entry.message)
            event = LogEvent(
                service_name=request.service_name,
                incident_id=request.incident_id,
                timestamp=entry.timestamp,
                level=entry.level.upper(),
                message=entry.message,
                masked_message=masked_message,
                metadata=entry.metadata,
            )
            self._publisher.publish_log(event, partition_key=partition_key)
            log_ids.append(event.log_id)

        self._publisher.flush()
        return log_ids
