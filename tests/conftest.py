"""
Pytest configuration and fixtures for tests.

This module provides shared fixtures and configuration for all test modules.
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import Dict, Any


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.epicor_base_url = "https://test.epicor.com/ERP11TEST"
    settings.epicor_company = "TEST"
    settings.epicor_username = "test_user"
    settings.epicor_password = "test_password"
    settings.epicor_api_key = "test_epicor_key"
    settings.hubspot_api_key = "test_hubspot_key"
    settings.hubspot_quotes_pipeline_id = "quotes_pipeline_123"
    settings.hubspot_orders_pipeline_id = "orders_pipeline_456"
    settings.aws_region = "us-east-1"
    settings.aws_s3_bucket = "test-bucket"
    settings.sync_batch_size = 100
    settings.sync_max_retries = 3
    settings.log_level = "INFO"
    settings.environment = "development"
    return settings


@pytest.fixture
def sample_customer():
    """Sample Epicor customer data."""
    return {
        "CustNum": 123,
        "CustID": "ABC123",
        "Name": "Test Company Ltd.",
        "Address1": "123 Main Street",
        "Address2": "Suite 100",
        "City": "Toronto",
        "State": "ON",
        "Zip": "M5H 2N2",
        "Country": "Canada",
        "PhoneNum": "416-555-0123",
        "FaxNum": "416-555-0124",
        "EmailAddress": "info@testcompany.com",
        "TermsCode": "NET30",
        "CreditHold": False,
        "TerritoryID": "EAST",
        "CurrencyCode": "CAD",
        "SysRowID": "550e8400-e29b-41d4-a716-446655440000"
    }


@pytest.fixture
def sample_contact():
    """Sample Epicor contact data."""
    return {
        "PerConID": 456,
        "Name": "John Smith",
        "FirstName": "John",
        "MiddleName": "A",
        "LastName": "Smith",
        "EmailAddress": "john.smith@testcompany.com",
        "PhoneNum": "416-555-0125",
        "FaxNum": "416-555-0126",
        "Func": "SALES",
        "SysRowID": "660e8400-e29b-41d4-a716-446655440001",
        "PerConLnks": [
            {
                "CustNum": 123,
                "PrimaryContact": True
            }
        ]
    }


@pytest.fixture
def sample_quote():
    """Sample Epicor quote data."""
    return {
        "QuoteNum": 789,
        "CustNum": 123,
        "EntryDate": "2024-01-15T10:30:00Z",
        "DueDate": "2024-02-15T00:00:00Z",
        "ExpirationDate": "2024-03-15T00:00:00Z",
        "DateQuoted": "2024-01-16T14:00:00Z",
        "QuoteAmt": 15000.00,
        "DocQuoteAmt": 15000.00,
        "PONum": "PO-2024-001",
        "CurrentStage": "QUOTED",
        "Quoted": True,
        "QuoteClosed": False,
        "Ordered": False,
        "Expired": False,
        "DiscountPercent": 5.0,
        "CurrencyCode": "CAD",
        "SysRowID": "770e8400-e29b-41d4-a716-446655440002",
        "QuoteDtls": [
            {
                "QuoteNum": 789,
                "QuoteLine": 1,
                "PartNum": "PART-001",
                "LineDesc": "Widget Type A",
                "QuoteQty": 10,
                "DocUnitPrice": 100.00,
                "DocExtPriceDtl": 1000.00
            },
            {
                "QuoteNum": 789,
                "QuoteLine": 2,
                "PartNum": "PART-002",
                "LineDesc": "Widget Type B",
                "QuoteQty": 5,
                "DocUnitPrice": 200.00,
                "DocExtPriceDtl": 1000.00
            }
        ]
    }


@pytest.fixture
def sample_order():
    """Sample Epicor order data."""
    return {
        "OrderNum": 1001,
        "CustNum": 123,
        "OrderDate": "2024-01-20T09:00:00Z",
        "RequestDate": "2024-02-20T00:00:00Z",
        "NeedByDate": "2024-02-15T00:00:00Z",
        "OrderAmt": 12000.00,
        "TotalCharges": 11400.00,
        "DocOrderAmt": 12000.00,
        "PONum": "PO-2024-002",
        "OpenOrder": True,
        "OrderHeld": False,
        "VoidOrder": False,
        "OrderStatus": "OPEN",
        "CurrencyCode": "CAD",
        "SysRowID": "880e8400-e29b-41d4-a716-446655440003",
        "OrderDtls": [
            {
                "OrderNum": 1001,
                "OrderLine": 1,
                "PartNum": "PART-003",
                "LineDesc": "Widget Type C",
                "OrderQty": 20,
                "DocUnitPrice": 50.00,
                "DocExtPriceDtl": 1000.00
            }
        ]
    }


@pytest.fixture
def sample_part():
    """Sample Epicor part data."""
    return {
        "PartNum": "PART-001",
        "PartDescription": "High Quality Widget Type A",
        "SearchWord": "WIDGET-A",
        "ClassID": "WIDGETS",
        "TypeCode": "M",  # Manufactured
        "IUM": "EA",  # Each
        "PUM": "EA",
        "NonStock": False,
        "PurchasingFactor": 1.0,
        "InActive": False,
        "SysRowID": "990e8400-e29b-41d4-a716-446655440004"
    }


@pytest.fixture
def mock_epicor_client(sample_customer, sample_contact, sample_quote, sample_order, sample_part):
    """Mock Epicor API client."""
    client = Mock()
    client.test_connection = Mock(return_value=True)
    client.get_entity = Mock(side_effect=lambda service, entity_set, **kwargs: {
        ("Erp.BO.CustomerSvc", "Customers"): [sample_customer],
        ("Erp.BO.PerConSvc", "PerCons"): [sample_contact],
        ("Erp.BO.QuoteSvc", "Quotes"): [sample_quote],
        ("Erp.BO.SalesOrderSvc", "SalesOrders"): [sample_order],
        ("Erp.BO.PartSvc", "Parts"): [sample_part],
    }.get((service, entity_set), []))
    return client


@pytest.fixture
def mock_hubspot_client():
    """Mock HubSpot API client."""
    client = Mock()
    client.test_connection = Mock(return_value=True)
    client.search_objects = Mock(return_value=[])
    client.create_object = Mock(return_value={"id": "12345", "properties": {}})
    client.update_object = Mock(return_value={"id": "12345", "properties": {}})
    client.create_association = Mock(return_value=True)
    return client


@pytest.fixture
def mock_responses():
    """Provides a context manager for mocking HTTP responses."""
    try:
        import responses
        return responses
    except ImportError:
        pytest.skip("responses library not installed")
