"""
Test quote sync module with stage logic.
"""

import pytest
from unittest.mock import Mock, MagicMock
from src.sync.quote_sync import QuoteSync


class TestQuoteSync:
    """Test quote synchronization with stage logic."""

    @pytest.fixture
    def epicor_client(self):
        """Mock Epicor client."""
        client = Mock()
        client.get_quotes = Mock(return_value=[
            {
                'QuoteNum': 1001,
                'CustNum': 12345,
                'QuoteAmt': 5000.00,
                'Quoted': True,
                'QuoteClosed': False,
                'Ordered': False,
                'Expired': False
            },
            {
                'QuoteNum': 1002,
                'CustNum': 12345,
                'QuoteAmt': 10000.00,
                'Quoted': False,
                'QuoteClosed': False,
                'Ordered': False,
                'Expired': False
            }
        ])
        return client

    @pytest.fixture
    def hubspot_client(self):
        """Mock HubSpot client."""
        client = Mock()
        client.get_deal_by_property = Mock(return_value=None)
        client.get_company_by_property = Mock(return_value={'id': 'company-123'})
        client.create_deal = Mock(return_value={'id': 'deal-123'})
        client.update_deal = Mock(return_value={'id': 'deal-123'})
        client.associate_deal_to_company = Mock(return_value=True)
        return client

    @pytest.fixture
    def quote_sync(self, epicor_client, hubspot_client):
        """Create quote sync instance with mocked clients."""
        return QuoteSync(epicor_client, hubspot_client)

    def test_sync_all_quotes_creates_new(self, quote_sync, epicor_client, hubspot_client):
        """Test syncing quotes that don't exist in HubSpot."""
        result = quote_sync.sync_all_quotes()

        # Verify it fetched quotes from Epicor
        epicor_client.get_quotes.assert_called_once()

        # Verify summary
        assert result['success'] == True
        assert result['total'] == 2
        assert result['created'] == 2
        assert result['updated'] == 0

    def test_sync_all_quotes_updates_existing(self, quote_sync, epicor_client, hubspot_client):
        """Test syncing quotes that exist in HubSpot."""
        # Mock existing deals
        hubspot_client.get_deal_by_property = Mock(return_value={
            'id': 'deal-123',
            'properties': {'dealstage': 'quote_created'}
        })

        result = quote_sync.sync_all_quotes()

        # Verify summary
        assert result['success'] == True
        assert result['total'] == 2
        assert result['created'] == 0
        assert result['updated'] == 2

    def test_sync_quote_with_stage_logic(self, quote_sync, hubspot_client):
        """Test that stage logic is applied during sync."""
        quote_data = {
            'QuoteNum': 1001,
            'CustNum': 12345,
            'QuoteAmt': 5000.00,
            'Quoted': True,
            'QuoteClosed': False,
            'Ordered': False,
            'Expired': False
        }

        # Mock existing deal at quote_created stage
        hubspot_client.get_deal_by_property = Mock(return_value={
            'id': 'deal-123',
            'properties': {'dealstage': 'quote_created'}
        })

        result = quote_sync.sync_quote(quote_data)

        # Verify it was updated (stage should move forward)
        assert result == 'updated'
        hubspot_client.update_deal.assert_called_once()

    def test_sync_quote_skips_if_company_missing(self, quote_sync, hubspot_client):
        """Test that quote is skipped if company doesn't exist."""
        quote_data = {
            'QuoteNum': 1001,
            'CustNum': 99999,  # Non-existent customer
            'QuoteAmt': 5000.00,
            'Quoted': True,
            'QuoteClosed': False,
            'Ordered': False,
            'Expired': False
        }

        # Mock no company found
        hubspot_client.get_company_by_property = Mock(return_value=None)

        result = quote_sync.sync_quote(quote_data)

        # Verify it returned error
        assert result == 'error'
        hubspot_client.create_deal.assert_not_called()

    def test_sync_quote_associates_to_company(self, quote_sync, hubspot_client):
        """Test that new quote is associated to company."""
        quote_data = {
            'QuoteNum': 1001,
            'CustNum': 12345,
            'QuoteAmt': 5000.00,
            'Quoted': True,
            'QuoteClosed': False,
            'Ordered': False,
            'Expired': False
        }

        result = quote_sync.sync_quote(quote_data)

        # Verify association was created
        assert result == 'created'
        hubspot_client.associate_deal_to_company.assert_called_once_with(
            'deal-123',
            'company-123'
        )
