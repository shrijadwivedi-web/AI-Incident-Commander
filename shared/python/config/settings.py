from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_alerts_topic: str = "alerts-topic"
    kafka_logs_topic: str = "logs-topic"
    kafka_client_id: str = "aic-ingestion"


@lru_cache
def get_settings() -> Settings:
    return Settings()
