"""
Test customer transformer.
"""

import pytest
from src.transformers.customer_transformer import CustomerTransformer


class TestCustomerTransformer:
    """Test customer to company transformation."""

    @pytest.fixture
    def transformer(self):
        """Create transformer instance."""
        return CustomerTransformer()

    @pytest.fixture
    def sample_customer(self):
        """Sample customer data from Epicor."""
        return {
            'CustNum': 12345,
            'CustID': 'CUST001',
            'Name': 'Test Company Inc.',
            'Address1': '123 Main St',
            'Address2': 'Suite 100',
            'City': 'Toronto',
            'State': 'ON',
            'Zip': 'M5H 2N2',
            'Country': 'Canada',
            'PhoneNum': '(416) 555-1234',
            'FaxNum': '(416) 555-5678',
            'EmailAddress': 'contact@testcompany.com',
            'CurrencyCode': 'CAD',
            'SysRowID': '123e4567-e89b-12d3-a456-426614174000'
        }

    def test_transform_complete_customer(self, transformer, sample_customer):
        """Test transformation with all fields present."""
        result = transformer.transform(sample_customer)

        # Verify all 14 required fields are present
        assert result['epicor_customer_number'] == 12345
        assert result['epicor_customer_code'] == 'CUST001'
        assert result['name'] == 'Test Company Inc.'
        assert result['address'] == '123 Main St'
        assert result['address2'] == 'Suite 100'
        assert result['city'] == 'Toronto'
        assert result['state'] == 'ON'
        assert result['zip'] == 'M5H 2N2'
        assert result['country'] == 'Canada'
        assert result['phone'] == '+14165551234'  # E.164 format
        assert result['fax_number'] == '(416) 555-5678'
        assert result['epicor_email'] == 'contact@testcompany.com'
        assert result['currency_code'] == 'CAD'
        assert result['epicor_sysrowid'] == '123e4567e89b12d3a456426614174000'

    def test_transform_minimal_customer(self, transformer):
        """Test transformation with only required fields."""
        minimal_customer = {
            'CustNum': 99999,
            'Name': 'Minimal Customer'
        }

        result = transformer.transform(minimal_customer)

        # Verify required fields
        assert result['epicor_customer_number'] == 99999
        assert result['name'] == 'Minimal Customer'

        # Optional fields should not be present (None values removed)
        assert 'address' not in result
        assert 'phone' not in result

    def test_missing_required_field_raises_error(self, transformer):
        """Test that missing required fields raise ValueError."""
        invalid_customer = {
            'CustNum': 12345
            # Missing 'Name'
        }

        with pytest.raises(ValueError) as exc_info:
            transformer.transform(invalid_customer)

        assert "Missing required fields" in str(exc_info.value)

    def test_get_customer_num(self, transformer, sample_customer):
        """Test getting customer number."""
        result = transformer.get_customer_num(sample_customer)
        assert result == 12345

    def test_phone_formatting(self, transformer):
        """Test phone number E.164 formatting."""
        customer = {
            'CustNum': 12345,
            'Name': 'Test',
            'PhoneNum': '416-555-1234'
        }

        result = transformer.transform(customer)
        assert result['phone'] == '+14165551234'
