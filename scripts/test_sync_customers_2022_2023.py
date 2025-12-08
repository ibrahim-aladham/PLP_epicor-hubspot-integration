#!/usr/bin/env python3
"""
Test script to sync 20 customers from Epicor to HubSpot.
10 from year 2022 and 10 from year 2023.

This script:
1. Fetches 10 customers created in 2022
2. Fetches 10 customers created in 2023
3. Transforms them to HubSpot Company format
4. Creates or updates them in HubSpot

Usage:
    python scripts/test_sync_customers_2022_2023.py

WARNING: This will create/update REAL data in HubSpot!
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from src.config import get_settings
from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.transformers.customer_transformer import CustomerTransformer
from src.utils.logger import setup_logging

# Configuration
CUSTOMERS_PER_YEAR = 10


def fetch_customers_by_year(epicor_client: EpicorClient, year: int, limit: int):
    """
    Fetch customers created in a specific year.

    Args:
        epicor_client: Epicor API client
        year: Year to filter by (e.g., 2022, 2023)
        limit: Maximum number of customers to fetch

    Returns:
        List of customer records
    """
    # Build OData filter for the year using EstDate (Establishment Date)
    # OData v4 datetime format: ISO 8601 without 'datetime' keyword
    start_date = f"{year}-01-01T00:00:00Z"
    end_date = f"{year + 1}-01-01T00:00:00Z"

    filter_expr = f"EstDate ge {start_date} and EstDate lt {end_date}"

    print(f"      Fetching customers from {year}...")
    print(f"      Filter: {filter_expr}")

    try:
        customers = epicor_client.get_entity(
            service="Erp.BO.CustomerSvc",
            entity_set="Customers",
            filter_expr=filter_expr,
            limit=limit
        )
        print(f"      Found {len(customers)} customers from {year}")
        return customers
    except Exception as e:
        print(f"      ERROR fetching {year} customers: {e}")
        return []


def main():
    """Sync 10 customers from 2022 and 10 from 2023."""

    print("=" * 70)
    print("TEST SYNC: Customers from 2022 & 2023")
    print("=" * 70)
    print()

    # Load settings
    print("[1/6] Loading configuration...")
    settings = get_settings()
    setup_logging(settings.log_level)
    print(f"      Environment: {settings.environment}")
    print(f"      Epicor Company: {settings.epicor_company}")
    print()

    # Initialize clients
    print("[2/6] Initializing API clients...")
    epicor_client = EpicorClient(
        base_url=settings.epicor_base_url,
        company=settings.epicor_company,
        username=settings.epicor_username,
        password=settings.epicor_password,
        api_key=settings.epicor_api_key,
        batch_size=settings.sync_batch_size
    )

    hubspot_client = HubSpotClient(
        api_key=settings.hubspot_api_key
    )

    transformer = CustomerTransformer()
    print("      Clients initialized successfully")
    print()

    # Test connections
    print("[3/6] Testing API connections...")
    if not epicor_client.test_connection():
        print("      ERROR: Epicor connection failed!")
        return 1
    print("      Epicor: OK")

    if not hubspot_client.test_connection():
        print("      ERROR: HubSpot connection failed!")
        return 1
    print("      HubSpot: OK")
    print()

    # Fetch customers from Epicor
    print(f"[4/6] Fetching customers from Epicor...")
    customers_2022 = fetch_customers_by_year(epicor_client, 2022, CUSTOMERS_PER_YEAR)
    customers_2023 = fetch_customers_by_year(epicor_client, 2023, CUSTOMERS_PER_YEAR)

    # Combine all customers
    all_customers = customers_2022 + customers_2023
    print(f"      Total: {len(all_customers)} customers")
    print()

    if not all_customers:
        print("      ERROR: No customers found!")
        return 1

    # Display customers to sync
    print("[5/6] Customers to sync:")
    print("-" * 80)
    print(f"{'#':<4} {'Year':<6} {'CustNum':<10} {'CustID':<12} {'Name':<40}")
    print("-" * 80)

    # Display 2022 customers
    for i, cust in enumerate(customers_2022, 1):
        print(f"{i:<4} 2022   {cust.get('CustNum', 'N/A'):<10} {cust.get('CustID', 'N/A'):<12} {cust.get('Name', 'N/A')[:40]:<40}")

    # Display 2023 customers
    for i, cust in enumerate(customers_2023, len(customers_2022) + 1):
        print(f"{i:<4} 2023   {cust.get('CustNum', 'N/A'):<10} {cust.get('CustID', 'N/A'):<12} {cust.get('Name', 'N/A')[:40]:<40}")

    print("-" * 80)
    print()

    # Confirm before proceeding
    print("WARNING: This will create/update REAL data in HubSpot!")
    response = input("Do you want to proceed? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Aborted by user.")
        return 0
    print()

    # Sync each customer
    print("[6/6] Syncing customers to HubSpot...")
    print("-" * 80)

    stats = {'created': 0, 'updated': 0, 'errors': 0, '2022': 0, '2023': 0}

    for i, customer in enumerate(all_customers, 1):
        cust_num = customer.get('CustNum')
        cust_name = customer.get('Name', 'Unknown')[:30]
        year = '2022' if customer in customers_2022 else '2023'

        try:
            # Transform customer data
            hs_properties = transformer.transform(customer)

            # Search for existing company in HubSpot
            filter_groups = [{
                "filters": [{
                    "propertyName": "epicor_customer_number",
                    "operator": "EQ",
                    "value": str(cust_num)
                }]
            }]

            existing = hubspot_client.search_objects(
                object_type="companies",
                filter_groups=filter_groups
            )

            if existing:
                # Update existing company
                company_id = existing[0]['id']
                hubspot_client.update_object("companies", company_id, hs_properties)
                stats['updated'] += 1
                stats[year] += 1
                print(f"  [{i:2}/{len(all_customers)}] [{year}] UPDATED: {cust_num} - {cust_name}")
            else:
                # Create new company
                result = hubspot_client.create_object("companies", hs_properties)
                stats['created'] += 1
                stats[year] += 1
                print(f"  [{i:2}/{len(all_customers)}] [{year}] CREATED: {cust_num} - {cust_name} (HubSpot ID: {result['id']})")

        except Exception as e:
            stats['errors'] += 1
            print(f"  [{i:2}/{len(all_customers)}] [{year}] ERROR:   {cust_num} - {cust_name} - {str(e)[:50]}")

    print("-" * 80)
    print()

    # Summary
    print("=" * 70)
    print("SYNC COMPLETE")
    print("=" * 70)
    print(f"  2022 Customers: {stats['2022']}")
    print(f"  2023 Customers: {stats['2023']}")
    print(f"  Created:        {stats['created']}")
    print(f"  Updated:        {stats['updated']}")
    print(f"  Errors:         {stats['errors']}")
    print(f"  Total:          {stats['created'] + stats['updated'] + stats['errors']}")
    print("=" * 70)

    return 0 if stats['errors'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
