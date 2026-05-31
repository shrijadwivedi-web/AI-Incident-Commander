from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LogIngestRequest(BaseModel):
    service_name: str
    incident_id: str | None = None
    logs: list[LogEntry]


class LogEvent(BaseModel):
    log_id: str = Field(default_factory=lambda: str(uuid4()))
    service_name: str
    incident_id: str | None = None
    timestamp: datetime
    level: str
    message: str
    masked_message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
