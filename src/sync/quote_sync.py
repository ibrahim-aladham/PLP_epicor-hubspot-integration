"""
Quote synchronization module with approved pipeline strategy.
Syncs Epicor Quotes to HubSpot Deals (Quotes Pipeline).
"""

import logging
from typing import List, Dict, Any, Optional

from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.transformers.quote_transformer import QuoteTransformer
from src.utils.error_handler import ErrorTracker


logger = logging.getLogger(__name__)


class QuoteSync:
    """Handles quote to deal synchronization with stage logic."""

    def __init__(
        self,
        epicor_client: EpicorClient,
        hubspot_client: HubSpotClient
    ):
        """
        Initialize quote sync.

        Args:
            epicor_client: Epicor API client
            hubspot_client: HubSpot API client
        """
        self.epicor = epicor_client
        self.hubspot = hubspot_client
        self.transformer = QuoteTransformer()
        self.error_tracker = ErrorTracker()

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
            return 'error'

        company_id = company['id']

        if existing_deal:
            # Update existing deal
            deal_id = existing_deal['id']
            result = self.hubspot.update_deal(deal_id, properties)
            if result:
                logger.info(f"✅ Updated quote {quote_num}")
                return 'updated'
            else:
                logger.error(f"❌ Failed to update quote {quote_num}")
                self.error_tracker.add_error('quote', quote_num, "HubSpot update failed")
                return 'error'
        else:
            # Create new deal
            result = self.hubspot.create_deal(properties)
            if result:
                deal_id = result['id']
                logger.info(f"✅ Created quote {quote_num}")

                # Associate with company
                assoc_result = self.hubspot.associate_deal_to_company(deal_id, company_id)
                if assoc_result:
                    logger.debug(f"Associated quote {quote_num} to company {customer_num}")
                else:
                    logger.warning(f"Failed to associate quote {quote_num} to company")

                return 'created'
            else:
                logger.error(f"❌ Failed to create quote {quote_num}")
                self.error_tracker.add_error('quote', quote_num, "HubSpot create failed")
                return 'error'
