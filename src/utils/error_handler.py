"""
Error handling utilities for Epicor-HubSpot integration.

This module provides custom exception classes, error logging wrappers,
and retry decorators for robust error handling throughout the application.
"""

import logging
import time
import functools
from typing import Callable, Any, Type, Tuple, Optional


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
                    'args': str(args)[:200],  # Limit size
                    'kwargs': str(kwargs)[:200]  # Limit size
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
