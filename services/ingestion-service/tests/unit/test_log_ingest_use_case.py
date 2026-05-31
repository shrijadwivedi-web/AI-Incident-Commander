from datetime import datetime, timezone
from unittest.mock import Mock

from common.schemas.log_event import LogEntry, LogIngestRequest
from ingestion_service.application.use_cases.ingest_logs import IngestLogsUseCase


def test_ingest_logs_publishes_masked_events() -> None:
    publisher = Mock()
    use_case = IngestLogsUseCase(publisher)
    request = LogIngestRequest(
        service_name="payment-gateway",
        incident_id="inc-123",
        logs=[
            LogEntry(
                timestamp=datetime.now(timezone.utc),
                level="error",
                message="contact user@example.com",
                metadata={"pod": "pay-1"},
            )
        ],
    )

    log_ids = use_case.execute(request)

    assert len(log_ids) == 1
    publisher.publish_log.assert_called_once()
    publisher.flush.assert_called_once()
    event = publisher.publish_log.call_args.args[0]
    assert "user@example.com" not in event.masked_message
