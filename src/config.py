"""
Configuration management for Epicor-HubSpot integration.

This module provides a centralized configuration class that loads settings from
environment variables using Pydantic for validation and type safety.
"""

import os
import json
from typing import Optional, Dict, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
import logging

logger = logging.getLogger(__name__)


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

    # Sync Feature Flags
    sync_customers: bool = Field(
        default=True,
        description="Enable customer synchronization"
    )
    sync_quotes: bool = Field(
        default=True,
        description="Enable quote synchronization"
    )
    sync_orders: bool = Field(
        default=True,
        description="Enable order synchronization"
    )

    # Sales Rep Mapping
    sales_rep_mapping_file: str = Field(
        default="config/sales_rep_mapping.json",
        description="Path to sales rep mapping JSON file"
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

    # Cache for sales rep mapping
    _sales_rep_mapping: Optional[Dict[str, Any]] = None

    def get_hubspot_owner(self, sales_rep_code: Optional[str]) -> Optional[str]:
        """
        Get HubSpot owner ID from Epicor sales rep code.

        Loads mapping from JSON file specified in sales_rep_mapping_file.
        Uses fallback to default_owner_id if rep not found in mappings.
        Returns None if no mapping found and no default (deal will be unassigned).

        Args:
            sales_rep_code: Epicor sales rep code

        Returns:
            HubSpot owner ID, default owner ID, or None if not mapped

        Example mapping file (config/sales_rep_mapping.json):
        {
            "default_owner_id": "99999999",  // or null for no fallback
            "mappings": {
                "REP001": "12345678",
                "REP002": "87654321"
            }
        }
        """
        if not sales_rep_code:
            return None

        # Load mapping if not cached
        if self._sales_rep_mapping is None:
            try:
                if os.path.exists(self.sales_rep_mapping_file):
                    with open(self.sales_rep_mapping_file, 'r') as f:
                        self._sales_rep_mapping = json.load(f)

                    # Validate structure
                    if not isinstance(self._sales_rep_mapping, dict):
                        logger.error("Sales rep mapping file is not a valid JSON object")
                        self._sales_rep_mapping = {"mappings": {}, "default_owner_id": None}

                    # Ensure required keys exist
                    if "mappings" not in self._sales_rep_mapping:
                        logger.warning("Sales rep mapping file missing 'mappings' key")
                        self._sales_rep_mapping["mappings"] = {}

                    if "default_owner_id" not in self._sales_rep_mapping:
                        self._sales_rep_mapping["default_owner_id"] = None

                    logger.info(f"Loaded sales rep mapping from {self.sales_rep_mapping_file}")

                    # Log fallback configuration
                    default_owner = self._sales_rep_mapping.get("default_owner_id")
                    if default_owner:
                        logger.info(f"Default owner configured: {default_owner}")
                    else:
                        logger.info("No default owner - unmapped reps will be unassigned")

                else:
                    logger.warning(
                        f"Sales rep mapping file not found: {self.sales_rep_mapping_file}. "
                        f"All deals will be unassigned."
                    )
                    self._sales_rep_mapping = {"mappings": {}, "default_owner_id": None}
            except Exception as e:
                logger.error(f"Failed to load sales rep mapping: {e}")
                self._sales_rep_mapping = {"mappings": {}, "default_owner_id": None}

        # Look up mapping
        mappings = self._sales_rep_mapping.get("mappings", {})
        owner_id = mappings.get(sales_rep_code)

        if owner_id:
            # Found specific mapping
            return owner_id
        else:
            # Use fallback default owner
            default_owner = self._sales_rep_mapping.get("default_owner_id")
            if default_owner:
                logger.debug(
                    f"Rep '{sales_rep_code}' not mapped, using default owner: {default_owner}"
                )
            else:
                logger.debug(
                    f"Rep '{sales_rep_code}' not mapped and no default owner configured"
                )
            return default_owner

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


class Pipelines:
    """
    Helper class for HubSpot pipeline IDs.
    Provides static methods to access pipeline IDs from settings.
    """

    @staticmethod
    def get_quotes_pipeline_id() -> str:
        """
        Get the HubSpot pipeline ID for quotes.

        Returns:
            HubSpot quotes pipeline ID
        """
        return get_settings().hubspot_quotes_pipeline_id

    @staticmethod
    def get_orders_pipeline_id() -> str:
        """
        Get the HubSpot pipeline ID for orders.

        Returns:
            HubSpot orders pipeline ID
        """
        return get_settings().hubspot_orders_pipeline_id


# Convenience alias for settings singleton
settings = get_settings()