"""
Configuration management for Epicor-HubSpot integration.

This module provides a centralized configuration class that loads settings from
environment variables using Pydantic for validation and type safety.
"""

import os
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings are validated using Pydantic and can be loaded from:
    - Environment variables
    - .env files (via python-dotenv)
    - Default values where specified
    """

    # Epicor API Configuration
    epicor_base_url: str = Field(
        ...,
        description="Base URL for Epicor API (e.g., https://plpc-apperp.preformed.ca/ERP11PROD)"
    )
    epicor_company: str = Field(
        ...,
        description="Epicor company ID"
    )
    epicor_username: str = Field(
        ...,
        description="Epicor API username"
    )
    epicor_password: str = Field(
        ...,
        description="Epicor API password"
    )
    epicor_api_key: str = Field(
        ...,
        description="Epicor API key for additional authentication"
    )

    # HubSpot API Configuration
    hubspot_api_key: str = Field(
        ...,
        description="HubSpot private app access token"
    )
    hubspot_quotes_pipeline_id: str = Field(
        ...,
        description="HubSpot pipeline ID for quotes (deals)"
    )
    hubspot_orders_pipeline_id: str = Field(
        ...,
        description="HubSpot pipeline ID for orders (deals)"
    )

    # AWS Configuration
    aws_region: str = Field(
        default="us-east-1",
        description="AWS region for services"
    )
    aws_s3_bucket: Optional[str] = Field(
        default=None,
        description="S3 bucket for logs and artifacts"
    )

    # Sync Configuration
    sync_batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Number of records to process in each batch"
    )
    sync_max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of retry attempts for failed operations"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )

    # Environment
    environment: str = Field(
        default="development",
        description="Environment name (development, staging, production)"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the standard Python logging levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(
                f"log_level must be one of {valid_levels}, got '{v}'"
            )
        return v_upper

    @field_validator("epicor_base_url")
    @classmethod
    def validate_epicor_base_url(cls, v: str) -> str:
        """Ensure Epicor base URL doesn't end with trailing slash."""
        return v.rstrip("/")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is one of the expected values."""
        valid_envs = ["development", "staging", "production"]
        v_lower = v.lower()
        if v_lower not in valid_envs:
            raise ValueError(
                f"environment must be one of {valid_envs}, got '{v}'"
            )
        return v_lower

    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
_settings: Optional[Settings] = None


def get_settings(force_reload: bool = False) -> Settings:
    """
    Get the application settings singleton.

    Args:
        force_reload: If True, reload settings from environment/files

    Returns:
        Settings: The application settings instance

    Example:
        >>> settings = get_settings()
        >>> print(settings.epicor_company)
    """
    global _settings

    if _settings is None or force_reload:
        # Load .env file if it exists
        from dotenv import load_dotenv
        load_dotenv()

        _settings = Settings()

    return _settings


def load_settings_from_file(file_path: str) -> Settings:
    """
    Load settings from a specific .env file.

    Args:
        file_path: Path to the .env file

    Returns:
        Settings: The application settings instance

    Example:
        >>> settings = load_settings_from_file("config/prod.env")
    """
    from dotenv import load_dotenv

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Settings file not found: {file_path}")

    load_dotenv(file_path, override=True)
    return Settings()