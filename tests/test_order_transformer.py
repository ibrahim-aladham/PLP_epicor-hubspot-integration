"""
Test order transformer with stage logic.
"""

import pytest
from src.transformers.order_transformer import OrderTransformer, OrderStageLogic


class TestOrderTransformer:
    """Test order to deal transformation."""

    @pytest.fixture
    def transformer(self):
        """Create transformer instance."""
        return OrderTransformer()

    @pytest.fixture
    def sample_order(self):
        """Sample order data from Epicor."""
        return {
            'OrderNum': 5001,
            'CustNum': 12345,
            'OrderDate': '2024-01-15T10:00:00Z',
            'RequestDate': '2024-02-15T10:00:00Z',
            'NeedByDate': '2024-02-10T10:00:00Z',
            'OrderAmt': 25000.00,
            'DocOrderAmt': 25000.00,
            'PONum': 'PO-67890',
            'OpenOrder': True,
            'VoidOrder': False,
            'OrderHeld': False,
            'TotalShipped': 0,
            'CurrencyCode': 'CAD',
            'SysRowID': '123e4567-e89b-12d3-a456-426614174000'
        }

    def test_transform_complete_order(self, transformer, sample_order):
        """Test transformation with all fields present."""
        result = transformer.transform(sample_order)

        # Verify all 13 required fields
        assert result['dealname'] == 'Order #5001'
        assert result['epicor_order_number'] == 5001
        assert result['amount'] == 25000.00
        assert result['epicor_doc_amount'] == 25000.00
        assert result['customer_po_number'] == 'PO-67890'
        assert result['epicor_open_order'] == True
        assert result['deal_currency_code_'] == 'CAD'

        # Verify stage (new order with no shipments)
        assert result['dealstage'] == 'order_received'

    def test_stage_derivation_cancelled(self, transformer, sample_order):
        """Test: VoidOrder=true → cancelled."""
        sample_order['VoidOrder'] = True

        result = transformer.transform(sample_order)
        assert result['dealstage'] == 'cancelled'

    def test_stage_derivation_completed(self, transformer, sample_order):
        """Test: OpenOrder=false → completed."""
        sample_order['OpenOrder'] = False

        result = transformer.transform(sample_order)
        assert result['dealstage'] == 'completed'

    def test_stage_derivation_held(self, transformer, sample_order):
        """Test: OrderHeld=true → order_held."""
        sample_order['OrderHeld'] = True

        result = transformer.transform(sample_order)
        assert result['dealstage'] == 'order_held'

    def test_stage_derivation_partially_shipped(self, transformer, sample_order):
        """Test: OpenOrder=true AND TotalShipped>0 → partially_shipped."""
        sample_order['OpenOrder'] = True
        sample_order['TotalShipped'] = 5000

        result = transformer.transform(sample_order)
        assert result['dealstage'] == 'partially_shipped'

    def test_stage_derivation_order_received(self, transformer, sample_order):
        """Test: Default state → order_received."""
        sample_order['OpenOrder'] = True
        sample_order['TotalShipped'] = 0
        sample_order['OrderHeld'] = False
        sample_order['VoidOrder'] = False

        result = transformer.transform(sample_order)
        assert result['dealstage'] == 'order_received'

    def test_get_customer_num(self, transformer, sample_order):
        """Test getting customer number for association."""
        result = transformer.get_customer_num(sample_order)
        assert result == 12345

    def test_missing_required_field_raises_error(self, transformer):
        """Test that missing required fields raise ValueError."""
        invalid_order = {
            'OrderNum': 5001
            # Missing 'CustNum' and 'OpenOrder'
        }

        with pytest.raises(ValueError) as exc_info:
            transformer.transform(invalid_order)

        assert "Missing required fields" in str(exc_info.value)


class TestOrderStageLogic:
    """Test order stage derivation logic."""

    def test_void_takes_priority(self):
        """Test: VoidOrder takes highest priority."""
        order = {
            'VoidOrder': True,
            'OpenOrder': False,  # Should be ignored
            'OrderHeld': True,  # Should be ignored
            'TotalShipped': 10
        }
        assert OrderStageLogic.get_stage_from_epicor(order) == 'cancelled'

    def test_completed_takes_second_priority(self):
        """Test: OpenOrder=false takes second priority."""
        order = {
            'VoidOrder': False,
            'OpenOrder': False,
            'OrderHeld': True,  # Should be ignored
            'TotalShipped': 100
        }
        assert OrderStageLogic.get_stage_from_epicor(order) == 'completed'

    def test_held_takes_third_priority(self):
        """Test: OrderHeld takes third priority."""
        order = {
            'VoidOrder': False,
            'OpenOrder': True,
            'OrderHeld': True,
            'TotalShipped': 0
        }
        assert OrderStageLogic.get_stage_from_epicor(order) == 'order_held'

    def test_partially_shipped_logic(self):
        """Test: Partially shipped when open and has shipments."""
        order = {
            'VoidOrder': False,
            'OpenOrder': True,
            'OrderHeld': False,
            'TotalShipped': 50
        }
        assert OrderStageLogic.get_stage_from_epicor(order) == 'partially_shipped'

    def test_default_order_received(self):
        """Test: Default state is order_received."""
        order = {
            'VoidOrder': False,
            'OpenOrder': True,
            'OrderHeld': False,
            'TotalShipped': 0
        }
        assert OrderStageLogic.get_stage_from_epicor(order) == 'order_received'
