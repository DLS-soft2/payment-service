"""
Application settings loaded from environment variables.

Uses pydantic-settings to automatically read env vars.
Default values match the docker-compose setup so the service
works out of the box with `docker compose up`.
"""

from importlib.metadata import PackageNotFoundError, version
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_default_service_version() -> str:
    """
    Derive the default service version from the installed package metadata.

    Falls back to the project version declared in pyproject.toml when the
    distribution is not installed (e.g. in local development).
    """
    try:
        return version("payment-service")
    except PackageNotFoundError:
        # Keep this in sync with the project version in pyproject.toml
        return "0.2.0"


class Settings(BaseSettings):
    """Central configuration for the Payment Service."""

    model_config = SettingsConfigDict(env_file=".env")

    # Service metadata
    service_name: str = "payment-service"
    service_version: str = _get_default_service_version()

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
