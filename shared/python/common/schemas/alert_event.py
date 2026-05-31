from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AlertEvent(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    service_name: str
    severity: str
    summary: str
    status: str
    raw_payload: dict[str, Any]
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
