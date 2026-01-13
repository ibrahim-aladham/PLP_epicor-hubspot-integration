#!/usr/bin/env python3
"""
Audit script to verify Unit Cost in ALL Quotes.

This script:
1. Fetches all quote deals from HubSpot (Quotes pipeline)
2. Gets line items for each deal
3. Compares unit cost between Epicor (Number02) and HubSpot (epicor_line_current_cost)
4. Generates a CSV report of discrepancies

Usage:
    python scripts/audit_unit_cost.py
    python scripts/audit_unit_cost.py --output report.csv

Output:
    - CSV report with all discrepancies
    - Console summary
"""

import sys
import os
import csv
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from src.config import get_settings
from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient


class UnitCostAuditor:
    """Audits unit cost discrepancies between Epicor and HubSpot."""

    def __init__(self, epicor_client: EpicorClient, hubspot_client: HubSpotClient, settings):
        self.epicor = epicor_client
        self.hubspot = hubspot_client
        self.settings = settings

        # Cache for Epicor quote data to avoid repeated API calls
        self.epicor_quote_cache: Dict[int, Dict] = {}

        # Results
        self.discrepancies: List[Dict] = []
        self.all_items: List[Dict] = []

        # Stats
        self.stats = {
            'total_deals': 0,
            'total_line_items': 0,
            'items_with_cost': 0,
            'items_missing_cost': 0,
            'items_with_discrepancy': 0,
            'items_matched': 0,
            'epicor_fetch_errors': 0,
        }

    def get_epicor_quote_lines(self, quote_num: int) -> Optional[List[Dict]]:
        """Fetch quote lines from Epicor (with caching)."""
        if quote_num in self.epicor_quote_cache:
            return self.epicor_quote_cache[quote_num]

        try:
            quotes = self.epicor.get_entity(
                service="Erp.BO.QuoteSvc",
                entity_set="Quotes",
                filter_expr=f"QuoteNum eq {quote_num}",
                expand="QuoteDtls"
            )

            if quotes and len(quotes) > 0:
                lines = quotes[0].get('QuoteDtls', [])
                self.epicor_quote_cache[quote_num] = lines
                return lines
            else:
                self.epicor_quote_cache[quote_num] = []
                return []

        except Exception as e:
            print(f"    ERROR fetching Epicor quote {quote_num}: {e}")
            self.stats['epicor_fetch_errors'] += 1
            return None

    def get_hubspot_line_items(self, deal_id: str) -> List[Dict]:
        """Fetch line items associated with a deal."""
        try:
            # Search for line items associated with this deal
            url = f"https://api.hubapi.com/crm/v3/objects/line_items"
            params = {
                "associations": "deals",
                "properties": "name,sku,quantity,price,amount,epicor_line_item_id,epicor_line_current_cost,hs_cost_of_goods_sold,epicor_cost_source",
                "limit": 100
            }

            import requests
            headers = {
                "Authorization": f"Bearer {self.settings.hubspot_api_key}",
                "Content-Type": "application/json"
            }

            # Use associations API to get line items for this deal
            assoc_url = f"https://api.hubapi.com/crm/v4/objects/deals/{deal_id}/associations/line_items"
            resp = requests.get(assoc_url, headers=headers)

            if resp.status_code != 200:
                return []

            assoc_data = resp.json()
            line_item_ids = [r['toObjectId'] for r in assoc_data.get('results', [])]

            if not line_item_ids:
                return []

            # Batch fetch line items
            line_items = []
            for li_id in line_item_ids:
                li_url = f"https://api.hubapi.com/crm/v3/objects/line_items/{li_id}"
                li_params = {
                    "properties": "name,sku,quantity,price,amount,epicor_line_item_id,epicor_line_current_cost,hs_cost_of_goods_sold,epicor_cost_source"
                }
                li_resp = requests.get(li_url, headers=headers, params=li_params)
                if li_resp.status_code == 200:
                    line_items.append(li_resp.json())

            return line_items

        except Exception as e:
            print(f"    ERROR fetching HubSpot line items for deal {deal_id}: {e}")
            return []

    def get_all_quote_deals(self) -> List[Dict]:
        """Fetch all deals from the Quotes pipeline."""
        print("\nFetching all quote deals from HubSpot...")

        all_deals = []
        after = None
        pipeline_id = self.settings.hubspot_quotes_pipeline_id

        import requests
        headers = {
            "Authorization": f"Bearer {self.settings.hubspot_api_key}",
            "Content-Type": "application/json"
        }

        while True:
            # Search for deals in quotes pipeline
            search_url = "https://api.hubapi.com/crm/v3/objects/deals/search"
            payload = {
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "pipeline",
                        "operator": "EQ",
                        "value": pipeline_id
                    }]
                }],
                "properties": ["dealname", "epicor_quote_number", "pipeline", "dealstage", "amount"],
                "limit": 100
            }

            if after:
                payload["after"] = after

            resp = requests.post(search_url, headers=headers, json=payload)

            if resp.status_code != 200:
                print(f"ERROR fetching deals: {resp.status_code} - {resp.text}")
                break

            data = resp.json()
            results = data.get('results', [])
            all_deals.extend(results)

            # Check for pagination
            paging = data.get('paging', {})
            next_page = paging.get('next', {})
            after = next_page.get('after')

            if not after:
                break

            print(f"  Fetched {len(all_deals)} deals so far...")

        print(f"  Total deals found: {len(all_deals)}")
        return all_deals

    def parse_epicor_line_id(self, epicor_id: str) -> tuple:
        """Parse epicor_line_item_id (e.g., 'Q12345-1') into quote_num and line_num."""
        if not epicor_id or not epicor_id.startswith('Q'):
            return None, None

        try:
            # Format: Q{QuoteNum}-{QuoteLine}
            parts = epicor_id[1:].split('-')
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            pass

        return None, None

    def compare_costs(self, epicor_cost: Any, hubspot_cost: Any) -> tuple:
        """Compare costs, handling None/empty values. Returns (match, epicor_val, hubspot_val)."""
        # Normalize values
        epicor_val = None
        hubspot_val = None

        if epicor_cost is not None and epicor_cost != '':
            try:
                epicor_val = float(epicor_cost)
            except (ValueError, TypeError):
                epicor_val = None

        if hubspot_cost is not None and hubspot_cost != '':
            try:
                hubspot_val = float(hubspot_cost)
            except (ValueError, TypeError):
                hubspot_val = None

        # Both None = match (both missing)
        if epicor_val is None and hubspot_val is None:
            return True, epicor_val, hubspot_val

        # One None, one has value = discrepancy
        if epicor_val is None or hubspot_val is None:
            return False, epicor_val, hubspot_val

        # Both have values, compare with tolerance
        match = abs(epicor_val - hubspot_val) < 0.01
        return match, epicor_val, hubspot_val

    def audit_deal(self, deal: Dict) -> List[Dict]:
        """Audit a single deal's line items."""
        deal_id = deal['id']
        props = deal.get('properties', {})
        deal_name = props.get('dealname', 'Unknown')
        quote_num_str = props.get('epicor_quote_number')

        results = []

        # Get HubSpot line items
        hs_line_items = self.get_hubspot_line_items(deal_id)

        if not hs_line_items:
            return results

        for hs_item in hs_line_items:
            hs_props = hs_item.get('properties', {})
            epicor_line_id = hs_props.get('epicor_line_item_id')

            if not epicor_line_id:
                continue

            quote_num, line_num = self.parse_epicor_line_id(epicor_line_id)

            if quote_num is None:
                continue

            self.stats['total_line_items'] += 1

            # Get Epicor data
            epicor_lines = self.get_epicor_quote_lines(quote_num)

            if epicor_lines is None:
                # Epicor fetch error
                result = {
                    'deal_id': deal_id,
                    'deal_name': deal_name,
                    'quote_num': quote_num,
                    'line_num': line_num,
                    'epicor_line_id': epicor_line_id,
                    'sku': hs_props.get('sku'),
                    'epicor_cost': 'FETCH_ERROR',
                    'hubspot_cost': hs_props.get('epicor_line_current_cost'),
                    'hubspot_cogs': hs_props.get('hs_cost_of_goods_sold'),
                    'status': 'EPICOR_ERROR',
                    'issue': 'Could not fetch from Epicor'
                }
                results.append(result)
                continue

            # Find matching line in Epicor
            epicor_line = None
            for el in epicor_lines:
                if el.get('QuoteLine') == line_num:
                    epicor_line = el
                    break

            if epicor_line is None:
                result = {
                    'deal_id': deal_id,
                    'deal_name': deal_name,
                    'quote_num': quote_num,
                    'line_num': line_num,
                    'epicor_line_id': epicor_line_id,
                    'sku': hs_props.get('sku'),
                    'epicor_cost': 'NOT_FOUND',
                    'hubspot_cost': hs_props.get('epicor_line_current_cost'),
                    'hubspot_cogs': hs_props.get('hs_cost_of_goods_sold'),
                    'status': 'LINE_NOT_FOUND',
                    'issue': 'Line not found in Epicor'
                }
                results.append(result)
                continue

            # Compare costs
            epicor_cost = epicor_line.get('Number02')
            hubspot_cost = hs_props.get('epicor_line_current_cost')
            hubspot_cogs = hs_props.get('hs_cost_of_goods_sold')

            match, epicor_val, hubspot_val = self.compare_costs(epicor_cost, hubspot_cost)

            # Determine status
            if epicor_val is None and hubspot_val is None:
                status = 'BOTH_EMPTY'
                issue = 'Both Epicor and HubSpot have no cost'
                self.stats['items_missing_cost'] += 1
            elif epicor_val is not None and hubspot_val is None:
                status = 'MISSING_IN_HUBSPOT'
                issue = 'Cost exists in Epicor but missing in HubSpot'
                self.stats['items_with_discrepancy'] += 1
            elif epicor_val is None and hubspot_val is not None:
                status = 'MISSING_IN_EPICOR'
                issue = 'Cost in HubSpot but not in Epicor'
                self.stats['items_with_discrepancy'] += 1
            elif match:
                status = 'MATCH'
                issue = ''
                self.stats['items_matched'] += 1
                self.stats['items_with_cost'] += 1
            else:
                status = 'MISMATCH'
                issue = f'Values differ: Epicor={epicor_val}, HubSpot={hubspot_val}'
                self.stats['items_with_discrepancy'] += 1
                self.stats['items_with_cost'] += 1

            result = {
                'deal_id': deal_id,
                'deal_name': deal_name,
                'quote_num': quote_num,
                'line_num': line_num,
                'epicor_line_id': epicor_line_id,
                'sku': hs_props.get('sku') or epicor_line.get('PartNum'),
                'epicor_cost': epicor_val,
                'hubspot_cost': hubspot_val,
                'hubspot_cogs': hubspot_cogs,
                'status': status,
                'issue': issue
            }
            results.append(result)

            # Track discrepancies
            if status not in ['MATCH', 'BOTH_EMPTY']:
                self.discrepancies.append(result)

        return results

    def run_audit(self) -> None:
        """Run the full audit."""
        print("=" * 70)
        print("UNIT COST AUDIT: Epicor vs HubSpot")
        print("=" * 70)

        # Get all quote deals
        deals = self.get_all_quote_deals()
        self.stats['total_deals'] = len(deals)

        if not deals:
            print("No deals found in Quotes pipeline!")
            return

        print(f"\nAuditing {len(deals)} deals...")
        print("-" * 70)

        for i, deal in enumerate(deals):
            deal_id = deal['id']
            deal_name = deal.get('properties', {}).get('dealname', 'Unknown')[:40]
            quote_num = deal.get('properties', {}).get('epicor_quote_number', '?')

            print(f"  [{i+1}/{len(deals)}] Quote #{quote_num} - {deal_name}...", end='')

            results = self.audit_deal(deal)
            self.all_items.extend(results)

            discrepancy_count = sum(1 for r in results if r['status'] not in ['MATCH', 'BOTH_EMPTY'])
            if discrepancy_count > 0:
                print(f" {discrepancy_count} discrepancies")
            else:
                print(" OK")

    def generate_report(self, output_file: str) -> None:
        """Generate CSV report."""
        print(f"\nGenerating report: {output_file}")

        # Write all items report
        all_items_file = output_file.replace('.csv', '_all.csv')
        with open(all_items_file, 'w', newline='', encoding='utf-8') as f:
            if self.all_items:
                writer = csv.DictWriter(f, fieldnames=self.all_items[0].keys())
                writer.writeheader()
                writer.writerows(self.all_items)
        print(f"  Full report: {all_items_file} ({len(self.all_items)} items)")

        # Write discrepancies only
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            if self.discrepancies:
                writer = csv.DictWriter(f, fieldnames=self.discrepancies[0].keys())
                writer.writeheader()
                writer.writerows(self.discrepancies)
            else:
                f.write("No discrepancies found!\n")
        print(f"  Discrepancies: {output_file} ({len(self.discrepancies)} items)")

    def print_summary(self) -> None:
        """Print audit summary."""
        print("\n" + "=" * 70)
        print("AUDIT SUMMARY")
        print("=" * 70)
        print(f"\nDeals audited:           {self.stats['total_deals']}")
        print(f"Total line items:        {self.stats['total_line_items']}")
        print(f"\nCost Status:")
        print(f"  Matched (OK):          {self.stats['items_matched']}")
        print(f"  Both empty:            {self.stats['items_missing_cost']}")
        print(f"  Discrepancies:         {self.stats['items_with_discrepancy']}")
        print(f"  Epicor fetch errors:   {self.stats['epicor_fetch_errors']}")

        if self.discrepancies:
            print(f"\n" + "-" * 70)
            print("DISCREPANCY BREAKDOWN:")

            # Group by status
            status_counts = {}
            for d in self.discrepancies:
                status = d['status']
                status_counts[status] = status_counts.get(status, 0) + 1

            for status, count in sorted(status_counts.items()):
                print(f"  {status}: {count}")

            print(f"\n" + "-" * 70)
            print("SAMPLE DISCREPANCIES (first 10):")
            for d in self.discrepancies[:10]:
                print(f"  Quote #{d['quote_num']}-{d['line_num']} ({d['sku']}): {d['status']}")
                print(f"    Epicor: {d['epicor_cost']} | HubSpot: {d['hubspot_cost']}")


def main():
    parser = argparse.ArgumentParser(description='Audit Unit Cost discrepancies between Epicor and HubSpot')
    parser.add_argument('--output', '-o', default=None, help='Output CSV file path')
    args = parser.parse_args()

    # Default output file with timestamp
    if args.output:
        output_file = args.output
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"reports/unit_cost_discrepancies_{timestamp}.csv"

    # Ensure reports directory exists
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else 'reports', exist_ok=True)

    # Load settings
    print("Loading configuration...")
    settings = get_settings()

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

    print("Connections OK")

    # Run audit
    auditor = UnitCostAuditor(epicor_client, hubspot_client, settings)
    auditor.run_audit()
    auditor.generate_report(output_file)
    auditor.print_summary()

    print("\n" + "=" * 70)
    print("AUDIT COMPLETE")
    print("=" * 70)

    return 0 if not auditor.discrepancies else 1


if __name__ == "__main__":
    sys.exit(main())
