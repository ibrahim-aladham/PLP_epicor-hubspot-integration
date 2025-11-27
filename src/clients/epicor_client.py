"""
Epicor REST API client for OData v4.

This client provides a generic interface to interact with Epicor ERP's REST API v2,
which uses OData v4. It handles authentication (Basic Auth + API Key), pagination,
retry logic, and error handling.
"""

import base64
import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..utils.error_handler import EpicorAPIError, retry, log_errors


class EpicorClient:
    """
    Generic client for Epicor REST API v2 (OData v4).

    Handles:
    - Authentication: Basic Auth + x-api-key header (BOTH required)
    - OData query parameters: $expand, $filter, $select, $top, $skip, $orderby
    - Pagination: Automatic handling of large result sets
    - Retry logic: Automatic retries for transient failures
    - Error handling: Comprehensive error logging and exceptions
    """

    def __init__(
        self,
        base_url: str,
        company: str,
        username: str,
        password: str,
        api_key: str,
        batch_size: int = 100
    ):
        """
        Initialize Epicor API client.

        Args:
            base_url: Epicor base URL (e.g., https://plpc-apperp.preformed.ca/ERP11PROD)
            company: Company ID (e.g., PLPC)
            username: API username
            password: API password
            api_key: API key for x-api-key header
            batch_size: Default batch size for pagination
        """
        self.base_url = base_url.rstrip('/')
        self.company = company
        self.api_key = api_key
        self.batch_size = batch_size
        self.logger = logging.getLogger(__name__)

        # Create session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PATCH", "PUT"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Disable SSL verification for self-signed certificates (Epicor server)
        self.session.verify = False
        # Suppress SSL warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Set authentication headers (BOTH Basic Auth AND API Key required)
        credentials = f"{username}:{password}"
        encoded_creds = base64.b64encode(credentials.encode()).decode()
        self.session.headers.update({
            "Authorization": f"Basic {encoded_creds}",
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

        self.logger.info(f"Epicor client initialized for company {company}")

    def _build_url(
        self,
        service: str,
        entity_set: str,
        params: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Build OData URL with query parameters.

        Args:
            service: Service name (e.g., "Erp.BO.CustomerSvc")
            entity_set: Entity set name (e.g., "Customers")
            params: Optional OData query parameters

        Returns:
            Complete URL with query string

        Example:
            >>> client._build_url("Erp.BO.CustomerSvc", "Customers", {"$top": "10"})
            'https://...api/v2/odata/PLPC/Erp.BO.CustomerSvc/Customers?$top=10'
        """
        url = f"{self.base_url}/api/v2/odata/{self.company}/{service}/{entity_set}"

        if params:
            query_string = urlencode(params, safe='$,:')
            url = f"{url}?{query_string}"

        return url

    @log_errors
    def _get_paged(
        self,
        url: str,
        batch_size: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch all pages of data from an OData endpoint.

        Handles OData pagination using $top and $skip parameters, and follows
        @odata.nextLink if provided.

        Args:
            url: Base URL (may already contain query parameters)
            batch_size: Number of records per page (default: self.batch_size)

        Returns:
            List of all records across all pages

        Raises:
            EpicorAPIError: If API request fails
        """
        if batch_size is None:
            batch_size = self.batch_size

        all_records = []
        skip = 0
        page = 1

        while True:
            # Add pagination parameters
            separator = '&' if '?' in url else '?'
            paged_url = f"{url}{separator}$top={batch_size}&$skip={skip}"

            self.logger.debug(f"Fetching page {page}: {paged_url}")

            try:
                response = self.session.get(paged_url, timeout=30)

                if not response.ok:
                    raise EpicorAPIError(
                        f"Request failed: {response.text}",
                        status_code=response.status_code,
                        response=response.text
                    )

                data = response.json()
                records = data.get('value', [])

                if not records:
                    self.logger.info(f"No more records. Total fetched: {len(all_records)}")
                    break

                all_records.extend(records)
                skip += len(records)
                page += 1

                self.logger.info(
                    f"Page {page-1}: Fetched {len(records)} records, "
                    f"total: {len(all_records)}"
                )

                # Check if there's a next link
                if '@odata.nextLink' not in data:
                    break

            except requests.exceptions.RequestException as e:
                raise EpicorAPIError(f"Request failed: {str(e)}")

        return all_records

    def get_entity(
        self,
        service: str,
        entity_set: str,
        expand: Optional[str] = None,
        filter_expr: Optional[str] = None,
        select: Optional[str] = None,
        orderby: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Generic method to fetch entities from any Epicor service.

        Args:
            service: Service name (e.g., "Erp.BO.CustomerSvc")
            entity_set: Entity set name (e.g., "Customers")
            expand: OData $expand parameter (e.g., "QuoteDtls")
            filter_expr: OData $filter parameter (e.g., "CustNum gt 100")
            select: OData $select parameter (e.g., "CustNum,Name")
            orderby: OData $orderby parameter (e.g., "Name desc")
            limit: Maximum number of records to return

        Returns:
            List of entity records

        Example:
            >>> client.get_entity(
            ...     "Erp.BO.QuoteSvc",
            ...     "Quotes",
            ...     expand="QuoteDtls",
            ...     filter_expr="QuoteNum gt 1000"
            ... )
        """
        params = {}

        if expand:
            params['$expand'] = expand
        if filter_expr:
            params['$filter'] = filter_expr
        if select:
            params['$select'] = select
        if orderby:
            params['$orderby'] = orderby
        # Note: Don't add $top here - _get_paged handles pagination with $top/$skip

        url = self._build_url(service, entity_set, params)

        if limit:
            # If limit is specified, don't paginate beyond it
            return self._get_paged(url, batch_size=limit)
        else:
            return self._get_paged(url)

    # ========================================================================
    # Convenience Methods for Common Entities
    # ========================================================================

    def get_customers(
        self,
        filter_condition: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch customers from Epicor.

        Args:
            filter_condition: Optional OData filter expression

        Returns:
            List of customer records
        """
        return self.get_entity(
            service="Erp.BO.CustomerSvc",
            entity_set="Customers",
            filter_expr=filter_condition
        )

    def get_quotes(
        self,
        expand_line_items: bool = False,
        filter_condition: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch quotes from Epicor.

        Args:
            expand_line_items: Whether to include quote line items
            filter_condition: Optional OData filter expression

        Returns:
            List of quote records
        """
        expand = "QuoteDtls" if expand_line_items else None
        return self.get_entity(
            service="Erp.BO.QuoteSvc",
            entity_set="Quotes",
            expand=expand,
            filter_expr=filter_condition
        )

    def get_orders(
        self,
        expand_line_items: bool = False,
        filter_condition: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch sales orders from Epicor.

        Args:
            expand_line_items: Whether to include order line items
            filter_condition: Optional OData filter expression

        Returns:
            List of order records
        """
        expand = "OrderDtls" if expand_line_items else None
        return self.get_entity(
            service="Erp.BO.SalesOrderSvc",
            entity_set="SalesOrders",
            expand=expand,
            filter_expr=filter_condition
        )

    # ========================================================================
    # Connection Test
    # ========================================================================

    def test_connection(self) -> bool:
        """
        Test API connection by fetching one customer record.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Test by fetching 1 customer - this validates auth and connectivity
            url = f"{self.base_url}/api/v2/odata/{self.company}/Erp.BO.CustomerSvc/Customers?$top=1"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            self.logger.info("✓ Epicor connection successful")
            return True
        except Exception as e:
            self.logger.error(f"✗ Epicor connection failed: {e}")
            return False