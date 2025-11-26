#!/usr/bin/env python3
"""
Fetch HubSpot Deal Pipelines and Stage IDs.

This script retrieves all deal pipelines and their stages from HubSpot,
displaying the stage IDs needed for configuration.

Usage:
    python scripts/fetch_hubspot_pipelines.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

import requests


def main():
    """Fetch and display HubSpot pipelines and stages."""

    # Get API key from environment
    api_key = os.environ.get('HUBSPOT_API_KEY')

    if not api_key:
        print("ERROR: HUBSPOT_API_KEY not set in .env file")
        return 1

    print("=" * 80)
    print("HUBSPOT DEAL PIPELINES AND STAGES")
    print("=" * 80)
    print()

    # Fetch pipelines
    url = "https://api.hubapi.com/crm/v3/pipelines/deals"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to fetch pipelines: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return 1

    pipelines = data.get('results', [])

    if not pipelines:
        print("No pipelines found.")
        return 0

    print(f"Found {len(pipelines)} pipeline(s):\n")

    for pipeline in pipelines:
        pipeline_id = pipeline.get('id')
        pipeline_label = pipeline.get('label')
        stages = pipeline.get('stages', [])

        print("=" * 80)
        print(f"PIPELINE: {pipeline_label}")
        print(f"PIPELINE ID: {pipeline_id}")
        print("=" * 80)
        print()
        print(f"{'Stage Label':<30} {'Stage ID':<15} {'Display Order':<15} {'Probability'}")
        print("-" * 80)

        # Sort stages by display order
        stages_sorted = sorted(stages, key=lambda s: s.get('displayOrder', 0))

        for stage in stages_sorted:
            stage_id = stage.get('id')
            stage_label = stage.get('label')
            display_order = stage.get('displayOrder')
            metadata = stage.get('metadata', {})
            probability = metadata.get('probability', 'N/A')

            print(f"{stage_label:<30} {stage_id:<15} {display_order:<15} {probability}")

        print()

        # Print as config format
        print("Configuration format for .env or config file:")
        print("-" * 80)
        print(f"HUBSPOT_{'QUOTES' if 'quote' in pipeline_label.lower() else 'ORDERS'}_PIPELINE_ID={pipeline_id}")
        print()
        print("Stage ID mapping (copy to your config):")
        print("{")
        for stage in stages_sorted:
            stage_id = stage.get('id')
            stage_label = stage.get('label', '').lower().replace(' ', '_').replace('-', '_')
            print(f'    "{stage_label}": "{stage_id}",')
        print("}")
        print()

    # Print summary for .env
    print("=" * 80)
    print("SUMMARY - Add these to your .env file:")
    print("=" * 80)
    for pipeline in pipelines:
        pipeline_id = pipeline.get('id')
        pipeline_label = pipeline.get('label', '').lower()

        if 'quote' in pipeline_label:
            print(f"HUBSPOT_QUOTES_PIPELINE_ID={pipeline_id}")
        elif 'order' in pipeline_label:
            print(f"HUBSPOT_ORDERS_PIPELINE_ID={pipeline_id}")
        else:
            print(f"# {pipeline.get('label')}: {pipeline_id}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
