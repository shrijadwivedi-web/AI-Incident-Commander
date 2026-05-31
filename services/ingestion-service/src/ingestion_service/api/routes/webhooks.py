from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ingestion_service.api.dependencies import get_publisher
from ingestion_service.application.use_cases.ingest_alert import IngestAlertUseCase
from ingestion_service.infrastructure.messaging.kafka_event_publisher import KafkaAdapter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SUPPORTED_SOURCES = {"prometheus", "datadog", "pagerduty"}


@router.post("/{source}", status_code=status.HTTP_202_ACCEPTED)
async def ingest_webhook(
    source: str,
    request: Request,
    publisher=Depends(get_publisher),
) -> dict[str, Any]:
    if source not in SUPPORTED_SOURCES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported webhook source")

    payload = await request.json()
    use_case = IngestAlertUseCase(KafkaAdapter(publisher))

    try:
        alert_ids = use_case.execute(source=source, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return {"status": "queued", "alert_ids": alert_ids, "count": len(alert_ids)}
