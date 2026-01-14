#!/usr/bin/env python3
"""
Historical Data Migration Script.

Imports historical quotes and orders from Epicor to HubSpot.
Processes data in year-based batches with progress tracking.

Usage:
    # Sync all historical data (2020-present)
    python scripts/backfill_historical.py

    # Sync specific year range
    python scripts/backfill_historical.py --start-year 2022 --end-year 2023

    # Sync only customers first
    python scripts/backfill_historical.py --customers-only

    # Sync only quotes and orders (assumes customers exist)
    python scripts/backfill_historical.py --skip-customers

    # Dry run (show what would be synced without making changes)
    python scripts/backfill_historical.py --dry-run

    # Resume from last checkpoint (if previous run failed)
    python scripts/backfill_historical.py --resume

    # Reset checkpoint and start fresh
    python scripts/backfill_historical.py --reset

WARNING: This will create/update REAL data in HubSpot!
"""

import sys
import os
import json
import argparse
from datetime import datetime
from typing import Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from src.config import get_settings
from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.sync.customer_sync import CustomerSync
from src.sync.quote_sync import QuoteSync
from src.sync.order_sync import OrderSync
from src.utils.error_handler import FailedRecordTracker
from src.utils.logger import setup_logging


# Default checkpoint file location
CHECKPOINT_FILE = "logs/backfill_checkpoint.json"


class MigrationCheckpoint:
    """
    Tracks migration progress for resume capability.

    Saves state to a JSON file so migration can resume after failures.
    """

    def __init__(self, checkpoint_file: str = CHECKPOINT_FILE):
        self.checkpoint_file = checkpoint_file
        self.state = {
            'phase': None,  # 'customers', 'quotes', 'orders', 'complete'
            'customers_done': False,
            'quotes_years_done': [],  # List of completed years
            'orders_years_done': [],  # List of completed years
            'start_year': None,
            'end_year': None,
            'started_at': None,
            'last_updated': None,
            'stats': {
                'customers': {'total': 0, 'created': 0, 'updated': 0, 'errors': 0},
                'quotes': {'total': 0, 'created': 0, 'updated': 0, 'errors': 0},
                'orders': {'total': 0, 'created': 0, 'updated': 0, 'errors': 0}
            }
        }

    def load(self) -> bool:
        """Load checkpoint from file. Returns True if checkpoint exists."""
        if not os.path.exists(self.checkpoint_file):
            return False

        try:
            with open(self.checkpoint_file, 'r') as f:
                self.state = json.load(f)
            return True
        except Exception as e:
            print(f"Warning: Could not load checkpoint: {e}")
            return False

    def save(self) -> None:
        """Save checkpoint to file."""
        self.state['last_updated'] = datetime.now().isoformat()

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.checkpoint_file) if os.path.dirname(self.checkpoint_file) else 'logs', exist_ok=True)

        with open(self.checkpoint_file, 'w') as f:
            json.dump(self.state, f, indent=2)

    def reset(self) -> None:
        """Reset checkpoint (delete file)."""
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
            print(f"Checkpoint reset: {self.checkpoint_file}")

    def start_migration(self, start_year: int, end_year: int) -> None:
        """Initialize a new migration."""
        self.state['started_at'] = datetime.now().isoformat()
        self.state['start_year'] = start_year
        self.state['end_year'] = end_year
        self.state['phase'] = 'customers'
        self.save()

    def complete_customers(self, stats: Dict) -> None:
        """Mark customers phase as complete."""
        self.state['customers_done'] = True
        self.state['phase'] = 'quotes'
        self.state['stats']['customers'] = stats
        self.save()

    def complete_quote_year(self, year: int, stats: Dict) -> None:
        """Mark a quote year as complete."""
        if year not in self.state['quotes_years_done']:
            self.state['quotes_years_done'].append(year)
        # Accumulate stats
        for key in ['total', 'created', 'updated', 'errors']:
            self.state['stats']['quotes'][key] += stats.get(key, 0)
        self.save()

    def complete_quotes(self) -> None:
        """Mark quotes phase as complete."""
        self.state['phase'] = 'orders'
        self.save()

    def complete_order_year(self, year: int, stats: Dict) -> None:
        """Mark an order year as complete."""
        if year not in self.state['orders_years_done']:
            self.state['orders_years_done'].append(year)
        # Accumulate stats
        for key in ['total', 'created', 'updated', 'errors']:
            self.state['stats']['orders'][key] += stats.get(key, 0)
        self.save()

    def complete_orders(self) -> None:
        """Mark orders phase as complete."""
        self.state['phase'] = 'complete'
        self.save()

    def complete_migration(self) -> None:
        """Mark entire migration as complete."""
        self.state['phase'] = 'complete'
        self.save()
        # Optionally remove checkpoint file on success
        # self.reset()

    def should_skip_customers(self) -> bool:
        """Check if customers phase should be skipped."""
        return self.state.get('customers_done', False)

    def should_skip_quote_year(self, year: int) -> bool:
        """Check if a quote year should be skipped."""
        return year in self.state.get('quotes_years_done', [])

    def should_skip_order_year(self, year: int) -> bool:
        """Check if an order year should be skipped."""
        return year in self.state.get('orders_years_done', [])

    def get_resume_info(self) -> str:
        """Get human-readable resume info."""
        if not self.state.get('started_at'):
            return "No checkpoint found"

        info = [
            f"Started: {self.state['started_at']}",
            f"Last updated: {self.state.get('last_updated', 'Unknown')}",
            f"Current phase: {self.state.get('phase', 'Unknown')}",
            f"Year range: {self.state.get('start_year')}-{self.state.get('end_year')}",
            f"Customers done: {self.state.get('customers_done', False)}",
            f"Quote years done: {self.state.get('quotes_years_done', [])}",
            f"Order years done: {self.state.get('orders_years_done', [])}"
        ]
        return "\n  ".join(info)


def get_date_filter(start_year: int, end_year: int, date_field: str = "EntryDate") -> str:
    """
    Build OData date filter for a year range.

    Args:
        start_year: Start year (inclusive)
        end_year: End year (inclusive)
        date_field: The date field to filter on

    Returns:
        OData filter string
    """
    start_date = f"{start_year}-01-01T00:00:00Z"
    end_date = f"{end_year + 1}-01-01T00:00:00Z"
    return f"{date_field} ge {start_date} and {date_field} lt {end_date}"


def sync_customers(
    epicor_client: EpicorClient,
    hubspot_client: HubSpotClient,
    failed_tracker: FailedRecordTracker,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Sync all customers from Epicor to HubSpot.

    Args:
        epicor_client: Epicor API client
        hubspot_client: HubSpot API client
        failed_tracker: Failed record tracker
        dry_run: If True, only show what would be synced

    Returns:
        Sync summary
    """
    print("\n" + "=" * 70)
    print("PHASE 1: CUSTOMER SYNC")
    print("=" * 70)

    if dry_run:
        # Count customers
        customers = epicor_client.get_customers()
        print(f"\n[DRY RUN] Would sync {len(customers)} customers")
        return {'total': len(customers), 'created': 0, 'updated': 0, 'errors': 0, 'dry_run': True}

    customer_sync = CustomerSync(epicor_client, hubspot_client, failed_tracker)
    return customer_sync.sync_all_customers()


def sync_quotes_by_year(
    epicor_client: EpicorClient,
    hubspot_client: HubSpotClient,
    failed_tracker: FailedRecordTracker,
    start_year: int,
    end_year: int,
    dry_run: bool = False,
    checkpoint: MigrationCheckpoint = None
) -> Dict[str, Any]:
    """
    Sync quotes for a specific year range.

    Args:
        epicor_client: Epicor API client
        hubspot_client: HubSpot API client
        failed_tracker: Failed record tracker
        start_year: Start year (inclusive)
        end_year: End year (inclusive)
        dry_run: If True, only show what would be synced
        checkpoint: Migration checkpoint for resume capability

    Returns:
        Sync summary
    """
    print("\n" + "=" * 70)
    print(f"PHASE 2: QUOTE SYNC ({start_year}-{end_year})")
    print("=" * 70)

    total_stats = {'total': 0, 'created': 0, 'updated': 0, 'errors': 0}

    for year in range(start_year, end_year + 1):
        # Check if this year was already completed
        if checkpoint and checkpoint.should_skip_quote_year(year):
            print(f"\n--- Skipping quotes for {year} (already completed) ---")
            continue

        print(f"\n--- Processing quotes for {year} ---")

        date_filter = get_date_filter(year, year, "EntryDate")

        if dry_run:
            # Count quotes for this year
            quotes = epicor_client.get_quotes(
                expand_line_items=False,
                filter_condition=date_filter
            )
            print(f"[DRY RUN] Would sync {len(quotes)} quotes from {year}")
            total_stats['total'] += len(quotes)
            continue

        quote_sync = QuoteSync(epicor_client, hubspot_client, failed_tracker)
        result = quote_sync.sync_all_quotes(filter_condition=date_filter)

        year_stats = {
            'total': result.get('total', 0),
            'created': result.get('created', 0),
            'updated': result.get('updated', 0),
            'errors': result.get('errors', 0)
        }

        total_stats['total'] += year_stats['total']
        total_stats['created'] += year_stats['created']
        total_stats['updated'] += year_stats['updated']
        total_stats['errors'] += year_stats['errors']

        # Save checkpoint after each year
        if checkpoint:
            checkpoint.complete_quote_year(year, year_stats)

        print(f"Year {year}: {year_stats['total']} quotes, "
              f"{year_stats['created']} created, {year_stats['updated']} updated, "
              f"{year_stats['errors']} errors")

    # Mark quotes phase complete
    if checkpoint and not dry_run:
        checkpoint.complete_quotes()

    return total_stats


def sync_orders_by_year(
    epicor_client: EpicorClient,
    hubspot_client: HubSpotClient,
    failed_tracker: FailedRecordTracker,
    start_year: int,
    end_year: int,
    dry_run: bool = False,
    checkpoint: MigrationCheckpoint = None
) -> Dict[str, Any]:
    """
    Sync orders for a specific year range.

    Args:
        epicor_client: Epicor API client
        hubspot_client: HubSpot API client
        failed_tracker: Failed record tracker
        start_year: Start year (inclusive)
        end_year: End year (inclusive)
        dry_run: If True, only show what would be synced
        checkpoint: Migration checkpoint for resume capability

    Returns:
        Sync summary
    """
    print("\n" + "=" * 70)
    print(f"PHASE 3: ORDER SYNC ({start_year}-{end_year})")
    print("=" * 70)

    total_stats = {'total': 0, 'created': 0, 'updated': 0, 'errors': 0}

    for year in range(start_year, end_year + 1):
        # Check if this year was already completed
        if checkpoint and checkpoint.should_skip_order_year(year):
            print(f"\n--- Skipping orders for {year} (already completed) ---")
            continue

        print(f"\n--- Processing orders for {year} ---")

        date_filter = get_date_filter(year, year, "OrderDate")

        if dry_run:
            # Count orders for this year
            orders = epicor_client.get_orders(
                expand_line_items=False,
                filter_condition=date_filter
            )
            print(f"[DRY RUN] Would sync {len(orders)} orders from {year}")
            total_stats['total'] += len(orders)
            continue

        order_sync = OrderSync(epicor_client, hubspot_client, failed_tracker)
        result = order_sync.sync_all_orders(filter_condition=date_filter)

        year_stats = {
            'total': result.get('total', 0),
            'created': result.get('created', 0),
            'updated': result.get('updated', 0),
            'errors': result.get('errors', 0)
        }

        total_stats['total'] += year_stats['total']
        total_stats['created'] += year_stats['created']
        total_stats['updated'] += year_stats['updated']
        total_stats['errors'] += year_stats['errors']

        # Save checkpoint after each year
        if checkpoint:
            checkpoint.complete_order_year(year, year_stats)

        print(f"Year {year}: {year_stats['total']} orders, "
              f"{year_stats['created']} created, {year_stats['updated']} updated, "
              f"{year_stats['errors']} errors")

    # Mark orders phase complete
    if checkpoint and not dry_run:
        checkpoint.complete_orders()

    return total_stats


def main():
    parser = argparse.ArgumentParser(
        description='Historical Data Migration: Epicor to HubSpot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full migration (all years, all data)
    python scripts/backfill_historical.py

    # Migrate specific years
    python scripts/backfill_historical.py --start-year 2022 --end-year 2023

    # Migrate only customers
    python scripts/backfill_historical.py --customers-only

    # Migrate quotes/orders only (customers already synced)
    python scripts/backfill_historical.py --skip-customers

    # Preview what would be synced
    python scripts/backfill_historical.py --dry-run

    # Resume from last checkpoint (if previous run failed)
    python scripts/backfill_historical.py --resume

    # Reset checkpoint and start fresh
    python scripts/backfill_historical.py --reset
        """
    )

    parser.add_argument(
        '--start-year', type=int, default=2020,
        help='Start year for historical data (default: 2020)'
    )
    parser.add_argument(
        '--end-year', type=int, default=datetime.now().year,
        help='End year for historical data (default: current year)'
    )
    parser.add_argument(
        '--customers-only', action='store_true',
        help='Sync only customers (skip quotes and orders)'
    )
    parser.add_argument(
        '--skip-customers', action='store_true',
        help='Skip customer sync (assumes customers already exist in HubSpot)'
    )
    parser.add_argument(
        '--quotes-only', action='store_true',
        help='Sync only quotes (skip customers and orders)'
    )
    parser.add_argument(
        '--orders-only', action='store_true',
        help='Sync only orders (skip customers and quotes)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview what would be synced without making changes'
    )
    parser.add_argument(
        '--resume', action='store_true',
        help='Resume from last checkpoint (if previous run failed)'
    )
    parser.add_argument(
        '--reset', action='store_true',
        help='Reset checkpoint and start fresh'
    )
    parser.add_argument(
        '--output', '-o', type=str, default=None,
        help='Path for failed records CSV file'
    )

    args = parser.parse_args()

    # Handle reset
    checkpoint = MigrationCheckpoint()
    if args.reset:
        checkpoint.reset()
        print("Checkpoint has been reset. Run again without --reset to start fresh.")
        return 0

    # Validate year range
    if args.start_year > args.end_year:
        print("ERROR: start-year must be <= end-year")
        return 1

    # Handle resume
    resuming = False
    if args.resume:
        if checkpoint.load():
            resuming = True
            print("=" * 70)
            print("RESUMING HISTORICAL DATA MIGRATION")
            print("=" * 70)
            print(f"\nCheckpoint found:")
            print(f"  {checkpoint.get_resume_info()}")
            print()

            # Use year range from checkpoint
            args.start_year = checkpoint.state.get('start_year', args.start_year)
            args.end_year = checkpoint.state.get('end_year', args.end_year)
        else:
            print("No checkpoint found. Starting fresh migration.")

    # Setup
    print("=" * 70)
    print("HISTORICAL DATA MIGRATION" + (" (RESUMED)" if resuming else ""))
    print("Epicor -> HubSpot")
    print("=" * 70)
    print(f"\nYear range: {args.start_year} - {args.end_year}")
    if args.dry_run:
        print("MODE: DRY RUN (no changes will be made)")
    if resuming:
        print("MODE: RESUMING from checkpoint")
    print()

    # Load configuration
    print("Loading configuration...")
    settings = get_settings()
    setup_logging()

    # Initialize clients
    print("Initializing API clients...")
    epicor_client = EpicorClient(
        base_url=settings.epicor_base_url,
        company=settings.epicor_company,
        username=settings.epicor_username,
        password=settings.epicor_password,
        api_key=settings.epicor_api_key,
        batch_size=settings.sync_batch_size
    )

    hubspot_client = HubSpotClient(api_key=settings.hubspot_api_key)

    # Test connections
    print("Testing connections...")
    if not epicor_client.test_connection():
        print("ERROR: Epicor connection failed!")
        return 1

    if not hubspot_client.test_connection():
        print("ERROR: HubSpot connection failed!")
        return 1

    print("Connections OK\n")

    # Initialize failed record tracker
    if args.output:
        failed_records_file = args.output
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        failed_records_file = f"logs/backfill_failed_{timestamp}.csv"

    failed_tracker = FailedRecordTracker(failed_records_file)

    # Track overall stats
    start_time = datetime.now()
    summary = {
        'customers': None,
        'quotes': None,
        'orders': None
    }

    # Initialize checkpoint for new migration
    if not resuming and not args.dry_run:
        checkpoint.start_migration(args.start_year, args.end_year)

    try:
        # Phase 1: Customers
        skip_customers = (
            args.skip_customers or
            args.quotes_only or
            args.orders_only or
            (resuming and checkpoint.should_skip_customers())
        )

        if not skip_customers:
            summary['customers'] = sync_customers(
                epicor_client, hubspot_client, failed_tracker, args.dry_run
            )
            if not args.dry_run:
                checkpoint.complete_customers(summary['customers'])
        elif resuming and checkpoint.should_skip_customers():
            print("\n--- Skipping customers (already completed) ---")

        if args.customers_only:
            return 0

        # Phase 2: Quotes
        if not args.orders_only:
            summary['quotes'] = sync_quotes_by_year(
                epicor_client, hubspot_client, failed_tracker,
                args.start_year, args.end_year, args.dry_run,
                checkpoint if not args.dry_run else None
            )

        if args.quotes_only:
            return 0

        # Phase 3: Orders
        if not args.quotes_only:
            summary['orders'] = sync_orders_by_year(
                epicor_client, hubspot_client, failed_tracker,
                args.start_year, args.end_year, args.dry_run,
                checkpoint if not args.dry_run else None
            )

        # Mark migration complete
        if not args.dry_run:
            checkpoint.complete_migration()

    finally:
        # Close tracker
        failed_tracker.close()

    # Final summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    print(f"\nDuration: {duration:.2f} seconds ({duration/60:.1f} minutes)")

    if summary['customers']:
        c = summary['customers']
        print(f"\nCustomers: {c.get('total', 0)} total, "
              f"{c.get('created', 0)} created, {c.get('updated', 0)} updated, "
              f"{c.get('errors', 0)} errors")

    if summary['quotes']:
        q = summary['quotes']
        print(f"Quotes: {q.get('total', 0)} total, "
              f"{q.get('created', 0)} created, {q.get('updated', 0)} updated, "
              f"{q.get('errors', 0)} errors")

    if summary['orders']:
        o = summary['orders']
        print(f"Orders: {o.get('total', 0)} total, "
              f"{o.get('created', 0)} created, {o.get('updated', 0)} updated, "
              f"{o.get('errors', 0)} errors")

    if failed_tracker.has_failures():
        print(f"\nFailed records: {failed_tracker.output_file}")
        fail_summary = failed_tracker.get_summary()
        print(f"  Total failures: {fail_summary['total_failures']}")
        for entity_type, count in fail_summary.get('by_entity_type', {}).items():
            print(f"    {entity_type}: {count}")

    print("\n" + "=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
