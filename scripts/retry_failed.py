#!/usr/bin/env python3
"""
Retry failed records from backfill migration.

Reads all backfill_failed_*.csv files and retries based on error type:
- MissingCompany: Re-associates deal to company (requires customer to exist in HubSpot)
- HubSpotAPIError (transient): Re-syncs the full order/quote from Epicor
- Quote-to-order lookup: Re-attempts to find and sync the linked order

Usage:
    python scripts/retry_failed.py                    # Retry all failed records
    python scripts/retry_failed.py --dry-run           # Preview what would be retried
    python scripts/retry_failed.py --file <path.csv>   # Retry specific CSV file only
"""

import argparse
import csv
import glob
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.config import get_settings
from src.transformers.order_transformer import OrderTransformer
from src.transformers.quote_transformer import QuoteTransformer
from src.sync.order_sync import OrderSync
from src.sync.quote_sync import QuoteSync
from src.sync.line_item_sync import LineItemSync
from src.utils.error_handler import FailedRecordTracker
from src.utils.logger import setup_logging


logger = logging.getLogger(__name__)


def load_failed_records(file_pattern=None):
    """Load all failed records from CSV files."""
    if file_pattern:
        files = [file_pattern]
    else:
        files = sorted(glob.glob("logs/backfill_failed_*.csv"))

    records = []
    for filepath in files:
        logger.info(f"Loading failed records from {filepath}")
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row['_source_file'] = filepath
                records.append(row)

    # Also load quote-to-order lookup failures from log extraction
    lookup_file = "logs/failed_quote_order_lookups.txt"
    if os.path.exists(lookup_file) and not file_pattern:
        logger.info(f"Loading quote-to-order lookup failures from {lookup_file}")
        with open(lookup_file, 'r') as f:
            for line in f:
                quote_num = line.strip()
                if quote_num:
                    records.append({
                        'entity_type': 'quote',
                        'entity_id': quote_num,
                        'operation': 'order_lookup',
                        'error_message': 'QuoteNum not found on SalesOrder',
                        'error_type': 'QuoteOrderLookup',
                        '_source_file': lookup_file,
                    })

    return records


def retry_transient_order(order_num, epicor, hubspot, order_sync):
    """Re-sync an order that failed due to transient API error."""
    logger.info(f"Retrying order {order_num}...")

    # Fetch from Epicor
    orders = epicor.get_orders(
        expand_line_items=True,
        filter_condition=f"OrderNum eq {order_num}"
    )
    if not orders:
        logger.error(f"Order {order_num} not found in Epicor")
        return False

    order = orders[0]

    # Use the order sync's single-order processing
    transformer = OrderTransformer()
    properties = transformer.transform(order)
    if not properties:
        logger.error(f"Failed to transform order {order_num}")
        return False

    # Check if already exists in HubSpot
    existing = hubspot.get_deal_by_property('epicor_order_number', str(order_num))

    if existing:
        deal_id = existing['id']
        result = hubspot.update_deal(deal_id, properties)
        if result:
            logger.info(f"Updated order {order_num} (deal {deal_id})")
        else:
            logger.error(f"Failed to update order {order_num}")
            return False
    else:
        result = hubspot.create_deal(properties)
        if result:
            deal_id = result['id']
            logger.info(f"Created order {order_num} (deal {deal_id})")
        else:
            logger.error(f"Failed to create order {order_num}")
            return False

    # Sync line items
    line_item_sync = LineItemSync(hubspot)
    order_lines = order.get('OrderDtls', [])
    if order_lines:
        li_result = line_item_sync.sync_order_line_items(deal_id, order_lines, order_num)
        logger.info(f"Order {order_num} line items: {li_result}")

    # Associate to company
    cust_num = order.get('CustNum')
    if cust_num:
        company = hubspot.get_company_by_property('epicor_customer_number', str(cust_num))
        if company:
            hubspot.associate_deal_to_company(deal_id, company['id'])
            logger.info(f"Associated order {order_num} to company {cust_num}")
        else:
            logger.warning(f"Company {cust_num} not found in HubSpot for order {order_num}")

    return True


def retry_missing_company_with_epicor(entity_type, entity_id, epicor, hubspot, quote_sync, order_sync):
    """Re-sync a deal that failed due to missing company. Creates deal if needed."""
    logger.info(f"Retrying {entity_type} {entity_id} (missing company)...")

    # Fetch from Epicor
    if entity_type == 'quote':
        prop_name = 'epicor_quote_number'
        records = epicor.get_quotes(
            expand_line_items=True,
            filter_condition=f"QuoteNum eq {entity_id}"
        )
    else:
        prop_name = 'epicor_order_number'
        records = epicor.get_orders(
            expand_line_items=True,
            filter_condition=f"OrderNum eq {entity_id}"
        )

    if not records:
        logger.error(f"{entity_type} {entity_id} not found in Epicor")
        return False

    record = records[0]

    # Check if deal already exists
    deal = hubspot.get_deal_by_property(prop_name, str(entity_id))

    if deal:
        # Deal exists, just re-associate
        deal_id = deal['id']
        logger.info(f"{entity_type} {entity_id} exists (deal {deal_id}), re-associating...")
    else:
        # Deal doesn't exist, create it via the sync module
        logger.info(f"{entity_type} {entity_id} not in HubSpot, creating...")
        if entity_type == 'quote':
            result = quote_sync.sync_all_quotes(filter_condition=f"QuoteNum eq {entity_id}")
        else:
            result = order_sync.sync_all_orders(filter_condition=f"OrderNum eq {entity_id}")
        logger.info(f"Sync result: {result}")
        return True  # sync module handles everything including association

    # Associate to company
    cust_num = record.get('CustNum')
    if cust_num:
        company = hubspot.get_company_by_property('epicor_customer_number', str(cust_num))
        if company:
            hubspot.associate_deal_to_company(deal_id, company['id'])
            logger.info(f"Associated {entity_type} {entity_id} to company {cust_num}")
        else:
            logger.error(f"Company {cust_num} still not found in HubSpot")
            return False

    return True


def retry_quote_order_lookup(quote_num, epicor, hubspot, quote_sync):
    """Re-attempt to find and sync the linked order for a converted quote."""
    logger.info(f"Retrying quote-to-order lookup for quote {quote_num}...")

    # Find the quote deal in HubSpot
    quote_deal = hubspot.get_deal_by_property('epicor_quote_number', str(quote_num))
    if not quote_deal:
        logger.error(f"Quote {quote_num} not found in HubSpot")
        return False

    quote_deal_id = quote_deal['id']

    # Find company for association
    quotes = epicor.get_quotes(filter_condition=f"QuoteNum eq {quote_num}")
    company_id = None
    if quotes:
        cust_num = quotes[0].get('CustNum')
        if cust_num:
            company = hubspot.get_company_by_property('epicor_customer_number', str(cust_num))
            if company:
                company_id = company['id']

    # Use quote_sync's _handle_converted_order which fetches the order from Epicor
    quote_sync._handle_converted_order(quote_num, quote_deal_id, company_id)
    return True


def main():
    parser = argparse.ArgumentParser(description='Retry failed backfill records')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--file', type=str, help='Retry specific CSV file only')
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)

    # Load failed records
    records = load_failed_records(args.file)
    if not records:
        logger.info("No failed records found.")
        return

    # Categorize failures
    transient_orders = []
    transient_quotes = []
    missing_company = []
    quote_order_lookups = []

    for r in records:
        error_type = r.get('error_type', '')
        error_msg = r.get('error_message', '')
        entity_type = r.get('entity_type', '')
        entity_id = r.get('entity_id', '')

        if 'MissingCompany' in error_type or 'not found in HubSpot' in error_msg:
            missing_company.append(r)
        elif 'QuoteOrderLookup' in error_type:
            quote_order_lookups.append(r)
        elif 'QuoteNum' in error_msg and 'SalesOrder' in error_msg:
            quote_order_lookups.append(r)
        elif '429' in error_msg or '500' in error_msg or 'too many' in error_msg.lower():
            if entity_type == 'order':
                transient_orders.append(r)
            else:
                transient_quotes.append(r)
        else:
            logger.warning(f"Unknown error type for {entity_type} {entity_id}: {error_msg[:100]}")

    print("\n" + "=" * 60)
    print("RETRY FAILED RECORDS")
    print("=" * 60)
    print(f"\nTransient order errors:      {len(transient_orders)}")
    print(f"Transient quote errors:      {len(transient_quotes)}")
    print(f"Missing company associations: {len(missing_company)}")
    print(f"Quote-to-order lookups:      {len(quote_order_lookups)}")
    print(f"Total to retry:              {len(records)}")
    print()

    if args.dry_run:
        print("DRY RUN - No changes will be made.\n")
        for r in records:
            print(f"  Would retry: {r['entity_type']} {r['entity_id']} ({r.get('error_type', 'unknown')})")
        return

    # Initialize clients
    epicor = EpicorClient(
        base_url=settings.epicor_base_url,
        company=settings.epicor_company,
        username=settings.epicor_username,
        password=settings.epicor_password,
        api_key=settings.epicor_api_key,
    )
    hubspot = HubSpotClient(api_key=settings.hubspot_api_key)

    if not epicor.test_connection():
        logger.error("Epicor connection failed")
        return
    if not hubspot.test_connection():
        logger.error("HubSpot connection failed")
        return

    logger.info("Connections OK\n")

    failed_tracker = FailedRecordTracker("logs/retry_failed.csv")
    order_sync = OrderSync(epicor, hubspot, failed_tracker)
    quote_sync = QuoteSync(epicor, hubspot, failed_tracker)

    results = {'success': 0, 'failed': 0}

    # 1. Retry transient order errors
    for r in transient_orders:
        try:
            if retry_transient_order(int(r['entity_id']), epicor, hubspot, order_sync):
                results['success'] += 1
            else:
                results['failed'] += 1
        except Exception as e:
            logger.error(f"Failed to retry order {r['entity_id']}: {e}")
            results['failed'] += 1

    # 2. Retry missing company associations
    for r in missing_company:
        try:
            if retry_missing_company_with_epicor(
                r['entity_type'], int(r['entity_id']), epicor, hubspot, quote_sync, order_sync
            ):
                results['success'] += 1
            else:
                results['failed'] += 1
        except Exception as e:
            logger.error(f"Failed to retry {r['entity_type']} {r['entity_id']}: {e}")
            results['failed'] += 1

    # 3. Retry quote-to-order lookups (uses fixed OrderDtlSearchSvc)
    for r in quote_order_lookups:
        try:
            quote_num = int(r['entity_id'])
            if retry_quote_order_lookup(quote_num, epicor, hubspot, quote_sync):
                results['success'] += 1
            else:
                results['failed'] += 1
        except Exception as e:
            logger.error(f"Failed to retry quote {r['entity_id']} order lookup: {e}")
            results['failed'] += 1

    # Summary
    print("\n" + "=" * 60)
    print("RETRY COMPLETE")
    print("=" * 60)
    print(f"Success: {results['success']}")
    print(f"Failed:  {results['failed']}")

    if failed_tracker.has_failures():
        print(f"\nNew failures logged to: logs/retry_failed.csv")
        failed_tracker.close()
    print("=" * 60)


if __name__ == '__main__':
    main()
