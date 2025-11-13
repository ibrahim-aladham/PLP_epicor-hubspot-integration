"""
Customer synchronization module.
Syncs Epicor Customers to HubSpot Companies.
"""

import logging
from typing import List, Dict, Any

from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.transformers.customer_transformer import CustomerTransformer
from src.utils.error_handler import ErrorTracker


logger = logging.getLogger(__name__)


class CustomerSync:
    """Handles customer to company synchronization."""

    def __init__(
        self,
        epicor_client: EpicorClient,
        hubspot_client: HubSpotClient
    ):
        """
        Initialize customer sync.

        Args:
            epicor_client: Epicor API client
            hubspot_client: HubSpot API client
        """
        self.epicor = epicor_client
        self.hubspot = hubspot_client
        self.transformer = CustomerTransformer()
        self.error_tracker = ErrorTracker()

    def sync_all_customers(self) -> Dict[str, Any]:
        """
        Sync all customers from Epicor to HubSpot.

        Returns:
            Sync summary with counts and errors
        """
        logger.info("=" * 60)
        logger.info("STARTING CUSTOMER SYNC")
        logger.info("=" * 60)

        # Fetch customers from Epicor
        try:
            customers = self.epicor.get_customers()
            logger.info(f"Fetched {len(customers)} customers from Epicor")
        except Exception as e:
            logger.error(f"Failed to fetch customers: {e}")
            return {
                'success': False,
                'error': str(e),
                'total': 0,
                'created': 0,
                'updated': 0,
                'errors': 0
            }

        # Sync each customer
        created_count = 0
        updated_count = 0

        for customer in customers:
            try:
                result = self.sync_customer(customer)
                if result == 'created':
                    created_count += 1
                elif result == 'updated':
                    updated_count += 1
            except Exception as e:
                cust_num = customer.get('CustNum', 'unknown')
                logger.error(f"Error syncing customer {cust_num}: {e}")
                self.error_tracker.add_error('customer', cust_num, str(e))

        # Summary
        summary = {
            'success': True,
            'total': len(customers),
            'created': created_count,
            'updated': updated_count,
            'errors': len(self.error_tracker.errors),
            'error_details': self.error_tracker.errors if self.error_tracker.has_errors() else None
        }

        logger.info("=" * 60)
        logger.info("CUSTOMER SYNC COMPLETE")
        logger.info(f"Total: {summary['total']}, Created: {created_count}, Updated: {updated_count}, Errors: {summary['errors']}")
        logger.info("=" * 60)

        return summary

    def sync_customer(self, customer_data: Dict[str, Any]) -> str:
        """
        Sync a single customer.

        Args:
            customer_data: Epicor customer record

        Returns:
            'created' or 'updated'
        """
        cust_num = customer_data['CustNum']
        cust_name = customer_data.get('Name', 'Unknown')

        logger.debug(f"Syncing customer {cust_num}: {cust_name}")

        # Transform data
        try:
            properties = self.transformer.transform(customer_data)
        except Exception as e:
            logger.error(f"Transformation error for customer {cust_num}: {e}")
            self.error_tracker.add_error('customer', cust_num, f"Transform error: {e}")
            return 'error'

        # Check if company exists in HubSpot
        existing_company = self.hubspot.get_company_by_property(
            'epicor_customer_number',
            cust_num
        )

        if existing_company:
            # Update existing company
            company_id = existing_company['id']
            result = self.hubspot.update_company(company_id, properties)
            if result:
                logger.info(f"✅ Updated company {cust_num}: {cust_name}")
                return 'updated'
            else:
                logger.error(f"❌ Failed to update company {cust_num}")
                self.error_tracker.add_error('customer', cust_num, "HubSpot update failed")
                return 'error'
        else:
            # Create new company
            result = self.hubspot.create_company(properties)
            if result:
                logger.info(f"✅ Created company {cust_num}: {cust_name}")
                return 'created'
            else:
                logger.error(f"❌ Failed to create company {cust_num}")
                self.error_tracker.add_error('customer', cust_num, "HubSpot create failed")
                return 'error'
