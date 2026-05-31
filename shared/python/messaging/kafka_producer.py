import json
from typing import Any

from confluent_kafka import Producer
from pydantic import BaseModel

from config.settings import Settings
from messaging.topics import KafkaTopics


class KafkaEventPublisher:
    def __init__(self, settings: Settings, topics: KafkaTopics) -> None:
        self._topics = topics
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": settings.kafka_client_id,
                "acks": "all",
                "enable.idempotence": True,
            }
        )

    def publish_alert(self, event: BaseModel, partition_key: str) -> None:
        self._publish(self._topics.alerts, partition_key, event)

    def publish_log(self, event: BaseModel, partition_key: str) -> None:
        self._publish(self._topics.logs, partition_key, event)

    def flush(self) -> None:
        self._producer.flush(10)

    def _publish(self, topic: str, key: str, event: BaseModel) -> None:
        payload: dict[str, Any] = event.model_dump(mode="json")
        self._producer.produce(
            topic=topic,
            key=key.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8"),
            on_delivery=self._delivery_report,
        )
        self._producer.poll(0)

    @staticmethod
    def _delivery_report(err, msg) -> None:
        if err is not None:
            raise RuntimeError(f"Kafka delivery failed: {err}")
