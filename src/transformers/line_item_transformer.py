"""
Line Item transformer with AUTO-PRODUCT CREATION.
Transforms Epicor line items (QuoteDtls/OrderDtls) to HubSpot Line Items.

AGREED SOLUTION:
- Auto-create minimal products on-the-fly if SKU doesn't exist
- No bulk product sync (deleted from scope)
- Client wants part_number reporting without syncing 9,000 parts
"""

import logging
from typing import Dict, Any, Optional

from src.transformers.base_transformer import BaseTransformer


logger = logging.getLogger(__name__)


class LineItemTransformer(BaseTransformer):
    """Transform Epicor line items to HubSpot line items."""

    def transform(self, source_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Default transform method (not used for line items).
        Use transform_quote_line or transform_order_line instead.
        """
        raise NotImplementedError(
            "Use transform_quote_line or transform_order_line instead"
        )

    def transform_quote_line(
        self,
        line_data: Dict[str, Any],
        quote_num: int = None
    ) -> Dict[str, Any]:
        """
        Transform QuoteDtl to HubSpot line item properties.

        Args:
            line_data: Epicor QuoteDtl record
            quote_num: Quote number (if not in line_data)

        Returns:
            HubSpot line item properties
        """
        # Get quote number and line number for unique ID
        q_num = quote_num or self.safe_get(line_data, 'QuoteNum')
        q_line = self.safe_get(line_data, 'QuoteLine')

        properties = {
            'sku': self.safe_get(line_data, 'PartNum'),
            'name': self.safe_get(line_data, 'LineDesc') or f"Part {line_data.get('PartNum', '')}",
            'quantity': self.safe_get(line_data, 'OrderQty', 1),
            'price': self.safe_get(line_data, 'DocUnitPrice', 0),
            'amount': self.safe_get(line_data, 'DocExtPriceDtl', 0)
        }

        # Add unique identifier for upsert logic
        if q_num and q_line:
            properties['epicor_line_item_id'] = f"Q{q_num}-{q_line}"

        # Remove None values
        properties = {k: v for k, v in properties.items() if v is not None}

        logger.debug(f"Transformed quote line: {properties.get('sku')} ({properties.get('epicor_line_item_id')})")

        return properties

    def transform_order_line(
        self,
        line_data: Dict[str, Any],
        order_num: int = None
    ) -> Dict[str, Any]:
        """
        Transform OrderDtl to HubSpot line item properties.

        Args:
            line_data: Epicor OrderDtl record
            order_num: Order number (if not in line_data)

        Returns:
            HubSpot line item properties
        """
        # Get order number and line number for unique ID
        o_num = order_num or self.safe_get(line_data, 'OrderNum')
        o_line = self.safe_get(line_data, 'OrderLine')

        properties = {
            'sku': self.safe_get(line_data, 'PartNum'),
            'name': self.safe_get(line_data, 'LineDesc') or f"Part {line_data.get('PartNum', '')}",
            'quantity': self.safe_get(line_data, 'OrderQty', 1),
            'price': self.safe_get(line_data, 'DocUnitPrice', 0),
            'amount': self.safe_get(line_data, 'DocExtPriceDtl', 0)
        }

        # Add unique identifier for upsert logic
        if o_num and o_line:
            properties['epicor_line_item_id'] = f"O{o_num}-{o_line}"

        # Remove None values
        properties = {k: v for k, v in properties.items() if v is not None}

        logger.debug(f"Transformed order line: {properties.get('sku')} ({properties.get('epicor_line_item_id')})")

        return properties

    def get_minimal_product_properties(
        self,
        part_num: str,
        line_desc: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create minimal product properties for auto-creation.

        MINIMAL PRODUCT FIELDS:
        - hs_sku (required)
        - name (required)
        - description

        Args:
            part_num: Part number (SKU)
            line_desc: Line description (used as name if available)

        Returns:
            Minimal product properties
        """
        return {
            'hs_sku': part_num,
            'name': line_desc or f"Part {part_num}",
            'description': f"Auto-created from Epicor sync on first use"
        }
