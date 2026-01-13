"""
Test line item transformer.
"""

import pytest
from src.transformers.line_item_transformer import LineItemTransformer


class TestLineItemTransformer:
    """Test line item transformation."""

    @pytest.fixture
    def transformer(self):
        """Create transformer instance."""
        return LineItemTransformer()

    @pytest.fixture
    def sample_quote_line(self):
        """Sample quote line item from Epicor."""
        return {
            'QuoteNum': 1001,
            'QuoteLine': 1,
            'PartNum': 'PART-001',
            'LineDesc': 'Test Product Description',
            'OrderQty': 10,
            'ExpUnitPrice': 100.00,
            'ExtPriceDtl': 1000.00,
            'Number02': 75.00,  # Unit cost
            'Character06': 'Standard Cost',  # Cost source
            'Character01': 'Backup note',
            'QuoteComment': 'Line comment'
        }

    @pytest.fixture
    def sample_order_line(self):
        """Sample order line item from Epicor."""
        return {
            'OrderNum': 2001,
            'OrderLine': 1,
            'PartNum': 'PART-002',
            'LineDesc': 'Another Product',
            'OrderQty': 5,
            'UnitPrice': 200.00,
            'ExtPriceDtl': 1000.00,
            'NeedByDate': '2026-01-15T00:00:00',
            'RequestDate': '2026-01-20T00:00:00',
            'Character01': 'Manager Name'
        }

    def test_transform_quote_line(self, transformer, sample_quote_line):
        """Test quote line transformation."""
        result = transformer.transform_quote_line(sample_quote_line, quote_num=1001)

        assert result['sku'] == 'PART-001'
        assert result['name'] == 'PART-001 Test Product Description'
        assert result['quantity'] == 10
        assert result['price'] == 100.00
        assert result['amount'] == 1000.00
        assert result['epicor_line_item_id'] == 'Q1001-1'
        # Cost fields
        assert result['epicor_line_current_cost'] == 75.00
        assert result['hs_cost_of_goods_sold'] == 75.00
        assert result['epicor_cost_source'] == 'Standard Cost'

    def test_transform_order_line(self, transformer, sample_order_line):
        """Test order line transformation."""
        result = transformer.transform_order_line(sample_order_line, order_num=2001)

        assert result['sku'] == 'PART-002'
        assert result['name'] == 'PART-002 Another Product'
        assert result['quantity'] == 5
        assert result['price'] == 200.00
        assert result['amount'] == 1000.00
        assert result['epicor_line_item_id'] == 'O2001-1'
        assert result['epicor_c1_manager'] == 'Manager Name'

    def test_transform_line_without_description(self, transformer):
        """Test line item without description uses part number."""
        line = {
            'QuoteLine': 1,
            'PartNum': 'PART-003',
            'OrderQty': 1,
            'ExpUnitPrice': 50.00,
            'ExtPriceDtl': 50.00
        }

        result = transformer.transform_quote_line(line, quote_num=999)

        assert result['sku'] == 'PART-003'
        assert result['name'] == 'PART-003'  # Just part number when no description

    def test_get_minimal_product_properties(self, transformer):
        """Test minimal product properties for auto-creation."""
        result = transformer.get_minimal_product_properties(
            'PART-001',
            'Test Product',
            price=100.00,
            cost=75.00
        )

        assert result['hs_sku'] == 'PART-001'
        assert result['name'] == 'PART-001 Test Product'
        assert result['description'] == 'Test Product'
        assert result['price'] == 100.00
        assert result['hs_cost_of_goods_sold'] == 75.00

    def test_get_minimal_product_properties_without_description(self, transformer):
        """Test minimal product properties without description."""
        result = transformer.get_minimal_product_properties('PART-001')

        assert result['hs_sku'] == 'PART-001'
        assert result['name'] == 'PART-001'  # Just part number when no description
        assert result['description'] == ''

    def test_get_minimal_product_properties_without_cost(self, transformer):
        """Test minimal product properties without cost."""
        result = transformer.get_minimal_product_properties(
            'PART-001',
            'Test Product'
        )

        assert result['hs_sku'] == 'PART-001'
        assert 'hs_cost_of_goods_sold' not in result  # Should not be present if None

    def test_transform_raises_not_implemented(self, transformer):
        """Test that base transform method raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            transformer.transform({})
