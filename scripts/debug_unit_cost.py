#!/usr/bin/env python3
"""
Debug script to investigate missing Unit Cost issue.

This script:
1. Fetches a specific quote from Epicor and shows Number02 field
2. Shows what data is being transformed
3. Helps identify where the issue is

Usage:
    python scripts/debug_unit_cost.py <quote_number>
    python scripts/debug_unit_cost.py 12345
"""

import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from src.config import get_settings
from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.transformers.line_item_transformer import LineItemTransformer


def debug_quote(quote_num: int):
    """Debug a specific quote's unit cost data."""
    print("=" * 70)
    print(f"DEBUGGING UNIT COST FOR QUOTE #{quote_num}")
    print("=" * 70)

    # Load settings
    settings = get_settings()

    # Initialize clients
    epicor_client = EpicorClient(
        base_url=settings.epicor_base_url,
        company=settings.epicor_company,
        username=settings.epicor_username,
        password=settings.epicor_password,
        api_key=settings.epicor_api_key,
        batch_size=settings.sync_batch_size
    )

    hubspot_client = HubSpotClient(api_key=settings.hubspot_api_key)
    transformer = LineItemTransformer()

    # STEP 1: Fetch raw data from Epicor
    print("\n[STEP 1] Fetching quote from Epicor...")
    print("-" * 70)

    try:
        quotes = epicor_client.get_entity(
            service="Erp.BO.QuoteSvc",
            entity_set="Quotes",
            filter_expr=f"QuoteNum eq {quote_num}",
            expand="QuoteDtls"
        )

        if not quotes:
            print(f"ERROR: Quote {quote_num} not found in Epicor!")
            return

        quote = quotes[0]
        print(f"Quote found: #{quote.get('QuoteNum')}")
        print(f"Customer: {quote.get('CustNum')}")

        line_items = quote.get('QuoteDtls', [])
        print(f"Line items count: {len(line_items)}")

    except Exception as e:
        print(f"ERROR fetching from Epicor: {e}")
        return

    # STEP 2: Show raw Epicor data for each line
    print("\n[STEP 2] Raw Epicor line item data (cost-related fields):")
    print("-" * 70)

    for i, line in enumerate(line_items):
        print(f"\n  Line {i+1} (QuoteLine: {line.get('QuoteLine')}):")
        print(f"    PartNum:       {line.get('PartNum')}")
        print(f"    LineDesc:      {line.get('LineDesc', '')[:50]}")
        print(f"    OrderQty:      {line.get('OrderQty')}")
        print(f"    ExpUnitPrice:  {line.get('ExpUnitPrice')}")
        print(f"    ExtPriceDtl:   {line.get('ExtPriceDtl')}")
        print(f"    ---- COST FIELDS ----")
        print(f"    Number02:      {line.get('Number02')} <-- This is the Unit Cost source")
        print(f"    Character06:   {line.get('Character06')} <-- Cost Source")
        print(f"    Character01:   {line.get('Character01')}")
        print(f"    QuoteComment:  {line.get('QuoteComment', '')[:50]}")

    # STEP 3: Show transformed data
    print("\n[STEP 3] Transformed properties (what gets sent to HubSpot):")
    print("-" * 70)

    for i, line in enumerate(line_items):
        transformed = transformer.transform_quote_line(line, quote_num)
        print(f"\n  Line {i+1}:")
        for key, value in transformed.items():
            if 'cost' in key.lower() or key in ['sku', 'name', 'price', 'amount']:
                print(f"    {key}: {value}")

    # STEP 4: Check HubSpot for this quote's line items
    print("\n[STEP 4] Checking HubSpot for existing line items...")
    print("-" * 70)

    for i, line in enumerate(line_items):
        epicor_id = f"Q{quote_num}-{line.get('QuoteLine')}"
        try:
            existing = hubspot_client.get_line_item_by_epicor_id(epicor_id)
            if existing:
                props = existing.get('properties', {})
                print(f"\n  Line item {epicor_id} found in HubSpot (ID: {existing.get('id')}):")
                print(f"    hs_cost_of_goods_sold:     {props.get('hs_cost_of_goods_sold')}")
                print(f"    epicor_line_current_cost:  {props.get('epicor_line_current_cost')}")
                print(f"    epicor_cost_source:        {props.get('epicor_cost_source')}")
            else:
                print(f"\n  Line item {epicor_id} NOT found in HubSpot")
        except Exception as e:
            print(f"\n  Error checking {epicor_id}: {e}")

    # STEP 5: Check if HubSpot properties exist
    print("\n[STEP 5] Checking HubSpot custom properties exist...")
    print("-" * 70)

    properties_to_check = [
        'epicor_line_current_cost',
        'hs_cost_of_goods_sold',
        'epicor_cost_source'
    ]

    try:
        import requests
        headers = {
            "Authorization": f"Bearer {settings.hubspot_api_key}",
            "Content-Type": "application/json"
        }

        for prop_name in properties_to_check:
            url = f"https://api.hubapi.com/crm/v3/properties/line_items/{prop_name}"
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                prop = resp.json()
                print(f"  {prop_name}: EXISTS (type: {prop.get('type')}, fieldType: {prop.get('fieldType')})")
            else:
                print(f"  {prop_name}: NOT FOUND (status: {resp.status_code})")
    except Exception as e:
        print(f"  Error checking properties: {e}")

    print("\n" + "=" * 70)
    print("DEBUG COMPLETE")
    print("=" * 70)
    print("\nAnalysis:")
    print("- If Number02 is empty/None in Epicor -> Data issue in Epicor")
    print("- If Number02 has data but HubSpot property is empty -> Transform/sync issue")
    print("- If HubSpot property doesn't exist -> Need to create custom property in HubSpot")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_unit_cost.py <quote_number>")
        print("Example: python scripts/debug_unit_cost.py 12345")
        return 1

    try:
        quote_num = int(sys.argv[1])
    except ValueError:
        print("ERROR: Quote number must be an integer")
        return 1

    debug_quote(quote_num)
    return 0


if __name__ == "__main__":
    sys.exit(main())
