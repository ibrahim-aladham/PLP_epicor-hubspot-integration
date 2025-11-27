"""
Order synchronization module.
Syncs Epicor Sales Orders to HubSpot Deals (Orders Pipeline).
"""

import logging
from typing import List, Dict, Any, Optional

from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.transformers.order_transformer import OrderTransformer
from src.sync.line_item_sync import LineItemSync
from src.utils.error_handler import ErrorTracker


logger = logging.getLogger(__name__)


class OrderSync:
    """Handles order to deal synchronization."""

    def __init__(
        self,
        epicor_client: EpicorClient,
        hubspot_client: HubSpotClient
    ):
        """
        Initialize order sync.

        Args:
            epicor_client: Epicor API client
            hubspot_client: HubSpot API client
        """
        self.epicor = epicor_client
        self.hubspot = hubspot_client
        self.transformer = OrderTransformer()
        self.line_item_sync = LineItemSync(hubspot_client)
        self.error_tracker = ErrorTracker()

    def sync_all_orders(
        self,
        filter_condition: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sync all orders from Epicor to HubSpot.

        Args:
            filter_condition: Optional OData filter

        Returns:
            Sync summary
        """
        logger.info("=" * 60)
        logger.info("STARTING ORDER SYNC")
        logger.info("=" * 60)

        # Fetch orders from Epicor
        try:
            orders = self.epicor.get_orders(
                expand_line_items=True,
                filter_condition=filter_condition
            )
            logger.info(f"Fetched {len(orders)} orders from Epicor")
        except Exception as e:
            logger.error(f"Failed to fetch orders: {e}")
            return {
                'success': False,
                'error': str(e),
                'total': 0,
                'created': 0,
                'updated': 0,
                'errors': 0
            }

        # Sync each order
        created_count = 0
        updated_count = 0

        for order in orders:
            try:
                result = self.sync_order(order)
                if result == 'created':
                    created_count += 1
                elif result == 'updated':
                    updated_count += 1
            except Exception as e:
                order_num = order.get('OrderNum', 'unknown')
                logger.error(f"Error syncing order {order_num}: {e}")
                self.error_tracker.add_error('order', order_num, str(e))

        # Summary
        summary = {
            'success': True,
            'total': len(orders),
            'created': created_count,
            'updated': updated_count,
            'errors': len(self.error_tracker.errors),
            'error_details': self.error_tracker.errors if self.error_tracker.has_errors() else None
        }

        logger.info("=" * 60)
        logger.info("ORDER SYNC COMPLETE")
        logger.info(f"Total: {summary['total']}, Created: {created_count}, Updated: {updated_count}, Errors: {summary['errors']}")
        logger.info("=" * 60)

        return summary

    def sync_order(self, order_data: Dict[str, Any]) -> str:
        """
        Sync a single order.

        Args:
            order_data: Epicor order record

        Returns:
            'created' or 'updated'
        """
        order_num = order_data['OrderNum']
        cust_num = order_data['CustNum']

        logger.debug(f"Syncing order {order_num} for customer {cust_num}")

        # Transform data
        try:
            properties = self.transformer.transform(order_data)
        except Exception as e:
            logger.error(f"Transformation error for order {order_num}: {e}")
            self.error_tracker.add_error('order', order_num, f"Transform error: {e}")
            return 'error'

        # Check if deal exists in HubSpot
        existing_deal = self.hubspot.get_deal_by_property(
            'epicor_order_number',
            order_num
        )

        # Get customer number for association
        customer_num = self.transformer.get_customer_num(order_data)

        # Find company in HubSpot
        company = self.hubspot.get_company_by_property(
            'epicor_customer_number',
            customer_num
        )

        if not company:
            logger.warning(
                f"Company {customer_num} not found in HubSpot for order {order_num}. "
                f"Skipping order."
            )
            self.error_tracker.add_warning(
                'order',
                order_num,
                f"Company {customer_num} not found"
            )
            return 'error'

        company_id = company['id']

        if existing_deal:
            # Update existing deal
            deal_id = existing_deal['id']
            result = self.hubspot.update_deal(deal_id, properties)
            if result:
                logger.info(f"✅ Updated order {order_num}")
                action = 'updated'
            else:
                logger.error(f"❌ Failed to update order {order_num}")
                self.error_tracker.add_error('order', order_num, "HubSpot update failed")
                return 'error'
        else:
            # Create new deal
            result = self.hubspot.create_deal(properties)
            if result:
                deal_id = result['id']
                logger.info(f"✅ Created order {order_num}")
                action = 'created'
            else:
                logger.error(f"❌ Failed to create order {order_num}")
                self.error_tracker.add_error('order', order_num, "HubSpot create failed")
                return 'error'

        # Always ensure association exists (for both create and update)
        try:
            self.hubspot.associate_deal_to_company(deal_id, company_id)
            logger.debug(f"Associated order {order_num} to company {customer_num}")
        except Exception as e:
            logger.warning(f"Failed to associate order {order_num} to company: {e}")

        # Sync line items if present
        line_items = order_data.get('OrderDtls', [])
        if line_items:
            try:
                line_item_summary = self.line_item_sync.sync_order_line_items(
                    deal_id, line_items, order_num
                )
                logger.info(
                    f"Order {order_num} line items: {line_item_summary['created']} created, "
                    f"{line_item_summary['updated']} updated"
                )
            except Exception as e:
                logger.warning(f"Failed to sync line items for order {order_num}: {e}")

        return action
