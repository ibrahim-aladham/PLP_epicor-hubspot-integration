"""
Fetch Sales Rep and HubSpot Owner data to help create mapping.

This script fetches all sales reps from Epicor and all owners from HubSpot,
then outputs them to a JSON file to help you create the sales_rep_mapping.json file.

Usage:
    python scripts/fetch_sales_rep_mapping_data.py

Output:
    Creates config/sales_rep_mapping_data.json with:
    - List of all Epicor sales rep codes
    - List of all HubSpot owners (ID, name, email)
"""

import os
import sys
import json
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.clients.epicor_client import EpicorClient
from src.config import settings

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_epicor_sales_reps():
    """
    Fetch all sales reps from Epicor.

    Returns:
        List of dictionaries with sales rep information
    """
    logger.info("Fetching sales reps from Epicor...")

    try:
        # Disable SSL warnings for self-signed certificates
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        client = EpicorClient(
            base_url=settings.epicor_base_url,
            username=settings.epicor_username,
            password=settings.epicor_password,
            api_key=settings.epicor_api_key,
            company=settings.epicor_company
        )

        # Disable SSL verification for self-signed certificate
        client.session.verify = False

        # Query Epicor for sales reps from SalesRep table
        # Note: EmailAddress field might not exist or have different name
        sales_reps = client.get_entity(
            service="Erp.BO.SalesRepSvc",
            entity_set="SalesReps",
            select="SalesRepCode,Name,EMailAddress,RoleCode",  # Changed EmailAddress to EMailAddress
            orderby="SalesRepCode"
        )

        logger.info(f"Found {len(sales_reps)} sales reps in Epicor")

        # Format the data
        formatted_reps = []
        for rep in sales_reps:
            formatted_reps.append({
                "code": rep.get('SalesRepCode'),
                "name": rep.get('Name', ''),
                "email": rep.get('EMailAddress', ''),  # Try EMailAddress instead
                "role": rep.get('RoleCode', '')
            })

        return formatted_reps

    except Exception as e:
        logger.error(f"Failed to fetch sales reps from Epicor: {e}")
        return []


def fetch_hubspot_owners():
    """
    Fetch all owners from HubSpot using the Owners API directly.

    Returns:
        List of dictionaries with owner information
    """
    logger.info("Fetching owners from HubSpot...")

    try:
        # Check if API key is loaded
        api_key = settings.hubspot_api_key
        if not api_key:
            logger.error("HubSpot API key is not set!")
            return []

        logger.debug(f"Using HubSpot API key: {api_key[:10]}...{api_key[-4:]}")

        # Make direct HTTP request to HubSpot API
        base_url = "https://api.hubapi.com"
        url = f"{base_url}/crm/v3/owners"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        params = {"limit": 100}

        all_owners = []

        while url:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if not response.ok:
                logger.error(f"HubSpot API error: {response.status_code} - {response.text}")
                break

            data = response.json()
            all_owners.extend(data.get('results', []))

            # Check for pagination
            paging = data.get('paging', {})
            next_link = paging.get('next', {}).get('link')

            if next_link:
                url = next_link
                params = {}  # Next link already includes params
            else:
                url = None

        logger.info(f"Found {len(all_owners)} owners in HubSpot")

        # Format the data
        formatted_owners = []
        for owner in all_owners:
            formatted_owners.append({
                "id": owner.get('id'),
                "email": owner.get('email', ''),
                "firstName": owner.get('firstName', ''),
                "lastName": owner.get('lastName', ''),
                "userId": owner.get('userId', '')
            })

        return formatted_owners

    except Exception as e:
        logger.error(f"Failed to fetch owners from HubSpot: {e}")
        return []


def generate_mapping_template(epicor_reps, hubspot_owners):
    """
    Generate a template mapping file with both lists.

    Args:
        epicor_reps: List of Epicor sales reps
        hubspot_owners: List of HubSpot owners

    Returns:
        Dictionary with mapping data
    """
    # Create suggested mappings based on email matching
    suggested_mappings = {}

    for rep in epicor_reps:
        rep_email = rep.get('email', '').lower().strip()
        if not rep_email:
            continue

        # Try to find matching HubSpot owner by email
        for owner in hubspot_owners:
            owner_email = owner.get('email', '').lower().strip()
            if rep_email == owner_email:
                suggested_mappings[rep['code']] = {
                    "hubspot_owner_id": owner['id'],
                    "matched_by": "email",
                    "rep_name": rep.get('name'),
                    "owner_name": f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip()
                }
                break

    return {
        "_comment": "Sales Rep Mapping Data - Use this to fill config/sales_rep_mapping.json",
        "_instructions": [
            "1. Review the suggested_mappings (auto-matched by email)",
            "2. Review the unmapped_epicor_reps list",
            "3. Review the available_hubspot_owners list",
            "4. Create manual mappings for unmapped reps",
            "5. Update config/sales_rep_mapping.json with your final mappings"
        ],
        "suggested_mappings": suggested_mappings,
        "unmapped_epicor_reps": [
            rep for rep in epicor_reps
            if rep['code'] not in suggested_mappings
        ],
        "available_hubspot_owners": hubspot_owners,
        "statistics": {
            "total_epicor_reps": len(epicor_reps),
            "total_hubspot_owners": len(hubspot_owners),
            "auto_matched": len(suggested_mappings),
            "needs_manual_mapping": len(epicor_reps) - len(suggested_mappings)
        }
    }


def main():
    """Main function to fetch and generate mapping data."""
    logger.info("Starting sales rep mapping data fetch...")

    # Fetch data from both systems
    epicor_reps = fetch_epicor_sales_reps()
    hubspot_owners = fetch_hubspot_owners()

    if not epicor_reps:
        logger.warning("No Epicor sales reps found!")

    if not hubspot_owners:
        logger.warning("No HubSpot owners found!")

    # Generate mapping template
    mapping_data = generate_mapping_template(epicor_reps, hubspot_owners)

    # Save to file
    output_file = Path(__file__).parent.parent / "config" / "sales_rep_mapping_data.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(mapping_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Mapping data saved to: {output_file}")

    # Print summary
    stats = mapping_data['statistics']
    print("\n" + "="*60)
    print("SALES REP MAPPING DATA SUMMARY")
    print("="*60)
    print(f"Epicor Sales Reps:     {stats['total_epicor_reps']}")
    print(f"HubSpot Owners:        {stats['total_hubspot_owners']}")
    print(f"Auto-matched (email):  {stats['auto_matched']}")
    print(f"Needs manual mapping:  {stats['needs_manual_mapping']}")
    print("="*60)
    print(f"\nData saved to: {output_file}")
    print("\nNext steps:")
    print("1. Review the suggested_mappings in the output file")
    print("2. Manually map any unmapped_epicor_reps")
    print("3. Update config/sales_rep_mapping.json with final mappings")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
