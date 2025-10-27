"""
Main entry point for Epicor-HubSpot integration.

This module serves as the AWS Lambda handler for the sync operation.
The actual transformation and sync logic will be implemented after
data mapping approval.
"""

import json
import logging
from typing import Dict, Any

from .config import get_settings
from .utils.logger import setup_logging


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function.

    This is the entry point when deployed as a Lambda function.
    Currently serves as a placeholder for infrastructure validation.

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        Response dict with statusCode and body
    """
    # Initialize logging
    try:
        settings = get_settings()
        setup_logging(level=settings.log_level)
    except Exception:
        setup_logging(level="INFO")

    logger = logging.getLogger(__name__)

    logger.info("=" * 80)
    logger.info("Epicor-HubSpot Integration Lambda Function")
    logger.info("=" * 80)
    logger.info(f"Event: {json.dumps(event, default=str)}")

    try:
        settings = get_settings()

        logger.info("Infrastructure components initialized successfully:")
        logger.info(f"  - Config loaded: ")
        logger.info(f"  - Environment: {settings.environment}")
        logger.info(f"  - Epicor Company: {settings.epicor_company}")
        logger.info(f"  - Batch Size: {settings.sync_batch_size}")
        logger.info(f"  - Max Retries: {settings.sync_max_retries}")

        # Test API connections
        logger.info("\nTesting API connections...")

        from .clients.epicor_client import EpicorClient
        from .clients.hubspot_client import HubSpotClient

        epicor_client = EpicorClient(
            base_url=settings.epicor_base_url,
            company=settings.epicor_company,
            username=settings.epicor_username,
            password=settings.epicor_password,
            api_key=settings.epicor_api_key,
            batch_size=settings.sync_batch_size
        )

        hubspot_client = HubSpotClient(
            api_key=settings.hubspot_api_key
        )

        epicor_connected = epicor_client.test_connection()
        hubspot_connected = hubspot_client.test_connection()

        connection_status = {
            "epicor": " Connected" if epicor_connected else " Failed",
            "hubspot": " Connected" if hubspot_connected else " Failed"
        }

        logger.info(f"\nConnection Status:")
        logger.info(f"  - Epicor: {connection_status['epicor']}")
        logger.info(f"  - HubSpot: {connection_status['hubspot']}")

        response_message = {
            "status": "ready",
            "message": "Infrastructure validated. Waiting for data mapping approval.",
            "connections": connection_status,
            "environment": settings.environment,
            "note": "Transformation and sync modules will be implemented after mapping approval."
        }

        logger.info("\n" + "=" * 80)
        logger.info("Infrastructure Ready ")
        logger.info("=" * 80)

        return {
            "statusCode": 200,
            "body": json.dumps(response_message, indent=2)
        }

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": str(e)
            })
        }


# For local testing
if __name__ == "__main__":
    print("Running Epicor-HubSpot Integration locally...")
    print("-" * 80)

    result = lambda_handler({}, None)

    print("\n" + "-" * 80)
    print("Result:")
    print(json.dumps(json.loads(result["body"]), indent=2))
    print("-" * 80)
