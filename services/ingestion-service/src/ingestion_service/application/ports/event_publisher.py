from typing import Protocol

from common.schemas.alert_event import AlertEvent
from common.schemas.log_event import LogEvent


class EventPublisher(Protocol):
    def publish_alert(self, event: AlertEvent) -> None: ...

    def publish_log(self, event: LogEvent, *, partition_key: str) -> None: ...

    def flush(self) -> None: ...
