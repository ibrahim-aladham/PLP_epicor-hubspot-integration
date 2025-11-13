"""
Test customer sync module.
"""

import pytest
from unittest.mock import Mock, MagicMock
from src.sync.customer_sync import CustomerSync


class TestCustomerSync:
    """Test customer synchronization."""

    @pytest.fixture
    def epicor_client(self):
        """Mock Epicor client."""
        client = Mock()
        client.get_customers = Mock(return_value=[
            {
                'CustNum': 12345,
                'Name': 'Test Company 1',
                'City': 'Toronto'
            },
            {
                'CustNum': 67890,
                'Name': 'Test Company 2',
                'City': 'Vancouver'
            }
        ])
        return client

    @pytest.fixture
    def hubspot_client(self):
        """Mock HubSpot client."""
        client = Mock()
        client.get_company_by_property = Mock(return_value=None)
        client.create_company = Mock(return_value={'id': '123'})
        client.update_company = Mock(return_value={'id': '123'})
        return client

    @pytest.fixture
    def customer_sync(self, epicor_client, hubspot_client):
        """Create customer sync instance with mocked clients."""
        return CustomerSync(epicor_client, hubspot_client)

    def test_sync_all_customers_creates_new(self, customer_sync, epicor_client, hubspot_client):
        """Test syncing customers that don't exist in HubSpot."""
        result = customer_sync.sync_all_customers()

        # Verify it fetched customers from Epicor
        epicor_client.get_customers.assert_called_once()

        # Verify summary
        assert result['success'] == True
        assert result['total'] == 2
        assert result['created'] == 2
        assert result['updated'] == 0

    def test_sync_all_customers_updates_existing(self, customer_sync, epicor_client, hubspot_client):
        """Test syncing customers that exist in HubSpot."""
        # Mock existing companies
        hubspot_client.get_company_by_property = Mock(return_value={'id': '123'})

        result = customer_sync.sync_all_customers()

        # Verify summary
        assert result['success'] == True
        assert result['total'] == 2
        assert result['created'] == 0
        assert result['updated'] == 2

    def test_sync_all_customers_handles_error(self, customer_sync, epicor_client):
        """Test error handling when fetch fails."""
        epicor_client.get_customers = Mock(side_effect=Exception("API Error"))

        result = customer_sync.sync_all_customers()

        # Verify error response
        assert result['success'] == False
        assert 'API Error' in result['error']

    def test_sync_customer_creates_new(self, customer_sync, hubspot_client):
        """Test creating a new customer."""
        customer_data = {
            'CustNum': 12345,
            'Name': 'New Company'
        }

        result = customer_sync.sync_customer(customer_data)

        assert result == 'created'
        hubspot_client.create_company.assert_called_once()

    def test_sync_customer_updates_existing(self, customer_sync, hubspot_client):
        """Test updating an existing customer."""
        customer_data = {
            'CustNum': 12345,
            'Name': 'Existing Company'
        }

        # Mock existing company
        hubspot_client.get_company_by_property = Mock(return_value={'id': '123'})

        result = customer_sync.sync_customer(customer_data)

        assert result == 'updated'
        hubspot_client.update_company.assert_called_once()
