"""
Main entry point for Epicor-HubSpot integration.
Can be run locally or as AWS Lambda function.

For AWS Lambda:
- Credentials are loaded from AWS Secrets Manager at runtime
- Secret name defaults to 'epicor-hubspot-credentials' or AWS_SECRET_NAME env var

For local development:
- Credentials are loaded from .env file
"""

import logging
import sys
from datetime import datetime

from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.sync.sync_manager import SyncManager
from src.config import load_secrets_from_aws, get_settings
from src.utils.logger import setup_logger


# Module-level logger (basic until settings are loaded)
logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    """
    AWS Lambda handler function.

    Loads credentials from AWS Secrets Manager before initializing settings.

    Args:
        event: Lambda event data
        context: Lambda context

    Returns:
        Response dict with statusCode and body
    """
    # Step 1: Load secrets from AWS Secrets Manager (before settings init)
    try:
        load_secrets_from_aws()
    except Exception as e:
        # Log to CloudWatch even without proper logger setup
        print(f"CRITICAL: Failed to load secrets from AWS Secrets Manager: {e}")
        return {
            'statusCode': 500,
            'body': {'error': f'Failed to load secrets: {str(e)}'}
        }

    # Step 2: Now we can safely get settings and setup proper logging
    settings = get_settings()
    global logger
    logger = setup_logger("epicor_hubspot_sync", settings.log_level)

    logger.info("Lambda function invoked")
    logger.info(f"Event: {event}")

    # Step 3: Run the sync
    try:
        result = main()
        return {
            'statusCode': 200,
            'body': result
        }
    except Exception as e:
        logger.error(f"Lambda execution failed: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {'error': str(e)}
        }


def main():
    """
    Main synchronization function.

    Returns:
        Sync summary
    """
    logger.info("=" * 80)
    logger.info("EPICOR-HUBSPOT INTEGRATION STARTING")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info("=" * 80)

    # Initialize clients
    logger.info("Initializing API clients...")

    try:
        epicor_client = EpicorClient()
        logger.info("✅ Epicor client initialized")

        hubspot_client = HubSpotClient()
        logger.info("✅ HubSpot client initialized")

    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        sys.exit(1)

    # Test connections
    logger.info("Testing API connections...")

    if not epicor_client.test_connection():
        logger.error("Epicor connection test failed")
        sys.exit(1)

    if not hubspot_client.test_connection():
        logger.error("HubSpot connection test failed")
        sys.exit(1)

    logger.info("✅ All connections successful")

    # Initialize sync manager
    sync_manager = SyncManager(epicor_client, hubspot_client)

    # Run full sync
    try:
        result = sync_manager.run_full_sync()

        logger.info("\n" + "=" * 80)
        logger.info("SYNC SUMMARY:")
        logger.info(f"Success: {result['success']}")
        logger.info(f"Duration: {result.get('duration_seconds', 0):.2f} seconds")

        if result.get('customers'):
            logger.info(f"Customers: {result['customers']['created']} created, "
                       f"{result['customers']['updated']} updated, "
                       f"{result['customers']['errors']} errors")

        if result.get('quotes'):
            logger.info(f"Quotes: {result['quotes']['created']} created, "
                       f"{result['quotes']['updated']} updated, "
                       f"{result['quotes']['errors']} errors")

        if result.get('orders'):
            logger.info(f"Orders: {result['orders']['created']} created, "
                       f"{result['orders']['updated']} updated, "
                       f"{result['orders']['errors']} errors")

        logger.info("=" * 80)

        return result

    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # For local development, load .env file
    from dotenv import load_dotenv
    load_dotenv()

    # Setup logging for local run
    settings = get_settings()
    logger = setup_logger("epicor_hubspot_sync", settings.log_level)

    main()
