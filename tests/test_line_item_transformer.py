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
            'PartNum': 'PART-001',
            'LineDesc': 'Test Product Description',
            'OrderQty': 10,
            'DocUnitPrice': 100.00,
            'DocExtPriceDtl': 1000.00
        }

    @pytest.fixture
    def sample_order_line(self):
        """Sample order line item from Epicor."""
        return {
            'PartNum': 'PART-002',
            'LineDesc': 'Another Product',
            'OrderQty': 5,
            'DocUnitPrice': 200.00,
            'DocExtPriceDtl': 1000.00
        }

    def test_transform_quote_line(self, transformer, sample_quote_line):
        """Test quote line transformation."""
        result = transformer.transform_quote_line(sample_quote_line)

        assert result['sku'] == 'PART-001'
        assert result['name'] == 'Test Product Description'
        assert result['quantity'] == 10
        assert result['price'] == 100.00
        assert result['amount'] == 1000.00

    def test_transform_order_line(self, transformer, sample_order_line):
        """Test order line transformation."""
        result = transformer.transform_order_line(sample_order_line)

        assert result['sku'] == 'PART-002'
        assert result['name'] == 'Another Product'
        assert result['quantity'] == 5
        assert result['price'] == 200.00
        assert result['amount'] == 1000.00

    def test_transform_line_without_description(self, transformer):
        """Test line item without description uses part number."""
        line = {
            'PartNum': 'PART-003',
            'OrderQty': 1,
            'DocUnitPrice': 50.00,
            'DocExtPriceDtl': 50.00
        }

        result = transformer.transform_quote_line(line)

        assert result['sku'] == 'PART-003'
        assert result['name'] == 'Part PART-003'

    def test_get_minimal_product_properties(self, transformer):
        """Test minimal product properties for auto-creation."""
        result = transformer.get_minimal_product_properties(
            'PART-001',
            'Test Product'
        )

        assert result['hs_sku'] == 'PART-001'
        assert result['name'] == 'Test Product'
        assert 'Auto-created' in result['description']

    def test_get_minimal_product_properties_without_name(self, transformer):
        """Test minimal product properties without name."""
        result = transformer.get_minimal_product_properties('PART-001')

        assert result['hs_sku'] == 'PART-001'
        assert result['name'] == 'Part PART-001'
        assert 'Auto-created' in result['description']

    def test_transform_raises_not_implemented(self, transformer):
        """Test that base transform method raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            transformer.transform({})
