from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from messaging.topics import TOPIC_ALERTS_V1, TOPIC_INCIDENTS_V1, TOPIC_TELEMETRY_V1


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables / .env file.

    All Kafka topic names default to the canonical constants defined in
    ``messaging.topics`` so that the defaults are always in sync with the
    topic registry.  Override via environment variables in docker-compose or CI.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ------------------------------------------------------------------
    # Kafka
    # ------------------------------------------------------------------
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "aic-shared"

    # Topic names — defaults from the topic registry constants.
    kafka_alerts_topic: str = TOPIC_ALERTS_V1
    kafka_incidents_topic: str = TOPIC_INCIDENTS_V1
    kafka_telemetry_topic: str = TOPIC_TELEMETRY_V1

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------
    database_url: str = (
        "postgresql://incident_commander:incident_commander"
        "@localhost:5432/incident_commander"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
