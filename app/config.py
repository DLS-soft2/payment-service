"""
Application settings loaded from environment variables.

Uses pydantic-settings to automatically read env vars.
Default values match the docker-compose setup so the service
works out of the box with `docker compose up`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Payment Service."""

    model_config = SettingsConfigDict(env_file=".env")

    # Service metadata
    service_name: str = "payment-service"
    service_version: str = "0.1.0"

    # PostgreSQL connection
    # Format: postgresql://user:password@host:port/database
    database_url: str = "postgresql://payment:payment@localhost:5433/payment_db"

    # Kafka connection
    kafka_bootstrap_servers: str = "localhost:9092"

    # Kafka topics this service interacts with
    kafka_topic_orders: str = "orders"
    kafka_topic_payments: str = "payments"


# Single instance used throughout the app
settings = Settings()
