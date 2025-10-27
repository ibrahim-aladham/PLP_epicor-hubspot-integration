#!/usr/bin/env python3
"""
Test API connections for Epicor and HubSpot.

This script verifies that both API clients can successfully connect
to their respective services with the provided credentials.
"""

import sys
import os

# Add parent directory to path to import src modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import get_settings
from src.clients.epicor_client import EpicorClient
from src.clients.hubspot_client import HubSpotClient
from src.utils.logger import setup_logging


def main():
    """Test API connections."""
    print("=" * 80)
    print("Epicor-HubSpot Integration - Connection Test")
    print("=" * 80)
    print()

    # Setup logging
    setup_logging(level="INFO")

    try:
        # Load settings
        print("=Ë Loading configuration...")
        settings = get_settings()
        print(f"   Environment: {settings.environment}")
        print(f"   Epicor Company: {settings.epicor_company}")
        print(f"   Epicor URL: {settings.epicor_base_url}")
        print()

        # Test Epicor connection
        print("= Testing Epicor API connection...")
        print(f"   Base URL: {settings.epicor_base_url}")
        print(f"   Company: {settings.epicor_company}")
        print(f"   Username: {settings.epicor_username}")

        epicor_client = EpicorClient(
            base_url=settings.epicor_base_url,
            company=settings.epicor_company,
            username=settings.epicor_username,
            password=settings.epicor_password,
            api_key=settings.epicor_api_key,
            batch_size=settings.sync_batch_size
        )

        epicor_success = epicor_client.test_connection()

        if epicor_success:
            print("    Epicor connection SUCCESSFUL")

            # Try fetching a small sample
            try:
                print("   =Ê Fetching sample data (1 customer)...")
                customers = epicor_client.get_entity(
                    "Erp.BO.CustomerSvc",
                    "Customers",
                    limit=1
                )
                print(f"    Successfully fetched {len(customers)} customer(s)")
                if customers:
                    print(f"   Sample: {customers[0].get('Name', 'N/A')}")
            except Exception as e:
                print(f"      Sample fetch failed: {e}")
        else:
            print("   L Epicor connection FAILED")

        print()

        # Test HubSpot connection
        print("= Testing HubSpot API connection...")
        print(f"   Base URL: https://api.hubapi.com")
        print(f"   API Key: {settings.hubspot_api_key[:10]}...")

        hubspot_client = HubSpotClient(
            api_key=settings.hubspot_api_key
        )

        hubspot_success = hubspot_client.test_connection()

        if hubspot_success:
            print("    HubSpot connection SUCCESSFUL")

            # Try fetching a small sample
            try:
                print("   =Ê Fetching sample data (1 company)...")
                companies = hubspot_client.search_objects(
                    "companies",
                    filter_groups=[],
                    limit=1
                )
                print(f"    Successfully fetched {len(companies)} company(ies)")
                if companies:
                    props = companies[0].get('properties', {})
                    print(f"   Sample: {props.get('name', 'N/A')}")
            except Exception as e:
                print(f"      Sample fetch failed: {e}")
        else:
            print("   L HubSpot connection FAILED")

        print()
        print("=" * 80)

        # Final status
        if epicor_success and hubspot_success:
            print(" All connections successful!")
            print("=" * 80)
            return 0
        else:
            print("L One or more connections failed")
            print("=" * 80)
            return 1

    except Exception as e:
        print()
        print("=" * 80)
        print(f"L Error: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
