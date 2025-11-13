"""
Test quote transformer with stage logic.
"""

import pytest
from datetime import datetime
from src.transformers.quote_transformer import QuoteTransformer, QuoteStageLogic


class TestQuoteTransformer:
    """Test quote to deal transformation."""

    @pytest.fixture
    def transformer(self):
        """Create transformer instance."""
        return QuoteTransformer()

    @pytest.fixture
    def sample_quote(self):
        """Sample quote data from Epicor."""
        return {
            'QuoteNum': 1001,
            'CustNum': 12345,
            'EntryDate': '2024-01-15T10:00:00Z',
            'DueDate': '2024-02-15T10:00:00Z',
            'ExpirationDate': '2024-03-15T10:00:00Z',
            'DateQuoted': '2024-01-20T10:00:00Z',
            'QuoteAmt': 15000.00,
            'DocQuoteAmt': 15000.00,
            'PONum': 'PO-12345',
            'Quoted': True,
            'QuoteClosed': False,
            'Ordered': False,
            'Expired': False,
            'DiscountPercent': 10.5,
            'CurrencyCode': 'CAD',
            'SalesRepCode': 'REP001',
            'SysRowID': '123e4567-e89b-12d3-a456-426614174000'
        }

    def test_transform_new_quote(self, transformer, sample_quote):
        """Test transformation of a new quote (no current stage)."""
        result = transformer.transform(sample_quote, current_hubspot_stage=None)

        # Verify key fields
        assert result['dealname'] == 'Quote #1001'
        assert result['epicor_quote_number'] == 1001
        assert result['amount'] == 15000.00
        assert result['epicor_doc_amount'] == 15000.00
        assert result['customer_po_number'] == 'PO-12345'
        assert result['discount_percentage'] == 10.5
        assert result['deal_currency_code'] == 'CAD'
        assert result['epicor_sales_rep_code'] == 'REP001'

        # Verify boolean flags
        assert result['epicor_quoted'] == True
        assert result['epicor_closed'] == False
        assert result['epicor_converted_to_order'] == False
        assert result['epicor_expired'] == False

        # Verify stage is set (Quoted=true → quote_sent)
        assert result['dealstage'] == 'quote_sent'

    def test_transform_updates_existing_quote(self, transformer, sample_quote):
        """Test transformation of existing quote with stage update."""
        # Quote is currently at quote_created, should update to quote_sent
        result = transformer.transform(sample_quote, current_hubspot_stage='quote_created')

        # Stage should be updated
        assert result['dealstage'] == 'quote_sent'

    def test_transform_blocks_backward_stage_movement(self, transformer, sample_quote):
        """Test that backward stage movement is blocked."""
        # Modify quote to be in initial state
        sample_quote['Quoted'] = False

        # Current stage is quote_sent, new stage would be quote_created
        result = transformer.transform(sample_quote, current_hubspot_stage='quote_sent')

        # Stage should not be present (blocked)
        assert 'dealstage' not in result

    def test_transform_terminal_stage_wins(self, transformer, sample_quote):
        """Test that terminal stages always update."""
        # Quote is closed won
        sample_quote['Ordered'] = True

        result = transformer.transform(sample_quote, current_hubspot_stage='quote_sent')

        # Stage should be updated to closedwon
        assert result['dealstage'] == 'closedwon'

    def test_get_customer_num(self, transformer, sample_quote):
        """Test getting customer number for association."""
        result = transformer.get_customer_num(sample_quote)
        assert result == 12345

    def test_missing_required_field_raises_error(self, transformer):
        """Test that missing required fields raise ValueError."""
        invalid_quote = {
            'QuoteNum': 1001
            # Missing 'CustNum'
        }

        with pytest.raises(ValueError) as exc_info:
            transformer.transform(invalid_quote)

        assert "Missing required fields" in str(exc_info.value)


class TestQuoteStageDerivation:
    """Test stage derivation from Epicor flags."""

    def test_ordered_takes_priority(self):
        """Test: Ordered=true takes highest priority."""
        quote = {
            'Ordered': True,
            'Expired': True,  # This should be ignored
            'QuoteClosed': True,  # This should be ignored
            'Quoted': True
        }
        assert QuoteStageLogic.get_stage_from_epicor(quote) == 'closedwon'

    def test_expired_takes_second_priority(self):
        """Test: Expired=true takes second priority."""
        quote = {
            'Ordered': False,
            'Expired': True,
            'QuoteClosed': True,  # This should be ignored
            'Quoted': True
        }
        assert QuoteStageLogic.get_stage_from_epicor(quote) == 'quote_expired'

    def test_closed_without_order_is_lost(self):
        """Test: QuoteClosed=true without order is closedlost."""
        quote = {
            'Ordered': False,
            'Expired': False,
            'QuoteClosed': True,
            'Quoted': True
        }
        assert QuoteStageLogic.get_stage_from_epicor(quote) == 'closedlost'
