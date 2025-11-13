"""
Customer to Company transformer.
Transforms Epicor Customer records to HubSpot Company records.

MAPPING (14 ACTIVE FIELDS):
1. CustNum ’ epicor_customer_number (PRIMARY MATCHING)
2. CustID ’ epicor_customer_code
3. Name ’ name (required)
4-9. Address fields ’ address, address2, city, state, zip, country
10. PhoneNum ’ phone (E.164 format)
11. FaxNum ’ fax_number
12. EmailAddress ’ epicor_email
13. CurrencyCode ’ currency_code
14. SysRowID ’ epicor_sysrowid (GUID’string)

DELETED (DO NOT SYNC):
- TermsCode
- CreditHold
- TerritoryID
"""

import logging
from typing import Dict, Any

from src.transformers.base_transformer import BaseTransformer
from src.utils.date_utils import guid_to_string, format_phone_e164


logger = logging.getLogger(__name__)


class CustomerTransformer(BaseTransformer):
    """Transform Epicor Customer to HubSpot Company."""

    REQUIRED_FIELDS = ['CustNum', 'Name']

    def transform(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Epicor customer to HubSpot company properties.

        Args:
            customer_data: Epicor customer record

        Returns:
            HubSpot company properties

        Raises:
            ValueError: If required fields missing
        """
        # Validate required fields
        if not self.validate_required_fields(customer_data, self.REQUIRED_FIELDS):
            raise ValueError(
                f"Missing required fields in customer {customer_data.get('CustNum')}"
            )

        # Transform data (14 fields)
        properties = {
            # 1. Primary matching field
            'epicor_customer_number': customer_data['CustNum'],

            # 2. Business ID
            'epicor_customer_code': self.safe_get(customer_data, 'CustID'),

            # 3. Company name (required)
            'name': customer_data['Name'],

            # 4-9. Address fields
            'address': self.safe_get(customer_data, 'Address1'),
            'address2': self.safe_get(customer_data, 'Address2'),
            'city': self.safe_get(customer_data, 'City'),
            'state': self.safe_get(customer_data, 'State'),
            'zip': self.safe_get(customer_data, 'Zip'),
            'country': self.safe_get(customer_data, 'Country'),

            # 10-12. Contact fields
            'phone': format_phone_e164(self.safe_get(customer_data, 'PhoneNum')),
            'fax_number': self.safe_get(customer_data, 'FaxNum'),
            'epicor_email': self.safe_get(customer_data, 'EmailAddress'),

            # 13. Business fields
            'currency_code': self.safe_get(customer_data, 'CurrencyCode'),

            # 14. System fields
            'epicor_sysrowid': guid_to_string(self.safe_get(customer_data, 'SysRowID'))
        }

        # Remove None values
        properties = {k: v for k, v in properties.items() if v is not None}

        logger.debug(
            f"Transformed customer {customer_data['CustNum']}: {customer_data['Name']}"
        )

        return properties

    def get_customer_num(self, customer_data: Dict[str, Any]) -> int:
        """Get customer number (for reference)."""
        return customer_data['CustNum']
