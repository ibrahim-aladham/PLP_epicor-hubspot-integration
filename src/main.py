"""
Main entry point for Epicor-HubSpot integration.
Can be run locally or via Azure Functions.

For Azure Functions:
- Credentials are loaded from Azure Key Vault via Managed Identity
- See function_app.py for the Azure Functions entry point

For local development:
- Credentials are loaded from .env file
"""

import logging
from datetime import datetime

from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.sync.sync_manager import SyncManager
from src.config import get_settings
from src.utils.logger import setup_logging


# Module-level logger (basic until settings are loaded)
logger = logging.getLogger(__name__)


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
        raise

    # Test connections
    logger.info("Testing API connections...")

    if not epicor_client.test_connection():
        raise RuntimeError("Epicor connection test failed")

    if not hubspot_client.test_connection():
        raise RuntimeError("HubSpot connection test failed")

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
        raise


if __name__ == "__main__":
    # For local development, load .env file
    from dotenv import load_dotenv
    load_dotenv()

    # Setup logging for local run
    settings = get_settings()
    setup_logging(settings.log_level)

    main()
