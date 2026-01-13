"""
Quote synchronization module with approved pipeline strategy.
Syncs Epicor Quotes to HubSpot Deals (Quotes Pipeline).

When a quote is converted to an order (Closed Won):
- Creates/updates the Order deal in the Orders pipeline
- Associates Order deal with Company
- Links Quote deal to Order deal
"""

import logging
from typing import List, Dict, Any, Optional

from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.transformers.quote_transformer import QuoteTransformer
from src.transformers.order_transformer import OrderTransformer
from src.sync.line_item_sync import LineItemSync
from src.utils.error_handler import ErrorTracker, FailedRecordTracker


logger = logging.getLogger(__name__)


class QuoteSync:
    """Handles quote to deal synchronization with stage logic."""

    def __init__(
        self,
        epicor_client: EpicorClient,
        hubspot_client: HubSpotClient,
        failed_record_tracker: FailedRecordTracker = None
    ):
        """
        Initialize quote sync.

        Args:
            epicor_client: Epicor API client
            hubspot_client: HubSpot API client
            failed_record_tracker: Optional tracker for failed records (CSV output)
        """
        self.epicor = epicor_client
        self.hubspot = hubspot_client
        self.transformer = QuoteTransformer()
        self.order_transformer = OrderTransformer()
        self.line_item_sync = LineItemSync(hubspot_client)
        self.error_tracker = ErrorTracker()
        self.failed_tracker = failed_record_tracker

    def sync_all_quotes(
        self,
        filter_condition: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sync all quotes from Epicor to HubSpot.

        Args:
            filter_condition: Optional OData filter (e.g., for date range)

        Returns:
            Sync summary
        """
        logger.info("=" * 60)
        logger.info("STARTING QUOTE SYNC")
        logger.info("=" * 60)

        # Fetch quotes from Epicor
        try:
            quotes = self.epicor.get_quotes(
                expand_line_items=True,
                filter_condition=filter_condition
            )
            logger.info(f"Fetched {len(quotes)} quotes from Epicor")
        except Exception as e:
            logger.error(f"Failed to fetch quotes: {e}")
            return {
                'success': False,
                'error': str(e),
                'total': 0,
                'created': 0,
                'updated': 0,
                'errors': 0
            }

        # Sync each quote
        created_count = 0
        updated_count = 0

        for quote in quotes:
            try:
                result = self.sync_quote(quote)
                if result == 'created':
                    created_count += 1
                elif result == 'updated':
                    updated_count += 1
            except Exception as e:
                quote_num = quote.get('QuoteNum', 'unknown')
                logger.error(f"Error syncing quote {quote_num}: {e}")
                self.error_tracker.add_error('quote', quote_num, str(e))
                # Track failed record for CSV output
                if self.failed_tracker:
                    self.failed_tracker.add_failed_record(
                        entity_type='quote',
                        entity_id=quote_num,
                        operation='sync',
                        error_message=str(e),
                        error_type=type(e).__name__,
                        source_data=quote
                    )

        # Summary
        summary = {
            'success': True,
            'total': len(quotes),
            'created': created_count,
            'updated': updated_count,
            'errors': len(self.error_tracker.errors),
            'error_details': self.error_tracker.errors if self.error_tracker.has_errors() else None
        }

        logger.info("=" * 60)
        logger.info("QUOTE SYNC COMPLETE")
        logger.info(f"Total: {summary['total']}, Created: {created_count}, Updated: {updated_count}, Errors: {summary['errors']}")
        logger.info("=" * 60)

        return summary

    def sync_quote(self, quote_data: Dict[str, Any]) -> str:
        """
        Sync a single quote with stage logic.

        Args:
            quote_data: Epicor quote record

        Returns:
            'created' or 'updated'
        """
        quote_num = quote_data['QuoteNum']
        cust_num = quote_data['CustNum']

        logger.debug(f"Syncing quote {quote_num} for customer {cust_num}")

        # Check if deal exists in HubSpot
        existing_deal = self.hubspot.get_deal_by_property(
            'epicor_quote_number',
            quote_num
        )

        # Get current stage for stage logic
        current_stage = None
        if existing_deal:
            current_stage = existing_deal.get('properties', {}).get('dealstage')

        # Transform data (includes stage logic)
        try:
            properties = self.transformer.transform(quote_data, current_stage)
        except Exception as e:
            logger.error(f"Transformation error for quote {quote_num}: {e}")
            self.error_tracker.add_error('quote', quote_num, f"Transform error: {e}")
            if self.failed_tracker:
                self.failed_tracker.add_failed_record(
                    entity_type='quote', entity_id=quote_num, operation='transform',
                    error_message=str(e), error_type=type(e).__name__, source_data=quote_data
                )
            return 'error'

        # Get customer number for association
        customer_num = self.transformer.get_customer_num(quote_data)

        # Find company in HubSpot
        company = self.hubspot.get_company_by_property(
            'epicor_customer_number',
            customer_num
        )

        if not company:
            logger.warning(
                f"Company {customer_num} not found in HubSpot for quote {quote_num}. "
                f"Skipping quote."
            )
            self.error_tracker.add_warning(
                'quote',
                quote_num,
                f"Company {customer_num} not found"
            )
            if self.failed_tracker:
                self.failed_tracker.add_failed_record(
                    entity_type='quote', entity_id=quote_num, operation='associate',
                    error_message=f"Company {customer_num} not found in HubSpot",
                    error_type='MissingCompany', source_data=quote_data
                )
            return 'error'

        company_id = company['id']

        if existing_deal:
            # Update existing deal
            deal_id = existing_deal['id']
            result = self.hubspot.update_deal(deal_id, properties)
            if result:
                logger.info(f"Updated quote {quote_num}")
                action = 'updated'
            else:
                logger.error(f"Failed to update quote {quote_num}")
                self.error_tracker.add_error('quote', quote_num, "HubSpot update failed")
                if self.failed_tracker:
                    self.failed_tracker.add_failed_record(
                        entity_type='quote', entity_id=quote_num, operation='update',
                        error_message='HubSpot update failed', error_type='HubSpotAPIError',
                        source_data=quote_data
                    )
                return 'error'
        else:
            # Create new deal
            result = self.hubspot.create_deal(properties)
            if result:
                deal_id = result['id']
                logger.info(f"Created quote {quote_num}")
                action = 'created'
            else:
                logger.error(f"Failed to create quote {quote_num}")
                self.error_tracker.add_error('quote', quote_num, "HubSpot create failed")
                if self.failed_tracker:
                    self.failed_tracker.add_failed_record(
                        entity_type='quote', entity_id=quote_num, operation='create',
                        error_message='HubSpot create failed', error_type='HubSpotAPIError',
                        source_data=quote_data
                    )
                return 'error'

        # Always ensure association exists (for both create and update)
        try:
            self.hubspot.associate_deal_to_company(deal_id, company_id)
            logger.debug(f"Associated quote {quote_num} to company {customer_num}")
        except Exception as e:
            logger.warning(f"Failed to associate quote {quote_num} to company: {e}")

        # Sync line items if present
        line_items = quote_data.get('QuoteDtls', [])
        if line_items:
            try:
                line_item_summary = self.line_item_sync.sync_quote_line_items(
                    deal_id, line_items, quote_num
                )
                logger.info(
                    f"Quote {quote_num} line items: {line_item_summary['created']} created, "
                    f"{line_item_summary['updated']} updated"
                )
            except Exception as e:
                logger.warning(f"Failed to sync line items for quote {quote_num}: {e}")

        # If quote is Closed Won (converted to order), create/link the order deal
        if quote_data.get('Ordered'):
            self._handle_converted_order(quote_num, deal_id, company_id)

        return action

    def _handle_converted_order(
        self,
        quote_num: int,
        quote_deal_id: str,
        company_id: str
    ) -> None:
        """
        Handle a quote that was converted to an order.

        When a quote is Closed Won (Ordered=true):
        1. Find the corresponding order in Epicor
        2. Create/update the Order deal in the Orders pipeline
        3. Associate Order deal with Company
        4. Link Quote deal to Order deal

        Args:
            quote_num: Epicor quote number
            quote_deal_id: HubSpot quote deal ID
            company_id: HubSpot company ID
        """
        logger.info(f"Quote {quote_num} converted to order - processing linked order...")

        # Find the order in Epicor that was created from this quote
        try:
            order_data = self.epicor.get_order_by_quote(quote_num)
        except Exception as e:
            logger.error(f"Failed to find order for quote {quote_num}: {e}")
            self.error_tracker.add_error('quote', quote_num, f"Failed to find linked order: {e}")
            return

        if not order_data:
            logger.warning(f"No order found in Epicor for quote {quote_num}")
            return

        order_num = order_data['OrderNum']
        logger.info(f"Found order {order_num} linked to quote {quote_num}")

        # Transform order data
        try:
            order_properties = self.order_transformer.transform(order_data)
        except Exception as e:
            logger.error(f"Failed to transform order {order_num}: {e}")
            self.error_tracker.add_error('order', order_num, f"Transform error: {e}")
            return

        # Check if order deal exists in HubSpot
        existing_order_deal = self.hubspot.get_deal_by_property(
            'epicor_order_number',
            order_num
        )

        if existing_order_deal:
            # Update existing order deal
            order_deal_id = existing_order_deal['id']
            result = self.hubspot.update_deal(order_deal_id, order_properties)
            if result:
                logger.info(f"✅ Updated linked order {order_num}")
            else:
                logger.error(f"❌ Failed to update order {order_num}")
                self.error_tracker.add_error('order', order_num, "HubSpot update failed")
                return
        else:
            # Create new order deal
            result = self.hubspot.create_deal(order_properties)
            if result:
                order_deal_id = result['id']
                logger.info(f"✅ Created linked order {order_num}")
            else:
                logger.error(f"❌ Failed to create order {order_num}")
                self.error_tracker.add_error('order', order_num, "HubSpot create failed")
                return

        # Associate order deal with company
        try:
            self.hubspot.associate_deal_to_company(order_deal_id, company_id)
            logger.debug(f"Associated order {order_num} to company")
        except Exception as e:
            logger.warning(f"Failed to associate order {order_num} to company: {e}")

        # Link quote deal to order deal
        try:
            self.hubspot.associate_deal_to_deal(quote_deal_id, order_deal_id)
            logger.info(f"🔗 Linked quote {quote_num} to order {order_num}")
        except Exception as e:
            logger.warning(f"Failed to link quote {quote_num} to order {order_num}: {e}")

        # Sync order line items if present
        order_line_items = order_data.get('OrderDtls', [])
        if order_line_items:
            try:
                line_item_summary = self.line_item_sync.sync_order_line_items(
                    order_deal_id, order_line_items, order_num
                )
                logger.info(
                    f"Order {order_num} line items: {line_item_summary['created']} created, "
                    f"{line_item_summary['updated']} updated"
                )
            except Exception as e:
                logger.warning(f"Failed to sync line items for order {order_num}: {e}")
