#!/usr/bin/env python3
"""
Test script to sync 20 real customers from Epicor to HubSpot.

This script:
1. Fetches 20 customers from Epicor
2. Transforms them to HubSpot Company format
3. Creates or updates them in HubSpot

Usage:
    python scripts/test_sync_20_customers.py

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
CUSTOMER_LIMIT = 20


def main():
    """Sync 20 customers from Epicor to HubSpot."""

    print("=" * 70)
    print("TEST SYNC: 20 Customers from Epicor to HubSpot")
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
    print(f"[4/6] Fetching {CUSTOMER_LIMIT} customers from Epicor...")
    try:
        customers = epicor_client.get_entity(
            service="Erp.BO.CustomerSvc",
            entity_set="Customers",
            limit=CUSTOMER_LIMIT
        )
        print(f"      Fetched {len(customers)} customers")
    except Exception as e:
        print(f"      ERROR fetching customers: {e}")
        return 1
    print()

    # Display customers to sync
    print("[5/6] Customers to sync:")
    print("-" * 70)
    print(f"{'#':<4} {'CustNum':<10} {'CustID':<12} {'Name':<40}")
    print("-" * 70)
    for i, cust in enumerate(customers, 1):
        print(f"{i:<4} {cust.get('CustNum', 'N/A'):<10} {cust.get('CustID', 'N/A'):<12} {cust.get('Name', 'N/A')[:40]:<40}")
    print("-" * 70)
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
    print("-" * 70)

    stats = {'created': 0, 'updated': 0, 'errors': 0}

    for i, customer in enumerate(customers, 1):
        cust_num = customer.get('CustNum')
        cust_name = customer.get('Name', 'Unknown')[:30]

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
                print(f"  [{i:2}/{CUSTOMER_LIMIT}] UPDATED: {cust_num} - {cust_name}")
            else:
                # Create new company
                result = hubspot_client.create_object("companies", hs_properties)
                stats['created'] += 1
                print(f"  [{i:2}/{CUSTOMER_LIMIT}] CREATED: {cust_num} - {cust_name} (HubSpot ID: {result['id']})")

        except Exception as e:
            stats['errors'] += 1
            print(f"  [{i:2}/{CUSTOMER_LIMIT}] ERROR:   {cust_num} - {cust_name} - {str(e)[:50]}")

    print("-" * 70)
    print()

    # Summary
    print("=" * 70)
    print("SYNC COMPLETE")
    print("=" * 70)
    print(f"  Created: {stats['created']}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Errors:  {stats['errors']}")
    print(f"  Total:   {stats['created'] + stats['updated'] + stats['errors']}")
    print("=" * 70)

    return 0 if stats['errors'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
