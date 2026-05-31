from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from common.schemas.log_event import LogIngestRequest
from ingestion_service.api.dependencies import get_publisher
from ingestion_service.application.use_cases.ingest_logs import IngestLogsUseCase
from ingestion_service.infrastructure.messaging.kafka_event_publisher import KafkaAdapter

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
def ingest_logs(
    body: LogIngestRequest,
    publisher=Depends(get_publisher),
) -> dict[str, Any]:
    use_case = IngestLogsUseCase(KafkaAdapter(publisher))

    try:
        log_ids = use_case.execute(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return {"status": "queued", "log_ids": log_ids, "count": len(log_ids)}
