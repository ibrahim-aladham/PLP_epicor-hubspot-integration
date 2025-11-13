"""
Order to Deal transformer with FULL Stage Logic.
Transforms Epicor SalesOrder records to HubSpot Deal records.

AGREED SOLUTION:
- READ VoidOrder, OrderHeld, TotalShipped from Epicor for stage logic
- DO NOT sync these as HubSpot properties (they're in deleted list)
- Use full 5-stage logic instead of simplified 2-stage

ORDER PIPELINE STAGES (5 total):
1. Order Received - New order, nothing shipped
2. Order Held - Credit hold
3. Partially Shipped - Some items shipped
4. Completed - Fully shipped/closed
5. Cancelled - Voided order
"""

import logging
from typing import Dict, Any
from datetime import datetime

from src.transformers.base_transformer import BaseTransformer
from src.utils.date_utils import epicor_datetime_to_unix_ms, guid_to_string
from src.config import Pipelines


logger = logging.getLogger(__name__)


class OrderStageLogic:
    """
    Order Pipeline Stage Logic.

    USES FIELDS FOR LOGIC (not synced to HubSpot):
    - VoidOrder
    - OrderHeld
    - TotalShipped
    """

    @staticmethod
    def get_stage_from_epicor(order_data: Dict[str, Any]) -> str:
        """
        Derive HubSpot stage from Epicor fields.

        PRIORITY ORDER:
        1. VoidOrder=true ’ cancelled
        2. OpenOrder=false ’ completed
        3. OrderHeld=true ’ order_held
        4. OpenOrder=true AND TotalShipped>0 ’ partially_shipped
        5. Default ’ order_received

        Args:
            order_data: Epicor order record

        Returns:
            HubSpot stage internal name
        """
        void_order = order_data.get('VoidOrder', False)
        order_held = order_data.get('OrderHeld', False)
        open_order = order_data.get('OpenOrder', True)
        total_shipped = order_data.get('TotalShipped', 0)

        # Priority 1: Cancelled
        if void_order:
            logger.debug(f"Order stage: cancelled (VoidOrder=true)")
            return 'cancelled'

        # Priority 2: Completed
        if not open_order:
            logger.debug(f"Order stage: completed (OpenOrder=false)")
            return 'completed'

        # Priority 3: On hold
        if order_held:
            logger.debug(f"Order stage: order_held (OrderHeld=true)")
            return 'order_held'

        # Priority 4: Partially shipped
        if open_order and total_shipped > 0:
            logger.debug(
                f"Order stage: partially_shipped "
                f"(OpenOrder=true, TotalShipped={total_shipped})"
            )
            return 'partially_shipped'

        # Priority 5: New order
        logger.debug(f"Order stage: order_received (default)")
        return 'order_received'


class OrderTransformer(BaseTransformer):
    """Transform Epicor SalesOrder to HubSpot Deal with full stage logic."""

    REQUIRED_FIELDS = ['OrderNum', 'CustNum', 'OpenOrder']

    def transform(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Epicor order to HubSpot deal properties.

        MAPPING (13 ACTIVE FIELDS SYNCED TO HUBSPOT):
        1. OrderNum ’ dealname
        2. OrderNum ’ epicor_order_number (PRIMARY)
        3. CustNum ’ (association)
        4. OrderDate ’ createdate
        5. RequestDate ’ closedate
        6. NeedByDate ’ need_by_date
        7. OrderAmt ’ amount
        8. DocOrderAmt ’ epicor_doc_amount
        9. PONum ’ customer_po_number
        10. OpenOrder ’ epicor_open_order
        11. CurrencyCode ’ deal_currency_code
        12. SysRowID ’ epicor_order_sysrowid
        13. (hardcoded) ’ pipeline

        DELETED FIELDS (READ for stage logic, NOT synced):
        - TotalCharges
        - OrderHeld (used in stage logic)
        - VoidOrder (used in stage logic)
        - OrderStatus
        - TotalShipped (used in stage logic)

        Args:
            order_data: Epicor order record

        Returns:
            HubSpot deal properties

        Raises:
            ValueError: If required fields missing
        """
        # Validate required fields
        if not self.validate_required_fields(order_data, self.REQUIRED_FIELDS):
            raise ValueError(
                f"Missing required fields in order {order_data.get('OrderNum')}"
            )

        # Derive stage from Epicor data (uses VoidOrder, OrderHeld internally)
        stage = OrderStageLogic.get_stage_from_epicor(order_data)

        # Build properties (13 fields)
        properties = {
            # 1-2. Deal identification
            'dealname': f"Order #{order_data['OrderNum']}",
            'epicor_order_number': order_data['OrderNum'],

            # 13. Pipeline
            'pipeline': Pipelines.get_orders_pipeline_id(),

            # Stage (derived from deleted fields)
            'dealstage': stage,

            # 4-6. Dates
            'createdate': epicor_datetime_to_unix_ms(
                self.safe_get(order_data, 'OrderDate')
            ),
            'closedate': epicor_datetime_to_unix_ms(
                self.safe_get(order_data, 'RequestDate')
            ),
            'need_by_date': epicor_datetime_to_unix_ms(
                self.safe_get(order_data, 'NeedByDate')
            ),

            # 7-8. Amounts
            'amount': self.safe_get(order_data, 'OrderAmt'),
            'epicor_doc_amount': self.safe_get(order_data, 'DocOrderAmt'),

            # 9, 11. References
            'customer_po_number': self.safe_get(order_data, 'PONum'),
            'deal_currency_code': self.safe_get(order_data, 'CurrencyCode'),

            # 10. Boolean flags
            'epicor_open_order': self.safe_get(order_data, 'OpenOrder', True),

            # 12. System fields
            'epicor_order_sysrowid': guid_to_string(
                self.safe_get(order_data, 'SysRowID')
            ),

            # Sync metadata
            'epicor_last_sync_timestamp': int(datetime.now().timestamp() * 1000)
        }

        # Remove None values
        properties = {k: v for k, v in properties.items() if v is not None}

        logger.debug(
            f"Transformed order {order_data['OrderNum']} to stage '{stage}'"
        )

        return properties

    def get_customer_num(self, order_data: Dict[str, Any]) -> int:
        """Get customer number for association."""
        return order_data['CustNum']
