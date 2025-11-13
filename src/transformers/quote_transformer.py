"""
Quote to Deal transformer with APPROVED Pipeline Stage Logic.
Transforms Epicor Quote records to HubSpot Deal records.

APPROVED QUOTE PIPELINE STAGES (7 total):
1. Quote Created (20%) - Open
2. Technical Review (30%) - Open [HubSpot-only]
3. Quote Sent (40%) - Open
4. Follow Up (50%) - Open [HubSpot-only]
5. Quote Expired (0%) - Lost [Reversible terminal]
6. Closed Won (100%) - Won [Permanent terminal]
7. Closed Lost (0%) - Lost [Permanent terminal]

CRITICAL STAGE SYNC RULES:
1. Forward Movement Only - Never move backward
2. Terminal Stage Override - Epicor terminals always update
3. HubSpot-Only Stages Protected - Never overwrite Technical Review/Follow Up
4. Reversible Terminal - Quote Expired can reactivate
5. Permanent Terminals - Closed Won/Lost cannot reopen
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from src.transformers.base_transformer import BaseTransformer
from src.utils.date_utils import epicor_datetime_to_unix_ms, guid_to_string
from src.config import settings, Pipelines


logger = logging.getLogger(__name__)


class QuoteStageLogic:
    """
    Approved Quote Pipeline Stage Logic.
    Client approved on November 13, 2025.
    """

    STAGE_ORDER = {
        'quote_created': 1,
        'technical_review': 2,      # HubSpot-only
        'quote_sent': 3,
        'follow_up': 4,              # HubSpot-only
        'quote_expired': 5,
        'closedwon': 6,
        'closedlost': 7
    }

    TERMINAL_STAGES = {'closedwon', 'closedlost', 'quote_expired'}
    PERMANENT_TERMINAL_STAGES = {'closedwon', 'closedlost'}
    REVERSIBLE_TERMINAL_STAGES = {'quote_expired'}
    HUBSPOT_ONLY_STAGES = {'technical_review', 'follow_up'}

    @staticmethod
    def get_stage_from_epicor(quote_data: Dict[str, Any]) -> str:
        """
        Derive HubSpot stage from Epicor boolean flags.

        PRIORITY ORDER (evaluated in exact order):
        1. Ordered=true ’ closedwon
        2. Expired=true ’ quote_expired
        3. QuoteClosed=true AND Ordered=false ’ closedlost
        4. Quoted=true ’ quote_sent
        5. Default ’ quote_created

        Args:
            quote_data: Epicor quote record

        Returns:
            HubSpot stage internal name
        """
        # Priority 1: Converted to order
        if quote_data.get('Ordered'):
            return 'closedwon'

        # Priority 2: Expired
        elif quote_data.get('Expired'):
            return 'quote_expired'

        # Priority 3: Closed without order
        elif quote_data.get('QuoteClosed') and not quote_data.get('Ordered'):
            return 'closedlost'

        # Priority 4: Sent to customer
        elif quote_data.get('Quoted'):
            return 'quote_sent'

        # Priority 5: Initial state
        else:
            return 'quote_created'

    @staticmethod
    def should_update_stage(
        current_hubspot_stage: Optional[str],
        new_epicor_stage: str
    ) -> bool:
        """
        Determine if HubSpot stage should be updated.

        RULES:
        1. New deal ’ always set stage
        2. Terminal stages from Epicor ’ always update
        3. Permanent terminals (Won/Lost) ’ cannot reopen
        4. Reversible terminal (Expired) ’ can reactivate
        5. Forward only ’ never move backward

        Args:
            current_hubspot_stage: Current stage in HubSpot (None if new deal)
            new_epicor_stage: New stage derived from Epicor

        Returns:
            True if stage should be updated
        """
        # Rule 1: New deal - always set stage
        if current_hubspot_stage is None:
            logger.debug("New deal - setting initial stage")
            return True

        current = current_hubspot_stage.lower().strip()
        new = new_epicor_stage.lower().strip()

        # Rule 2: Terminal stages from Epicor always win
        if new in QuoteStageLogic.TERMINAL_STAGES:
            logger.debug(f"Terminal stage override: '{new}' always updates")
            return True

        # Rule 3: Can't reopen permanent terminals
        if current in QuoteStageLogic.PERMANENT_TERMINAL_STAGES:
            logger.debug(
                f"Blocking: Cannot reopen permanent terminal '{current}'"
            )
            return False

        # Rule 4: Can reactivate reversible terminals (Expired)
        if current in QuoteStageLogic.REVERSIBLE_TERMINAL_STAGES:
            logger.info(
                f"Reactivating quote from reversible terminal '{current}' ’ '{new}'"
            )
            return True

        # Rule 5: Only move forward, never backward
        current_position = QuoteStageLogic.STAGE_ORDER.get(current, 0)
        new_position = QuoteStageLogic.STAGE_ORDER.get(new, 0)

        if new_position > current_position:
            logger.debug(
                f"Forward progression: '{current}' (pos {current_position}) "
                f"’ '{new}' (pos {new_position})"
            )
            return True
        else:
            logger.debug(
                f"Blocking backward movement: '{current}' (pos {current_position}) "
                f" '{new}' (pos {new_position})"
            )
            return False


class QuoteTransformer(BaseTransformer):
    """Transform Epicor Quote to HubSpot Deal with approved stage logic."""

    REQUIRED_FIELDS = ['QuoteNum', 'CustNum']

    def transform(
        self,
        quote_data: Dict[str, Any],
        current_hubspot_stage: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transform Epicor quote to HubSpot deal properties.

        MAPPING (21 ACTIVE FIELDS):
        1. QuoteNum ’ dealname
        2. QuoteNum ’ epicor_quote_number (PRIMARY)
        3. CustNum ’ (association)
        4. EntryDate ’ createdate
        5. DueDate ’ closedate
        6. ExpirationDate ’ quote_expiration_date
        7. DateQuoted ’ quote_sent_date
        8. QuoteAmt ’ amount
        9. DocQuoteAmt ’ epicor_doc_amount
        10. PONum ’ customer_po_number
        11. Boolean flags ’ dealstage (using approved logic)
        12. Quoted ’ epicor_quoted
        13. QuoteClosed ’ epicor_closed
        14. Ordered ’ epicor_converted_to_order
        15. Expired ’ epicor_expired
        16. DiscountPercent ’ discount_percentage
        17. CurrencyCode ’ deal_currency_code
        18. SysRowID ’ epicor_quote_sysrowid
        19. SalesRepCode ’ epicor_sales_rep_code
        20. SalesRepCode ’ hubspot_owner_id (if mapped)
        21. (hardcoded) ’ pipeline

        Args:
            quote_data: Epicor quote record
            current_hubspot_stage: Current stage in HubSpot (None if new)

        Returns:
            HubSpot deal properties

        Raises:
            ValueError: If required fields missing
        """
        # Validate required fields
        if not self.validate_required_fields(quote_data, self.REQUIRED_FIELDS):
            raise ValueError(
                f"Missing required fields in quote {quote_data.get('QuoteNum')}"
            )

        # Derive stage from Epicor data
        new_stage = QuoteStageLogic.get_stage_from_epicor(quote_data)

        # Check if stage should be updated
        should_update = QuoteStageLogic.should_update_stage(
            current_hubspot_stage,
            new_stage
        )

        # Get sales rep mapping
        sales_rep_code = self.safe_get(quote_data, 'SalesRepCode')
        hubspot_owner = settings.get_hubspot_owner(sales_rep_code)

        # Build properties (21 fields)
        properties = {
            # 1-2. Deal identification
            'dealname': f"Quote #{quote_data['QuoteNum']}",
            'epicor_quote_number': quote_data['QuoteNum'],

            # 21. Pipeline
            'pipeline': Pipelines.get_quotes_pipeline_id(),

            # 4-7. Dates
            'createdate': epicor_datetime_to_unix_ms(
                self.safe_get(quote_data, 'EntryDate')
            ),
            'closedate': epicor_datetime_to_unix_ms(
                self.safe_get(quote_data, 'DueDate')
            ),
            'quote_expiration_date': epicor_datetime_to_unix_ms(
                self.safe_get(quote_data, 'ExpirationDate')
            ),
            'quote_sent_date': epicor_datetime_to_unix_ms(
                self.safe_get(quote_data, 'DateQuoted')
            ),

            # 8-9, 16. Amounts
            'amount': self.safe_get(quote_data, 'QuoteAmt'),
            'epicor_doc_amount': self.safe_get(quote_data, 'DocQuoteAmt'),
            'discount_percentage': self.safe_get(quote_data, 'DiscountPercent'),

            # 10, 17. References
            'customer_po_number': self.safe_get(quote_data, 'PONum'),
            'deal_currency_code': self.safe_get(quote_data, 'CurrencyCode'),

            # 12-15. Boolean flags
            'epicor_quoted': self.safe_get(quote_data, 'Quoted', False),
            'epicor_closed': self.safe_get(quote_data, 'QuoteClosed', False),
            'epicor_converted_to_order': self.safe_get(quote_data, 'Ordered', False),
            'epicor_expired': self.safe_get(quote_data, 'Expired', False),

            # 19. Sales rep
            'epicor_sales_rep_code': sales_rep_code,

            # 18. System fields
            'epicor_quote_sysrowid': guid_to_string(
                self.safe_get(quote_data, 'SysRowID')
            ),

            # Sync metadata
            'epicor_last_sync_stage': new_stage,
            'epicor_last_sync_timestamp': int(datetime.now().timestamp() * 1000)
        }

        # 11. Add stage if should update
        if should_update:
            properties['dealstage'] = new_stage
            action = 'set to' if current_hubspot_stage is None else 'updated to'
            logger.info(f"Quote {quote_data['QuoteNum']}: Stage {action} '{new_stage}'")
        else:
            logger.info(
                f"Quote {quote_data['QuoteNum']}: "
                f"Stage update blocked (keeping '{current_hubspot_stage}')"
            )

        # 20. Add owner if mapped
        if hubspot_owner:
            properties['hubspot_owner_id'] = hubspot_owner
            logger.debug(f"Mapped rep '{sales_rep_code}' to owner '{hubspot_owner}'")
        elif sales_rep_code:
            logger.warning(
                f"Sales rep '{sales_rep_code}' not mapped. Deal will be unassigned."
            )

        # Remove None values
        properties = {k: v for k, v in properties.items() if v is not None}

        logger.debug(f"Transformed quote {quote_data['QuoteNum']}")

        return properties

    def get_customer_num(self, quote_data: Dict[str, Any]) -> int:
        """Get customer number for association."""
        return quote_data['CustNum']
