#!/usr/bin/env python3
"""
Test script to sync Quotes and Orders for 20 customers from Epicor to HubSpot.

This script:
1. Fetches Quotes from Epicor for specific customers
2. Fetches Orders from Epicor for specific customers
3. Creates Deals in HubSpot (Quotes and Orders pipelines)
4. Associates each deal with its corresponding company

Usage:
    python scripts/test_sync_quotes_orders.py

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
from src.transformers.quote_transformer import QuoteTransformer
from src.transformers.order_transformer import OrderTransformer
from src.utils.logger import setup_logging

# Customer mapping: CustNum -> HubSpot Company ID
CUSTOMER_HUBSPOT_MAP = {
    # 7: "128438254552",   # Westower Communications - Anjo
    # 8: "127813962684",   # Bell Canada - Pembroke
    # 9: "127806761926",   # Apt Prophet Technologies
    # 10: "127830066129",  # TVC Communications Canada
    # 11: "127804962762",  # Advanced Tower Services (2007)
    # 12: "128387920862",  # Amtelecom Inc.
    # 13: "127835488188",  # Andec Agencies Ltd.
    # 14: "128340951997",  # Preformed Line Products (Spain)
    # 15: "128387920863",  # MTS Allstream Inc.
    # 16: "127833670605",  # Bell Canada
    # 17: "128387920864",  # Anixter Power Solutions Canada
    # 18: "127830066133",  # Burlington H.E.C.
    # 19: "127837257708",  # GrandBridge Energy
    # 20: "127806761929",  # Canadian Niagara Power Co.
    # 21: "127812189170",  # CapTel Inc.
    # 22: "127835488191",  # City of Thunder Bay
    # 23: "127828253678",  # Communications & Cabling Contr
    # 29: "127828253679",  # Bell - London
    # 30: "127828253680",  # Expertech - Newmarket
    31: "127835488193",  # Expertech - Purchasing
}

CUSTOMER_NUMS = list(CUSTOMER_HUBSPOT_MAP.keys())

# Limit quotes/orders per customer for testing
MAX_QUOTES_PER_CUSTOMER = 5
MAX_ORDERS_PER_CUSTOMER = 5


def sync_quotes(epicor_client, hubspot_client, settings):
    """Sync quotes for the specified customers."""
    print("\n" + "=" * 70)
    print("SYNCING QUOTES")
    print("=" * 70)

    transformer = QuoteTransformer()
    pipeline_id = settings.hubspot_quotes_pipeline_id

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

    # Build filter for customer numbers
    cust_filter = " or ".join([f"CustNum eq {c}" for c in CUSTOMER_NUMS])

    print(f"\nFetching quotes for {len(CUSTOMER_NUMS)} customers...")

    try:
        quotes = epicor_client.get_entity(
            service="Erp.BO.QuoteSvc",
            entity_set="Quotes",
            filter_expr=cust_filter,
            expand="QuoteDtls",
            limit=100  # Limit total quotes for testing
        )
        print(f"Found {len(quotes)} quotes")
    except Exception as e:
        print(f"ERROR fetching quotes: {e}")
        return stats

    if not quotes:
        print("No quotes found for these customers.")
        return stats

    print("\nSyncing quotes to HubSpot...")
    print("-" * 70)

    debug_first = True
    for quote in quotes:
        quote_num = quote.get('QuoteNum')
        cust_num = quote.get('CustNum')
        company_id = CUSTOMER_HUBSPOT_MAP.get(cust_num)

        if not company_id:
            print(f"  SKIP: Quote {quote_num} - Customer {cust_num} not in map")
            stats['skipped'] += 1
            continue

        try:
            # Check if deal already exists
            filter_groups = [{
                "filters": [{
                    "propertyName": "epicor_quote_number",
                    "operator": "EQ",
                    "value": str(quote_num)
                }]
            }]

            existing = hubspot_client.search_objects(
                object_type="deals",
                filter_groups=filter_groups
            )

            # Get current HubSpot stage if deal exists
            current_stage = None
            if existing:
                current_stage = existing[0].get('properties', {}).get('dealstage')

            # Transform quote to deal properties
            hs_properties = transformer.transform(
                quote_data=quote,
                current_hubspot_stage=current_stage
            )

            # Add pipeline ID
            hs_properties['pipeline'] = pipeline_id

            # Debug: Print first quote properties
            if debug_first:
                print(f"\n  DEBUG - Properties being sent for Quote #{quote_num}:")
                for key, value in hs_properties.items():
                    print(f"    {key}: {value}")
                print()
                debug_first = False

            if existing:
                # Update existing deal
                deal_id = existing[0]['id']
                hubspot_client.update_object("deals", deal_id, hs_properties)
                stats['updated'] += 1
                print(f"  UPDATED: Quote #{quote_num} (Deal ID: {deal_id})")
            else:
                # Create new deal
                result = hubspot_client.create_object("deals", hs_properties)
                deal_id = result['id']
                stats['created'] += 1
                print(f"  CREATED: Quote #{quote_num} (Deal ID: {deal_id})")

            # Associate deal with company (always ensure association exists)
            try:
                hubspot_client.create_association(
                    from_object="deals",
                    from_id=deal_id,
                    to_object="companies",
                    to_id=company_id,
                    association_type_id=5  # deal_to_company
                )
                print(f"           -> Associated with Company {company_id}")
            except Exception as e:
                print(f"           -> Association failed: {e}")

        except Exception as e:
            stats['errors'] += 1
            # Show full error details
            error_msg = str(e)
            if hasattr(e, 'response') and e.response:
                error_msg += f"\n           Response: {e.response}"
            print(f"  ERROR: Quote #{quote_num}")
            print(f"           {error_msg[:500]}")

    print("-" * 70)
    print(f"Quotes: {stats['created']} created, {stats['updated']} updated, {stats['skipped']} skipped, {stats['errors']} errors")

    return stats


def sync_orders(epicor_client, hubspot_client, settings):
    """Sync orders for the specified customers."""
    print("\n" + "=" * 70)
    print("SYNCING ORDERS")
    print("=" * 70)

    transformer = OrderTransformer()
    pipeline_id = settings.hubspot_orders_pipeline_id

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

    # Build filter for customer numbers
    cust_filter = " or ".join([f"CustNum eq {c}" for c in CUSTOMER_NUMS])

    print(f"\nFetching orders for {len(CUSTOMER_NUMS)} customers...")

    try:
        orders = epicor_client.get_entity(
            service="Erp.BO.SalesOrderSvc",
            entity_set="SalesOrders",
            filter_expr=cust_filter,
            expand="OrderDtls",
            limit=100  # Limit total orders for testing
        )
        print(f"Found {len(orders)} orders")
    except Exception as e:
        print(f"ERROR fetching orders: {e}")
        return stats

    if not orders:
        print("No orders found for these customers.")
        return stats

    print("\nSyncing orders to HubSpot...")
    print("-" * 70)

    for order in orders:
        order_num = order.get('OrderNum')
        cust_num = order.get('CustNum')
        company_id = CUSTOMER_HUBSPOT_MAP.get(cust_num)

        if not company_id:
            print(f"  SKIP: Order {order_num} - Customer {cust_num} not in map")
            stats['skipped'] += 1
            continue

        try:
            # Check if deal already exists
            filter_groups = [{
                "filters": [{
                    "propertyName": "epicor_order_number",
                    "operator": "EQ",
                    "value": str(order_num)
                }]
            }]

            existing = hubspot_client.search_objects(
                object_type="deals",
                filter_groups=filter_groups
            )

            # Transform order to deal properties
            hs_properties = transformer.transform(order_data=order)

            # Add pipeline ID
            hs_properties['pipeline'] = pipeline_id

            if existing:
                # Update existing deal
                deal_id = existing[0]['id']
                hubspot_client.update_object("deals", deal_id, hs_properties)
                stats['updated'] += 1
                print(f"  UPDATED: Order #{order_num} (Deal ID: {deal_id})")
            else:
                # Create new deal
                result = hubspot_client.create_object("deals", hs_properties)
                deal_id = result['id']
                stats['created'] += 1
                print(f"  CREATED: Order #{order_num} (Deal ID: {deal_id})")

            # Associate deal with company (always ensure association exists)
            try:
                hubspot_client.create_association(
                    from_object="deals",
                    from_id=deal_id,
                    to_object="companies",
                    to_id=company_id,
                    association_type_id=5  # deal_to_company
                )
                print(f"           -> Associated with Company {company_id}")
            except Exception as e:
                print(f"           -> Association failed: {e}")

        except Exception as e:
            stats['errors'] += 1
            error_msg = str(e)
            if hasattr(e, 'response'):
                error_msg += f"\n           Response: {e.response}"
            print(f"  ERROR: Order #{order_num}")
            print(f"           {error_msg[:200]}")

    print("-" * 70)
    print(f"Orders: {stats['created']} created, {stats['updated']} updated, {stats['skipped']} skipped, {stats['errors']} errors")

    return stats


def main():
    """Main function to sync quotes and orders."""
    print("=" * 70)
    print("TEST SYNC: Quotes & Orders for 20 Customers")
    print("=" * 70)

    # Load settings
    print("\n[1/5] Loading configuration...")
    settings = get_settings()
    setup_logging(settings.log_level)
    print(f"      Quotes Pipeline ID: {settings.hubspot_quotes_pipeline_id}")
    print(f"      Orders Pipeline ID: {settings.hubspot_orders_pipeline_id}")

    # Validate pipeline IDs
    if settings.hubspot_orders_pipeline_id == "default" or not settings.hubspot_orders_pipeline_id:
        print("\n      WARNING: Orders Pipeline ID is not set properly!")
        print("      Please set HUBSPOT_ORDERS_PIPELINE_ID in your .env file")
        print("      You can find it in HubSpot > Settings > Objects > Deals > Pipelines")

    # Initialize clients
    print("\n[2/5] Initializing API clients...")
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
    print("      Clients initialized")

    # Test connections
    print("\n[3/5] Testing connections...")
    if not epicor_client.test_connection():
        print("      ERROR: Epicor connection failed!")
        return 1
    print("      Epicor: OK")

    if not hubspot_client.test_connection():
        print("      ERROR: HubSpot connection failed!")
        return 1
    print("      HubSpot: OK")

    # Show customer mapping
    print("\n[4/5] Customer mapping:")
    print("-" * 70)
    print(f"{'CustNum':<10} {'HubSpot Company ID':<20}")
    print("-" * 70)
    for cust_num, company_id in CUSTOMER_HUBSPOT_MAP.items():
        print(f"{cust_num:<10} {company_id:<20}")
    print("-" * 70)

    # Confirm
    print("\nWARNING: This will create REAL deals in HubSpot!")
    response = input("Do you want to proceed? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Aborted by user.")
        return 0

    # Sync quotes
    print("\n[5/5] Syncing data...")
    quote_stats = sync_quotes(epicor_client, hubspot_client, settings)

    # Sync orders
    order_stats = sync_orders(epicor_client, hubspot_client, settings)

    # Final summary
    print("\n" + "=" * 70)
    print("SYNC COMPLETE - SUMMARY")
    print("=" * 70)
    print(f"\nQUOTES:")
    print(f"  Created: {quote_stats['created']}")
    print(f"  Updated: {quote_stats['updated']}")
    print(f"  Skipped: {quote_stats['skipped']}")
    print(f"  Errors:  {quote_stats['errors']}")

    print(f"\nORDERS:")
    print(f"  Created: {order_stats['created']}")
    print(f"  Updated: {order_stats['updated']}")
    print(f"  Skipped: {order_stats['skipped']}")
    print(f"  Errors:  {order_stats['errors']}")

    print("\n" + "=" * 70)

    total_errors = quote_stats['errors'] + order_stats['errors']
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
