"""
HubSpot REST API client.

This client provides a generic interface to interact with HubSpot CRM API v3/v4.
It handles authentication (Bearer token), rate limiting, retry logic, and error handling.
"""

import logging
import time
from typing import Dict, List, Optional, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..utils.error_handler import HubSpotAPIError, log_errors


class HubSpotClient:
    """
    Generic client for HubSpot REST API v3/v4.

    Handles:
    - Authentication: Bearer token (Private App Access Token)
    - Rate limiting: Respects HubSpot's rate limits (100 req/10 sec)
    - Retry logic: Automatic retries for transient failures
    - Error handling: Comprehensive error logging and exceptions
    - CRM Objects: Companies, Contacts, Deals, Products, Line Items
    - Associations: Creating relationships between objects
    """

    def __init__(self, api_key: str, rate_limit_delay: float = 0.11):
        """
        Initialize HubSpot API client.

        Args:
            api_key: HubSpot Private App Access Token
            rate_limit_delay: Delay between requests in seconds (default: 0.11s = ~90 req/10sec)
        """
        self.api_key = api_key
        self.base_url = "https://api.hubapi.com"
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
        self.logger = logging.getLogger(__name__)

        # Create session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PATCH", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set headers
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

        self.logger.info("HubSpot client initialized")

    def _rate_limit(self) -> None:
        """
        Implement rate limiting to avoid hitting HubSpot API limits.

        HubSpot limits: 100 requests per 10 seconds for most endpoints.
        """
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last_request
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    @log_errors
    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        """
        Make HTTP request with rate limiting and error handling.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            url: Full URL
            **kwargs: Additional arguments to pass to requests

        Returns:
            Response object

        Raises:
            HubSpotAPIError: If request fails
        """
        self._rate_limit()

        try:
            response = self.session.request(method, url, timeout=30, **kwargs)

            if not response.ok:
                error_detail = ""
                try:
                    error_detail = response.json()
                except:
                    error_detail = response.text

                raise HubSpotAPIError(
                    f"{method} {url} failed",
                    status_code=response.status_code,
                    response=str(error_detail)
                )

            return response

        except requests.exceptions.RequestException as e:
            raise HubSpotAPIError(f"Request failed: {str(e)}")
    
    # ========================================================================
    # Generic Object Methods
    # ========================================================================

    def search_objects(
        self,
        object_type: str,
        filter_groups: List[Dict],
        properties: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Generic method to search for HubSpot objects.

        Args:
            object_type: Type of object (companies, contacts, deals, products, line_items)
            filter_groups: HubSpot filter groups for search
            properties: List of properties to return
            limit: Maximum number of results per request

        Returns:
            List of matching objects

        Example:
            >>> client.search_objects(
            ...     "companies",
            ...     [{"filters": [{"propertyName": "name", "operator": "EQ", "value": "ACME"}]}],
            ...     properties=["name", "city"]
            ... )
        """
        url = f"{self.base_url}/crm/v3/objects/{object_type}/search"
        payload = {
            "filterGroups": filter_groups,
            "limit": limit
        }

        if properties:
            payload["properties"] = properties

        response = self._make_request("POST", url, json=payload)
        return response.json().get('results', [])

    def create_object(
        self,
        object_type: str,
        properties: Dict[str, Any]
    ) -> Dict:
        """
        Generic method to create a HubSpot object.

        Args:
            object_type: Type of object (companies, contacts, deals, products, line_items)
            properties: Object properties

        Returns:
            Created object with ID

        Example:
            >>> client.create_object("companies", {"name": "ACME Corp", "city": "Toronto"})
        """
        url = f"{self.base_url}/crm/v3/objects/{object_type}"
        payload = {"properties": properties}

        response = self._make_request("POST", url, json=payload)
        result = response.json()

        self.logger.debug(f"Created {object_type} with ID {result.get('id')}")
        return result

    def update_object(
        self,
        object_type: str,
        object_id: str,
        properties: Dict[str, Any]
    ) -> Dict:
        """
        Generic method to update a HubSpot object.

        Args:
            object_type: Type of object (companies, contacts, deals, products, line_items)
            object_id: HubSpot object ID
            properties: Properties to update

        Returns:
            Updated object

        Example:
            >>> client.update_object("companies", "123456", {"city": "Montreal"})
        """
        url = f"{self.base_url}/crm/v3/objects/{object_type}/{object_id}"
        payload = {"properties": properties}

        response = self._make_request("PATCH", url, json=payload)
        result = response.json()

        self.logger.debug(f"Updated {object_type} ID {object_id}")
        return result

    def delete_object(
        self,
        object_type: str,
        object_id: str
    ) -> bool:
        """
        Generic method to delete a HubSpot object.

        Args:
            object_type: Type of object
            object_id: HubSpot object ID

        Returns:
            True if successful

        Example:
            >>> client.delete_object("companies", "123456")
        """
        url = f"{self.base_url}/crm/v3/objects/{object_type}/{object_id}"

        self._make_request("DELETE", url)
        self.logger.debug(f"Deleted {object_type} ID {object_id}")
        return True

    # ========================================================================
    # Associations
    # ========================================================================

    def create_association(
        self,
        from_object: str,
        from_id: str,
        to_object: str,
        to_id: str,
        association_type_id: int
    ) -> bool:
        """
        Create association between two HubSpot objects.

        Args:
            from_object: Source object type (e.g., "contacts")
            from_id: Source object ID
            to_object: Target object type (e.g., "companies")
            to_id: Target object ID
            association_type_id: HubSpot association type ID

        Returns:
            True if successful

        Common association type IDs:
            - contact_to_company: 1
            - deal_to_company: 5
            - deal_to_contact: 3
            - line_item_to_deal: 20

        Example:
            >>> client.create_association("contacts", "123", "companies", "456", 1)
        """
        url = (
            f"{self.base_url}/crm/v4/objects/{from_object}/{from_id}/"
            f"associations/{to_object}/{to_id}"
        )

        payload = [{
            "associationCategory": "HUBSPOT_DEFINED",
            "associationTypeId": association_type_id
        }]

        self._make_request("PUT", url, json=payload)
        self.logger.debug(
            f"Created association: {from_object}/{from_id} -> {to_object}/{to_id}"
        )
        return True

    # ========================================================================
    # Convenience Methods for Common Operations
    # ========================================================================

    def get_deal_by_property(
        self,
        property_name: str,
        value: Any
    ) -> Optional[Dict]:
        """
        Find a deal by a specific property value.

        Args:
            property_name: Property to search by (e.g., 'epicor_quote_number')
            value: Value to match

        Returns:
            Deal object if found, None otherwise
        """
        results = self.search_objects(
            "deals",
            [{"filters": [{"propertyName": property_name, "operator": "EQ", "value": str(value)}]}],
            properties=["dealname", "dealstage", "pipeline", "amount"]
        )
        return results[0] if results else None

    def get_company_by_property(
        self,
        property_name: str,
        value: Any
    ) -> Optional[Dict]:
        """
        Find a company by a specific property value.

        Args:
            property_name: Property to search by (e.g., 'epicor_customer_number')
            value: Value to match

        Returns:
            Company object if found, None otherwise
        """
        results = self.search_objects(
            "companies",
            [{"filters": [{"propertyName": property_name, "operator": "EQ", "value": str(value)}]}]
        )
        return results[0] if results else None

    def create_deal(self, properties: Dict[str, Any]) -> Optional[Dict]:
        """Create a deal. Convenience wrapper around create_object."""
        return self.create_object("deals", properties)

    def update_deal(self, deal_id: str, properties: Dict[str, Any]) -> Optional[Dict]:
        """Update a deal. Convenience wrapper around update_object."""
        return self.update_object("deals", deal_id, properties)

    def create_company(self, properties: Dict[str, Any]) -> Optional[Dict]:
        """Create a company. Convenience wrapper around create_object."""
        return self.create_object("companies", properties)

    def update_company(self, company_id: str, properties: Dict[str, Any]) -> Optional[Dict]:
        """Update a company. Convenience wrapper around update_object."""
        return self.update_object("companies", company_id, properties)

    def associate_deal_to_company(self, deal_id: str, company_id: str) -> bool:
        """
        Associate a deal with a company.

        Args:
            deal_id: HubSpot deal ID
            company_id: HubSpot company ID

        Returns:
            True if successful
        """
        return self.create_association(
            from_object="deals",
            from_id=deal_id,
            to_object="companies",
            to_id=company_id,
            association_type_id=5  # deal_to_company
        )

    def associate_deal_to_deal(self, from_deal_id: str, to_deal_id: str) -> bool:
        """
        Associate two deals together (e.g., Quote deal to Order deal).

        Args:
            from_deal_id: Source deal ID (e.g., quote deal)
            to_deal_id: Target deal ID (e.g., order deal)

        Returns:
            True if successful
        """
        return self.create_association(
            from_object="deals",
            from_id=from_deal_id,
            to_object="deals",
            to_id=to_deal_id,
            association_type_id=6  # deal_to_deal
        )

    # ========================================================================
    # Line Item Methods
    # ========================================================================

    def create_line_item(self, properties: Dict[str, Any]) -> Optional[Dict]:
        """Create a line item. Convenience wrapper around create_object."""
        return self.create_object("line_items", properties)

    def associate_line_item_to_deal(self, line_item_id: str, deal_id: str) -> bool:
        """
        Associate a line item with a deal.

        Args:
            line_item_id: HubSpot line item ID
            deal_id: HubSpot deal ID

        Returns:
            True if successful
        """
        return self.create_association(
            from_object="line_items",
            from_id=line_item_id,
            to_object="deals",
            to_id=deal_id,
            association_type_id=20  # line_item_to_deal
        )

    def get_line_item_by_epicor_id(self, epicor_line_item_id: str) -> Optional[Dict]:
        """
        Find a line item by its Epicor unique identifier.

        Args:
            epicor_line_item_id: Unique ID (e.g., 'Q1234-1' or 'O5678-2')

        Returns:
            Line item object if found, None otherwise
        """
        results = self.search_objects(
            "line_items",
            [{"filters": [{"propertyName": "epicor_line_item_id", "operator": "EQ", "value": epicor_line_item_id}]}],
            properties=["name", "sku", "quantity", "price", "amount", "epicor_line_item_id"]
        )
        return results[0] if results else None

    def update_line_item(self, line_item_id: str, properties: Dict[str, Any]) -> Optional[Dict]:
        """Update a line item. Convenience wrapper around update_object."""
        return self.update_object("line_items", line_item_id, properties)

    # ========================================================================
    # Product Methods
    # ========================================================================

    def get_product_by_sku(self, sku: str) -> Optional[Dict]:
        """
        Find a product by SKU.

        Args:
            sku: Product SKU (hs_sku in HubSpot)

        Returns:
            Product object if found, None otherwise
        """
        results = self.search_objects(
            "products",
            [{"filters": [{"propertyName": "hs_sku", "operator": "EQ", "value": sku}]}]
        )
        return results[0] if results else None

    def create_product(self, properties: Dict[str, Any]) -> Optional[Dict]:
        """Create a product. Convenience wrapper around create_object."""
        return self.create_object("products", properties)

    def update_product(self, product_id: str, properties: Dict[str, Any]) -> Optional[Dict]:
        """Update a product. Convenience wrapper around update_object."""
        return self.update_object("products", product_id, properties)

    # ========================================================================
    # Connection Test
    # ========================================================================

    def test_connection(self) -> bool:
        """
        Test API connection by fetching a single company.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            url = f"{self.base_url}/crm/v3/objects/companies?limit=1"
            self._make_request("GET", url)
            self.logger.info("✓ HubSpot connection successful")
            return True
        except Exception as e:
            self.logger.error(f"✗ HubSpot connection failed: {e}")
            return False