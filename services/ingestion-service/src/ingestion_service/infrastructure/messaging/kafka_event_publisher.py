from common.schemas.alert_event import AlertEvent
from common.schemas.log_event import LogEvent
from messaging.kafka_producer import KafkaEventPublisher

from ingestion_service.application.ports.event_publisher import EventPublisher


class KafkaAdapter(EventPublisher):
    def __init__(self, producer: KafkaEventPublisher) -> None:
        self._producer = producer

    def publish_alert(self, event: AlertEvent) -> None:
        self._producer.publish_alert(event, partition_key=event.service_name)

    def publish_log(self, event: LogEvent, *, partition_key: str) -> None:
        self._producer.publish_log(event, partition_key=partition_key)

    def flush(self) -> None:
        self._producer.flush()
