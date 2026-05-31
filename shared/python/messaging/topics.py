from dataclasses import dataclass


@dataclass(frozen=True)
class KafkaTopics:
    alerts: str
    logs: str
