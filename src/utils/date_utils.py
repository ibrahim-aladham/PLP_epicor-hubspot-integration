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


# Alias for consistency with spec
epicor_datetime_to_unix_ms = epicor_to_unix_ms


def epicor_date_to_midnight_utc(date_str: Optional[str]) -> Optional[int]:
    """
    Convert Epicor date string to Unix milliseconds at midnight UTC.

    HubSpot date-only properties (like closedate, createdate) require timestamps
    to be set at midnight UTC (00:00:00.000 UTC) for that date.

    Args:
        date_str: ISO 8601 datetime string from Epicor

    Returns:
        Unix timestamp in milliseconds at midnight UTC, or None if input is None/invalid

    Examples:
        >>> epicor_date_to_midnight_utc("2024-01-15T14:30:00Z")
        1705276800000  # Midnight UTC on 2024-01-15
        >>> epicor_date_to_midnight_utc("2024-01-15")
        1705276800000  # Midnight UTC on 2024-01-15
        >>> epicor_date_to_midnight_utc(None)
        None
    """
    if not date_str:
        return None

    try:
        # Handle various date formats
        if date_str.endswith('Z'):
            date_str = date_str.replace('Z', '+00:00')

        # Check if it's just a date (no time component)
        if 'T' not in date_str and len(date_str) <= 10:
            # Parse date-only string
            dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
        else:
            # Parse full datetime
            has_timezone = '+' in date_str or date_str.count('-') > 2
            if not has_timezone:
                date_str = date_str + '+00:00'
            dt = datetime.fromisoformat(date_str)

        # Create a new datetime at midnight UTC for that date
        midnight_utc = datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=timezone.utc)

        return int(midnight_utc.timestamp() * 1000)

    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse date '{date_str}' for midnight UTC conversion: {e}")
        return None


def guid_to_string(guid: Optional[str]) -> Optional[str]:
    """
    Convert GUID to string (removes hyphens and formats consistently).

    Args:
        guid: GUID string (e.g., "123e4567-e89b-12d3-a456-426614174000")

    Returns:
        Formatted GUID string without hyphens, or None if input is None

    Examples:
        >>> guid_to_string("123e4567-e89b-12d3-a456-426614174000")
        '123e4567e89b12d3a456426614174000'
        >>> guid_to_string(None)
        None
    """
    if not guid:
        return None

    try:
        # Remove hyphens and convert to lowercase for consistency
        return str(guid).replace('-', '').lower()
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to convert GUID '{guid}': {e}")
        return str(guid) if guid else None


def format_phone_e164(phone: Optional[str]) -> Optional[str]:
    """
    Format phone number to E.164 format (international standard).

    E.164 format: +[country code][subscriber number]
    Example: +14165551234

    This is a simplified implementation that:
    - Assumes North American numbers (country code +1) if no + prefix
    - Removes all non-digit characters except leading +
    - Returns None for invalid/empty inputs

    Args:
        phone: Phone number in various formats

    Returns:
        E.164 formatted phone number, or None if invalid/empty

    Examples:
        >>> format_phone_e164("(416) 555-1234")
        '+14165551234'
        >>> format_phone_e164("416-555-1234")
        '+14165551234'
        >>> format_phone_e164("+14165551234")
        '+14165551234'
        >>> format_phone_e164(None)
        None
        >>> format_phone_e164("")
        None
    """
    if not phone:
        return None

    try:
        # Convert to string and strip whitespace
        phone_str = str(phone).strip()

        if not phone_str:
            return None

        # Check if already has country code
        has_country_code = phone_str.startswith('+')

        # Remove all non-digit characters except leading +
        if has_country_code:
            digits = '+' + ''.join(c for c in phone_str[1:] if c.isdigit())
        else:
            digits = ''.join(c for c in phone_str if c.isdigit())

        # If no digits, return None
        if not digits or digits == '+':
            return None

        # Add country code if not present (assume North America +1)
        if not has_country_code:
            # Check if number already starts with 1 (North American number)
            if len(digits) == 11 and digits.startswith('1'):
                digits = '+' + digits
            elif len(digits) == 10:
                digits = '+1' + digits
            else:
                # For other lengths, just add + prefix
                digits = '+' + digits

        return digits

    except Exception as e:
        logger.warning(f"Failed to format phone '{phone}': {e}")
        return None
