"""
Line Item synchronization module with AUTO-PRODUCT CREATION.
Syncs Epicor line items to HubSpot with automatic product creation.
"""

import logging
from typing import List, Dict, Any

from src.clients.hubspot_client import HubSpotClient
from src.transformers.line_item_transformer import LineItemTransformer
from src.utils.error_handler import ErrorTracker


logger = logging.getLogger(__name__)


class LineItemSync:
    """
    Handles line item synchronization with auto-product creation.

    STRATEGY:
    1. Check if product (SKU) exists in HubSpot
    2. If not, create minimal product automatically
    3. Create line item
    4. Associate line item to deal
    """

    def __init__(self, hubspot_client: HubSpotClient):
        """
        Initialize line item sync.

        Args:
            hubspot_client: HubSpot API client
        """
        self.hubspot = hubspot_client
        self.transformer = LineItemTransformer()
        self.error_tracker = ErrorTracker()

        # Cache for products to avoid repeated lookups
        self.product_cache = {}

    def sync_quote_line_items(
        self,
        deal_id: str,
        line_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Sync quote line items to a deal.

        Args:
            deal_id: HubSpot deal ID
            line_items: List of QuoteDtl records from Epicor

        Returns:
            Sync summary
        """
        logger.info(f"Syncing {len(line_items)} quote line items for deal {deal_id}")

        created_count = 0
        product_created_count = 0

        for line_item in line_items:
            try:
                # Transform line item
                properties = self.transformer.transform_quote_line(line_item)
                sku = properties.get('sku')

                if not sku:
                    logger.warning("Line item missing SKU, skipping")
                    continue

                # Ensure product exists (create if needed)
                product_created = self.ensure_product_exists(
                    sku,
                    properties.get('name')
                )
                if product_created:
                    product_created_count += 1

                # Create line item
                result = self.hubspot.create_line_item(properties)
                if result:
                    line_item_id = result['id']

                    # Associate to deal
                    assoc_result = self.hubspot.associate_line_item_to_deal(
                        line_item_id,
                        deal_id
                    )

                    if assoc_result:
                        created_count += 1
                        logger.debug(f"Created line item for SKU {sku}")
                    else:
                        logger.warning(f"Failed to associate line item {sku} to deal")

            except Exception as e:
                logger.error(f"Error creating line item: {e}")
                self.error_tracker.add_error('line_item', str(line_item), str(e))

        summary = {
            'total': len(line_items),
            'created': created_count,
            'products_created': product_created_count,
            'errors': len(self.error_tracker.errors)
        }

        logger.info(
            f"Line items: {created_count}/{len(line_items)} created, "
            f"{product_created_count} products auto-created"
        )

        return summary

    def sync_order_line_items(
        self,
        deal_id: str,
        line_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Sync order line items to a deal.

        Args:
            deal_id: HubSpot deal ID
            line_items: List of OrderDtl records from Epicor

        Returns:
            Sync summary
        """
        logger.info(f"Syncing {len(line_items)} order line items for deal {deal_id}")

        created_count = 0
        product_created_count = 0

        for line_item in line_items:
            try:
                # Transform line item
                properties = self.transformer.transform_order_line(line_item)
                sku = properties.get('sku')

                if not sku:
                    logger.warning("Line item missing SKU, skipping")
                    continue

                # Ensure product exists (create if needed)
                product_created = self.ensure_product_exists(
                    sku,
                    properties.get('name')
                )
                if product_created:
                    product_created_count += 1

                # Create line item
                result = self.hubspot.create_line_item(properties)
                if result:
                    line_item_id = result['id']

                    # Associate to deal
                    assoc_result = self.hubspot.associate_line_item_to_deal(
                        line_item_id,
                        deal_id
                    )

                    if assoc_result:
                        created_count += 1
                        logger.debug(f"Created line item for SKU {sku}")
                    else:
                        logger.warning(f"Failed to associate line item {sku} to deal")

            except Exception as e:
                logger.error(f"Error creating line item: {e}")
                self.error_tracker.add_error('line_item', str(line_item), str(e))

        summary = {
            'total': len(line_items),
            'created': created_count,
            'products_created': product_created_count,
            'errors': len(self.error_tracker.errors)
        }

        logger.info(
            f"Line items: {created_count}/{len(line_items)} created, "
            f"{product_created_count} products auto-created"
        )

        return summary

    def ensure_product_exists(
        self,
        sku: str,
        name: str = None
    ) -> bool:
        """
        Ensure product exists in HubSpot, create if not.

        STRATEGY:
        1. Check cache first
        2. Search HubSpot
        3. Create minimal product if not found

        Args:
            sku: Product SKU
            name: Product name (optional)

        Returns:
            True if product was created, False if already existed
        """
        # Check cache
        if sku in self.product_cache:
            return False

        # Search HubSpot
        product = self.hubspot.get_product_by_sku(sku)

        if product:
            # Product exists, cache it
            self.product_cache[sku] = product['id']
            logger.debug(f"Product {sku} already exists")
            return False
        else:
            # Product doesn't exist, create it
            logger.info(f"Product {sku} not found, auto-creating...")

            # Get minimal product properties
            properties = self.transformer.get_minimal_product_properties(sku, name)

            # Create product
            result = self.hubspot.create_product(properties)

            if result:
                self.product_cache[sku] = result['id']
                logger.info(f"✅ Auto-created product: {sku}")
                return True
            else:
                logger.error(f"❌ Failed to auto-create product: {sku}")
                return False
