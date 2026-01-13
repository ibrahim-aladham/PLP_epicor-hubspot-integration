"""
Main synchronization orchestrator.
Coordinates all sync operations in the correct order.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.sync.customer_sync import CustomerSync
from src.sync.quote_sync import QuoteSync
from src.sync.order_sync import OrderSync
from src.sync.line_item_sync import LineItemSync
from src.utils.error_handler import FailedRecordTracker
from src.config import settings


logger = logging.getLogger(__name__)


class SyncManager:
    """
    Main sync orchestrator.

    SYNC ORDER:
    1. Customers (must be first - creates companies)
    2. Quotes (needs companies to exist)
    3. Orders (needs companies to exist)
    4. Line Items (optional, handled within quote/order sync)
    """

    def __init__(
        self,
        epicor_client: EpicorClient,
        hubspot_client: HubSpotClient,
        failed_records_file: Optional[str] = None
    ):
        """
        Initialize sync manager.

        Args:
            epicor_client: Epicor API client
            hubspot_client: HubSpot API client
            failed_records_file: Optional path for failed records CSV
        """
        self.epicor = epicor_client
        self.hubspot = hubspot_client

        # Initialize failed record tracker
        self.failed_tracker = FailedRecordTracker(failed_records_file)

        # Initialize sync modules with shared failed tracker
        self.customer_sync = CustomerSync(epicor_client, hubspot_client, self.failed_tracker)
        self.quote_sync = QuoteSync(epicor_client, hubspot_client, self.failed_tracker)
        self.order_sync = OrderSync(epicor_client, hubspot_client, self.failed_tracker)
        self.line_item_sync = LineItemSync(hubspot_client)

    def run_full_sync(self) -> Dict[str, Any]:
        """
        Run full synchronization process.

        Returns:
            Complete sync summary
        """
        start_time = datetime.now()

        logger.info("=" * 80)
        logger.info("STARTING FULL SYNC")
        logger.info(f"Time: {start_time.isoformat()}")
        logger.info("=" * 80)

        summary = {
            'start_time': start_time.isoformat(),
            'customers': None,
            'quotes': None,
            'orders': None,
            'success': True,
            'errors': []
        }

        # 1. Sync Customers (REQUIRED FIRST)
        if settings.sync_customers:
            try:
                logger.info("\n" + "=" * 60)
                logger.info("PHASE 1: CUSTOMER SYNC")
                logger.info("=" * 60)
                summary['customers'] = self.customer_sync.sync_all_customers()
            except Exception as e:
                logger.error(f"Customer sync failed: {e}", exc_info=True)
                summary['success'] = False
                summary['errors'].append(f"Customer sync: {str(e)}")

        # 2. Sync Quotes
        if settings.sync_quotes:
            try:
                logger.info("\n" + "=" * 60)
                logger.info("PHASE 2: QUOTE SYNC")
                logger.info("=" * 60)
                summary['quotes'] = self.quote_sync.sync_all_quotes()
            except Exception as e:
                logger.error(f"Quote sync failed: {e}", exc_info=True)
                summary['success'] = False
                summary['errors'].append(f"Quote sync: {str(e)}")

        # 3. Sync Orders
        if settings.sync_orders:
            try:
                logger.info("\n" + "=" * 60)
                logger.info("PHASE 3: ORDER SYNC")
                logger.info("=" * 60)
                summary['orders'] = self.order_sync.sync_all_orders()
            except Exception as e:
                logger.error(f"Order sync failed: {e}", exc_info=True)
                summary['success'] = False
                summary['errors'].append(f"Order sync: {str(e)}")

        # End time
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        summary['end_time'] = end_time.isoformat()
        summary['duration_seconds'] = duration

        # Get failed records summary
        if self.failed_tracker.has_failures():
            failed_summary = self.failed_tracker.get_summary()
            summary['failed_records'] = failed_summary
            summary['failed_records_file'] = self.failed_tracker.output_file

        # Close the failed tracker
        self.failed_tracker.close()

        logger.info("\n" + "=" * 80)
        logger.info("FULL SYNC COMPLETE")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Success: {summary['success']}")
        if self.failed_tracker.has_failures():
            logger.warning(f"Failed records logged to: {self.failed_tracker.output_file}")
        logger.info("=" * 80)

        return summary
