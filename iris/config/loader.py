"""Environment-based configuration loader."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class LoggingConfig(BaseModel):
    """Logging settings for the application."""

    level: str = Field(default="INFO")
    file_path: Path = Field(default=Path("logs/iris.log"))


class AppConfig(BaseModel):
    """Runtime settings for IRIS."""

    app_name: str = Field(default="IRIS")
    environment: str = Field(default="development")
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(env_file: str | Path = ".env") -> AppConfig:
    """Load configuration from environment variables and an optional dotenv file."""
    load_dotenv(dotenv_path=env_file)

    return AppConfig(
        app_name=os.getenv("IRIS_APP_NAME", "IRIS"),
        environment=os.getenv("IRIS_ENVIRONMENT", "development"),
        logging=LoggingConfig(
            level=os.getenv("IRIS_LOG_LEVEL", "INFO"),
            file_path=Path(os.getenv("IRIS_LOG_FILE", "logs/iris.log")),
        ),
    )
