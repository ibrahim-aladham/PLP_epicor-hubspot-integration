"""
Error handling utilities for Epicor-HubSpot integration.

This module provides custom exception classes, error logging wrappers,
retry decorators, and failed record tracking for robust error handling.
"""

import logging
import time
import functools
import csv
import os
from datetime import datetime
from typing import Callable, Any, Type, Tuple, Optional, List, Dict


logger = logging.getLogger(__name__)


# ============================================================================
# Custom Exception Classes
# ============================================================================

class IntegrationError(Exception):
    """Base exception for integration errors."""
    pass


class EpicorAPIError(IntegrationError):
    """Exception raised for Epicor API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[str] = None):
        self.status_code = status_code
        self.response = response
        super().__init__(f"Epicor API Error: {message}")


class HubSpotAPIError(IntegrationError):
    """Exception raised for HubSpot API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[str] = None):
        self.status_code = status_code
        self.response = response
        super().__init__(f"HubSpot API Error: {message}")


class TransformationError(IntegrationError):
    """Exception raised for data transformation errors."""
    pass


class ConfigurationError(IntegrationError):
    """Exception raised for configuration errors."""
    pass


class ValidationError(IntegrationError):
    """Exception raised for data validation errors."""
    pass


# ============================================================================
# Retry Decorator
# ============================================================================

def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable:
    """
    Decorator to retry a function on failure with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch and retry

    Returns:
        Decorated function

    Example:
        >>> @retry(max_attempts=3, delay=1, backoff=2)
        ... def fetch_data():
        ...     # Function that might fail
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise

                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


# ============================================================================
# Error Logging Wrapper
# ============================================================================

def log_errors(func: Callable) -> Callable:
    """
    Decorator to log exceptions with full context.

    Args:
        func: Function to wrap

    Returns:
        Decorated function that logs errors before raising

    Example:
        >>> @log_errors
        ... def process_data(data):
        ...     # Function that might raise exceptions
        ...     pass
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(
                f"Error in {func.__name__}: {type(e).__name__}: {str(e)}",
                exc_info=True,
                extra={
                    'function': func.__name__,
                    'function_args': str(args)[:200],  # Renamed to avoid LogRecord conflict
                    'function_kwargs': str(kwargs)[:200]  # Renamed to avoid LogRecord conflict
                }
            )
            raise

    return wrapper


# ============================================================================
# Error Context Manager
# ============================================================================

class ErrorContext:
    """
    Context manager for consistent error handling and logging.

    Example:
        >>> with ErrorContext("Processing customer data", customer_id=123):
        ...     process_customer()
    """

    def __init__(self, operation: str, **context):
        """
        Initialize error context.

        Args:
            operation: Description of the operation
            **context: Additional context key-value pairs
        """
        self.operation = operation
        self.context = context

    def __enter__(self):
        logger.debug(f"Starting: {self.operation}", extra=self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error(
                f"Failed: {self.operation} - {exc_type.__name__}: {exc_val}",
                exc_info=True,
                extra=self.context
            )
        else:
            logger.debug(f"Completed: {self.operation}", extra=self.context)
        # Return False to propagate exceptions
        return False


# ============================================================================
# Error Handler Functions
# ============================================================================

def handle_api_error(response, api_name: str = "API") -> None:
    """
    Handle HTTP API errors consistently.

    Args:
        response: requests.Response object
        api_name: Name of the API for error messages

    Raises:
        EpicorAPIError or HubSpotAPIError depending on api_name
    """
    status_code = response.status_code
    try:
        error_detail = response.json()
    except:
        error_detail = response.text

    error_message = f"{api_name} request failed with status {status_code}"

    if api_name.lower() == "epicor":
        raise EpicorAPIError(error_message, status_code, str(error_detail))
    elif api_name.lower() == "hubspot":
        raise HubSpotAPIError(error_message, status_code, str(error_detail))
    else:
        raise IntegrationError(f"{error_message}: {error_detail}")


def safe_get(dictionary: dict, *keys, default: Any = None) -> Any:
    """
    Safely get nested dictionary values.

    Args:
        dictionary: Dictionary to traverse
        *keys: Keys to traverse
        default: Default value if key not found

    Returns:
        Value at the nested key path, or default if not found

    Example:
        >>> data = {'a': {'b': {'c': 123}}}
        >>> safe_get(data, 'a', 'b', 'c')
        123
        >>> safe_get(data, 'a', 'x', 'y', default=0)
        0
    """
    result = dictionary
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
            if result is None:
                return default
        else:
            return default
    return result if result is not None else default


# ============================================================================
# Error Tracker Class
# ============================================================================

class ErrorTracker:
    """
    Track errors and warnings during sync operations.

    Collects errors and warnings for reporting after batch operations complete.

    Example:
        >>> tracker = ErrorTracker()
        >>> tracker.add_error('customer', 123, 'Failed to sync')
        >>> tracker.add_warning('quote', 456, 'Missing field')
        >>> print(tracker.has_errors())
        True
        >>> print(tracker.get_summary())
    """

    def __init__(self):
        """Initialize empty error and warning lists."""
        self.errors = []
        self.warnings = []

    def add_error(self, entity_type: str, identifier: Any, message: str) -> None:
        """
        Add an error to the tracker.

        Args:
            entity_type: Type of entity (e.g., 'customer', 'quote', 'order')
            identifier: Identifier of the entity (e.g., CustNum, QuoteNum)
            message: Error message
        """
        error_entry = {
            'type': entity_type,
            'id': identifier,
            'message': message
        }
        self.errors.append(error_entry)
        logger.error(f"[{entity_type}:{identifier}] {message}")

    def add_warning(self, entity_type: str, identifier: Any, message: str) -> None:
        """
        Add a warning to the tracker.

        Args:
            entity_type: Type of entity (e.g., 'customer', 'quote', 'order')
            identifier: Identifier of the entity
            message: Warning message
        """
        warning_entry = {
            'type': entity_type,
            'id': identifier,
            'message': message
        }
        self.warnings.append(warning_entry)
        logger.warning(f"[{entity_type}:{identifier}] {message}")

    def has_errors(self) -> bool:
        """Return True if any errors have been recorded."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Return True if any warnings have been recorded."""
        return len(self.warnings) > 0

    def get_summary(self) -> dict:
        """
        Get a summary of all errors and warnings.

        Returns:
            Dictionary with error and warning counts and details
        """
        return {
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'errors': self.errors,
            'warnings': self.warnings
        }

    def clear(self) -> None:
        """Clear all errors and warnings."""
        self.errors = []
        self.warnings = []


# ============================================================================
# Failed Record Tracker (CSV-based)
# ============================================================================

class FailedRecordTracker:
    """
    Tracks failed sync records and writes them to a CSV file for retry.

    This tracker logs failed records with full context for debugging and
    enables easy retry of failed records.

    Example:
        >>> tracker = FailedRecordTracker("logs/failed_records.csv")
        >>> tracker.add_failed_record(
        ...     entity_type='quote',
        ...     entity_id=12345,
        ...     operation='create',
        ...     error_message='HubSpot API timeout',
        ...     source_data={'QuoteNum': 12345, 'CustNum': 100}
        ... )
        >>> tracker.close()
    """

    CSV_HEADERS = [
        'timestamp',
        'entity_type',
        'entity_id',
        'operation',
        'error_message',
        'error_type',
        'source_data',
        'retry_count'
    ]

    def __init__(self, output_file: str = None):
        """
        Initialize failed record tracker.

        Args:
            output_file: Path to CSV file. Defaults to logs/failed_records_<timestamp>.csv
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"logs/failed_records_{timestamp}.csv"

        self.output_file = output_file
        self.failed_records: List[Dict] = []
        self._file_handle = None
        self._writer = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Initialize CSV file and writer on first use."""
        if self._initialized:
            return

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.output_file) if os.path.dirname(self.output_file) else 'logs', exist_ok=True)

        # Check if file exists (for header writing)
        file_exists = os.path.exists(self.output_file)

        # Open file in append mode
        self._file_handle = open(self.output_file, 'a', newline='', encoding='utf-8')
        self._writer = csv.DictWriter(self._file_handle, fieldnames=self.CSV_HEADERS)

        # Write header only if new file
        if not file_exists:
            self._writer.writeheader()

        self._initialized = True
        logger.info(f"Failed record tracker initialized: {self.output_file}")

    def add_failed_record(
        self,
        entity_type: str,
        entity_id: Any,
        operation: str,
        error_message: str,
        error_type: str = None,
        source_data: Dict = None,
        retry_count: int = 0
    ) -> None:
        """
        Add a failed record to the tracker.

        Args:
            entity_type: Type of entity (customer, quote, order, line_item, product)
            entity_id: Identifier of the entity (e.g., QuoteNum, OrderNum)
            operation: Operation that failed (create, update, delete, associate)
            error_message: Human-readable error description
            error_type: Exception class name (optional)
            source_data: Original data that failed to sync (optional)
            retry_count: Number of times this record has been retried
        """
        self._ensure_initialized()

        record = {
            'timestamp': datetime.now().isoformat(),
            'entity_type': entity_type,
            'entity_id': str(entity_id),
            'operation': operation,
            'error_message': str(error_message)[:500],  # Truncate long messages
            'error_type': error_type or 'Unknown',
            'source_data': str(source_data)[:1000] if source_data else '',
            'retry_count': retry_count
        }

        # Write to CSV immediately
        self._writer.writerow(record)
        self._file_handle.flush()  # Ensure written to disk

        # Keep in memory for summary
        self.failed_records.append(record)

        # Log the failure
        logger.error(
            f"FAILED [{entity_type}:{entity_id}] {operation}: {error_message}"
        )

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of failed records.

        Returns:
            Dictionary with counts by entity type and operation
        """
        summary = {
            'total_failures': len(self.failed_records),
            'output_file': self.output_file,
            'by_entity_type': {},
            'by_operation': {}
        }

        for record in self.failed_records:
            # Count by entity type
            entity_type = record['entity_type']
            if entity_type not in summary['by_entity_type']:
                summary['by_entity_type'][entity_type] = 0
            summary['by_entity_type'][entity_type] += 1

            # Count by operation
            operation = record['operation']
            if operation not in summary['by_operation']:
                summary['by_operation'][operation] = 0
            summary['by_operation'][operation] += 1

        return summary

    def has_failures(self) -> bool:
        """Return True if any records have failed."""
        return len(self.failed_records) > 0

    def close(self) -> None:
        """Close the CSV file handle."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
            self._writer = None

        if self.failed_records:
            logger.warning(
                f"Sync completed with {len(self.failed_records)} failures. "
                f"See {self.output_file} for details."
            )

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure file is closed."""
        self.close()
        return False
