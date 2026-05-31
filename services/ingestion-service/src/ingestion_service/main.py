from contextlib import asynccontextmanager

from fastapi import FastAPI

from config.settings import get_settings
from ingestion_service.api.routes import health, logs, webhooks
from messaging.kafka_producer import KafkaEventPublisher
from messaging.topics import KafkaTopics


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    topics = KafkaTopics(alerts=settings.kafka_alerts_topic, logs=settings.kafka_logs_topic)
    app.state.publisher = KafkaEventPublisher(settings, topics)
    yield
    app.state.publisher.flush()


app = FastAPI(
    title="AI Incident Commander — Ingestion Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(logs.router, prefix="/api/v1")
