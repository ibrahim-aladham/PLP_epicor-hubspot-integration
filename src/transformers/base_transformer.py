"""
Base transformer class for data transformation.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod


logger = logging.getLogger(__name__)


class BaseTransformer(ABC):
    """Base class for all data transformers."""

    @abstractmethod
    def transform(self, source_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform source data to target format.

        Args:
            source_data: Source data from Epicor

        Returns:
            Transformed data for HubSpot
        """
        pass

    def safe_get(
        self,
        data: Dict[str, Any],
        key: str,
        default: Any = None
    ) -> Any:
        """
        Safely get a value from dictionary.

        Args:
            data: Dictionary to get value from
            key: Key to look up
            default: Default value if key not found

        Returns:
            Value or default
        """
        return data.get(key, default)

    def validate_required_fields(
        self,
        data: Dict[str, Any],
        required_fields: list
    ) -> bool:
        """
        Validate that required fields are present.

        Args:
            data: Data to validate
            required_fields: List of required field names

        Returns:
            True if all required fields present
        """
        missing_fields = [f for f in required_fields if f not in data or data[f] is None]

        if missing_fields:
            logger.error(f"Missing required fields: {missing_fields}")
            return False

        return True

    def _get_today_midnight_utc(self) -> int:
        """
        Get today's date at midnight UTC as Unix milliseconds.

        HubSpot datepicker properties require timestamps at midnight UTC.

        Returns:
            Unix timestamp in milliseconds for today at 00:00:00 UTC
        """
        now = datetime.now(timezone.utc)
        midnight = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
        return int(midnight.timestamp() * 1000)
