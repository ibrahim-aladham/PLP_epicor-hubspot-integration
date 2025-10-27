"""
Date utility functions for Epicor-HubSpot integration.

This module provides functions for converting between different date formats,
particularly for transforming Epicor ISO datetime strings to HubSpot's Unix
millisecond timestamps.

IMPORTANT: If no timezone is provided in the datetime string, UTC is assumed
to ensure consistent behavior across different servers and environments.
"""

from datetime import datetime, timezone
from typing import Optional
import logging


logger = logging.getLogger(__name__)


def epicor_to_unix_ms(date_str: Optional[str]) -> Optional[int]:
    """
    Convert Epicor datetime string to Unix milliseconds.

    Epicor uses ISO 8601 format (e.g., "2024-01-15T14:30:00Z" or "2024-01-15T14:30:00").
    HubSpot requires Unix timestamp in milliseconds.

    Timezone handling:
    - If timezone is present (Z, +00:00, etc.), it will be used
    - If no timezone is present, UTC is assumed (NOT server local time)

    Args:
        date_str: ISO 8601 datetime string from Epicor

    Returns:
        Unix timestamp in milliseconds, or None if input is None/invalid

    Examples:
        >>> epicor_to_unix_ms("2024-01-15T14:30:00Z")
        1705329000000
        >>> epicor_to_unix_ms("2024-01-15T14:30:00")  # Assumes UTC
        1705329000000
        >>> epicor_to_unix_ms(None)
        None
    """
    if not date_str:
        return None

    try:
        # Check if timezone information is present
        has_timezone = (
            date_str.endswith('Z') or
            '+' in date_str or
            date_str.count('-') > 2  # Has offset like -05:00
        )

        if date_str.endswith('Z'):
            # Replace Z with explicit UTC offset
            date_str = date_str.replace('Z', '+00:00')
        elif not has_timezone:
            # No timezone info - explicitly set to UTC to avoid using server time
            date_str = date_str + '+00:00'
            logger.debug(f"No timezone in date '{date_str}', assuming UTC")

        # Parse ISO format (will use provided timezone or UTC)
        dt = datetime.fromisoformat(date_str)

        # Convert to Unix milliseconds
        return int(dt.timestamp() * 1000)

    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse date '{date_str}': {e}")
        return None


def format_date(date_str: Optional[str]) -> Optional[str]:
    """
    Format Epicor date for display (YYYY-MM-DD).

    Timezone handling: Uses provided timezone or assumes UTC if not present.

    Args:
        date_str: ISO 8601 datetime string

    Returns:
        Formatted date string (YYYY-MM-DD), or None if input is None/invalid

    Examples:
        >>> format_date("2024-01-15T14:30:00Z")
        '2024-01-15'
        >>> format_date(None)
        None
    """
    if not date_str:
        return None

    try:
        has_timezone = date_str.endswith('Z') or '+' in date_str or date_str.count('-') > 2

        if date_str.endswith('Z'):
            date_str = date_str.replace('Z', '+00:00')
        elif not has_timezone:
            date_str = date_str + '+00:00'

        dt = datetime.fromisoformat(date_str)
        return dt.strftime('%Y-%m-%d')

    except (ValueError, AttributeError):
        return date_str  # Return original if parsing fails


def get_current_timestamp() -> int:
    """
    Get current Unix timestamp in milliseconds (UTC).

    Returns:
        Current Unix timestamp in milliseconds

    Example:
        >>> ts = get_current_timestamp()
        >>> ts > 1700000000000  # After Nov 2023
        True
    """
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def format_datetime(date_str: Optional[str], fmt: str = '%Y-%m-%d %H:%M:%S') -> Optional[str]:
    """
    Format Epicor datetime with custom format string.

    Timezone handling: Uses provided timezone or assumes UTC if not present.

    Args:
        date_str: ISO 8601 datetime string
        fmt: Python datetime format string

    Returns:
        Formatted datetime string, or None if input is None/invalid

    Examples:
        >>> format_datetime("2024-01-15T14:30:00Z", "%B %d, %Y")
        'January 15, 2024'
    """
    if not date_str:
        return None

    try:
        has_timezone = date_str.endswith('Z') or '+' in date_str or date_str.count('-') > 2

        if date_str.endswith('Z'):
            date_str = date_str.replace('Z', '+00:00')
        elif not has_timezone:
            date_str = date_str + '+00:00'

        dt = datetime.fromisoformat(date_str)
        return dt.strftime(fmt)

    except (ValueError, AttributeError):
        return date_str
