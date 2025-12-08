#!/usr/bin/env python3
"""
Test script to sync quotes and orders for 2022/2023 customers.
Syncs quotes and orders for the 20 customers (10 from 2022, 10 from 2023).

Usage:
    python scripts/test_sync_quotes_orders_2022_2023.py

WARNING: This will create/update REAL deals in HubSpot!
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
from src.sync.line_item_sync import LineItemSync
from src.utils.logger import setup_logging

# Customer numbers from 2022/2023 sync
CUSTOMER_NUMS_2022 = [1358, 1359, 1360, 1361, 1363, 1365, 1366, 1367, 1369, 1370]
CUSTOMER_NUMS_2023 = [1384, 1385, 1386, 1387, 1388, 1390, 1391, 1392, 1393, 1394]
CUSTOMER_NUMS = CUSTOMER_NUMS_2022 + CUSTOMER_NUMS_2023

# Customer mapping: CustNum -> HubSpot Company ID
CUSTOMER_HUBSPOT_MAP = {
    # 2022 customers
    1358: "135816807393",  # PROCAN POWER SYSTEMS LTD.
    1359: "135888753609",  # Kukielka Produce Inc.
    1360: "134955816899",  # EECOL ELECTRIC CORP.
    1361: "135888753610",  # Guillevin
    1363: "137366758337",  # ALU MC3
    1365: "137366758338",  # Les services marins Gilles Tougas
    1366: "137368556528",  # Pro Ballast Inc
    1367: "134955816900",  # EECOL ELECTRIC CORP
    1369: "137015704566",  # Industries Précision Plus Inc
    1370: "137272930235",  # EECOL ELECTRIC CORP-THOMPSON
    # 2023 customers
    1384: "137366758339",  # Wesbell Technologies West Inc
    1385: "137272930237",  # Valmont Industries, Inc.
    1386: "137364957177",  # Electrostatics Kft.
    1387: "137015704567",  # Enginomix Consulting Inc.
    1388: "137352518633",  # Nbisiing Power
    1390: "137210762199",  # AFC INDUSTRIES INC
    1391: "136755410878",  # Wood PLC
    1392: "137366758340",  # LEADING AHEAD ENERGY
    1393: "136237171647",  # Énergie CPG Est / Composite Power Group
    1394: "137278324723",  # Capital Power
}

# Max quotes/orders per customer
MAX_QUOTES_PER_CUSTOMER = 5
MAX_ORDERS_PER_CUSTOMER = 5


def sync_quotes(epicor_client, hubspot_client, line_item_sync, settings):
    """Sync quotes for the specified customers."""
    print("\n" + "=" * 70)
    print("SYNCING QUOTES")
    print("=" * 70)

    transformer = QuoteTransformer()
    pipeline_id = settings.hubspot_quotes_pipeline_id

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0, 'line_items': 0}

    # Build filter for customer numbers
    cust_filter = " or ".join([f"CustNum eq {c}" for c in CUSTOMER_NUMS])

    # Fetch quotes with line items
    print(f"\nFetching quotes for {len(CUSTOMER_NUMS)} customers...")
    quotes = epicor_client.get_entity(
        service="Erp.BO.QuoteSvc",
        entity_set="Quotes",
        filter_expr=cust_filter,
        expand="QuoteDtls",
        limit=len(CUSTOMER_NUMS) * MAX_QUOTES_PER_CUSTOMER
    )
    print(f"Found {len(quotes)} quotes")

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

            # Sync line items if present
            line_items = quote.get('QuoteDtls', [])
            if line_items:
                try:
                    li_summary = line_item_sync.sync_quote_line_items(deal_id, line_items, quote_num)
                    stats['line_items'] += li_summary['created'] + li_summary.get('updated', 0)
                    print(f"           -> Line items: {li_summary['created']} created, {li_summary.get('updated', 0)} updated")
                    if li_summary.get('products_created', 0) > 0:
                        print(f"           -> Products auto-created: {li_summary['products_created']}")
                except Exception as e:
                    print(f"           -> Line items failed: {e}")

        except Exception as e:
            stats['errors'] += 1
            # Show full error details
            error_msg = str(e)
            if hasattr(e, 'response') and e.response:
                error_msg += f"\n           Response: {e.response}"
            print(f"  ERROR: Quote #{quote_num}")
            print(f"           {error_msg[:500]}")

    print("-" * 70)
    print(f"Quotes: {stats['created']} created, {stats['updated']} updated, {stats['skipped']} skipped, {stats['errors']} errors, {stats['line_items']} line items")

    return stats


def sync_orders(epicor_client, hubspot_client, line_item_sync, settings):
    """Sync orders for the specified customers."""
    print("\n" + "=" * 70)
    print("SYNCING ORDERS")
    print("=" * 70)

    transformer = OrderTransformer()
    pipeline_id = settings.hubspot_orders_pipeline_id

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0, 'line_items': 0}

    # Build filter for customer numbers
    cust_filter = " or ".join([f"CustNum eq {c}" for c in CUSTOMER_NUMS])

    # Fetch orders with line items
    print(f"\nFetching orders for {len(CUSTOMER_NUMS)} customers...")
    orders = epicor_client.get_entity(
        service="Erp.BO.SalesOrderSvc",
        entity_set="SalesOrders",
        filter_expr=cust_filter,
        expand="OrderDtls",
        limit=len(CUSTOMER_NUMS) * MAX_ORDERS_PER_CUSTOMER
    )
    print(f"Found {len(orders)} orders")

    for order in orders:
        order_num = order.get('OrderNum')
        cust_num = order.get('CustNum')
        company_id = CUSTOMER_HUBSPOT_MAP.get(cust_num)

        if not company_id:
            print(f"  SKIP: Order {order_num} - Customer {cust_num} not in map")
            stats['skipped'] += 1
            continue

        try:
            # Transform order to deal properties
            hs_properties = transformer.transform(order)

            # Add pipeline ID
            hs_properties['pipeline'] = pipeline_id

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

            # Sync line items if present
            line_items = order.get('OrderDtls', [])
            if line_items:
                try:
                    li_summary = line_item_sync.sync_order_line_items(deal_id, line_items, order_num)
                    stats['line_items'] += li_summary['created'] + li_summary.get('updated', 0)
                    print(f"           -> Line items: {li_summary['created']} created, {li_summary.get('updated', 0)} updated")
                    if li_summary.get('products_created', 0) > 0:
                        print(f"           -> Products auto-created: {li_summary['products_created']}")
                except Exception as e:
                    print(f"           -> Line items failed: {e}")

        except Exception as e:
            stats['errors'] += 1
            error_msg = str(e)
            if hasattr(e, 'response'):
                error_msg += f"\n           Response: {e.response}"
            print(f"  ERROR: Order #{order_num}")
            print(f"           {error_msg[:200]}")

    print("-" * 70)
    print(f"Orders: {stats['created']} created, {stats['updated']} updated, {stats['skipped']} skipped, {stats['errors']} errors, {stats['line_items']} line items")

    return stats


def main():
    """Main function to sync quotes and orders."""
    print("=" * 70)
    print("TEST SYNC: Quotes & Orders for 2022/2023 Customers")
    print("=" * 70)

    # Check if customer mapping is filled
    unmapped = [cust for cust, company_id in CUSTOMER_HUBSPOT_MAP.items() if not company_id]
    if unmapped:
        print("\n❌ ERROR: Customer mapping incomplete!")
        print("Please fill in HubSpot Company IDs in CUSTOMER_HUBSPOT_MAP for:")
        for cust_num in unmapped:
            print(f"  - Customer {cust_num}")
        print("\nYou can get these IDs by running test_sync_customers_2022_2023.py first")
        return 1

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

    line_item_sync = LineItemSync(hubspot_client)
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
    quote_stats = sync_quotes(epicor_client, hubspot_client, line_item_sync, settings)

    # Sync orders
    order_stats = sync_orders(epicor_client, hubspot_client, line_item_sync, settings)

    # Final summary
    print("\n" + "=" * 70)
    print("SYNC COMPLETE - SUMMARY")
    print("=" * 70)
    print(f"\nQUOTES:")
    print(f"  Created:    {quote_stats['created']}")
    print(f"  Updated:    {quote_stats['updated']}")
    print(f"  Skipped:    {quote_stats['skipped']}")
    print(f"  Errors:     {quote_stats['errors']}")
    print(f"  Line Items: {quote_stats['line_items']}")

    print(f"\nORDERS:")
    print(f"  Created:    {order_stats['created']}")
    print(f"  Updated:    {order_stats['updated']}")
    print(f"  Skipped:    {order_stats['skipped']}")
    print(f"  Errors:     {order_stats['errors']}")
    print(f"  Line Items: {order_stats['line_items']}")

    print("\n" + "=" * 70)

    total_errors = quote_stats['errors'] + order_stats['errors']
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
