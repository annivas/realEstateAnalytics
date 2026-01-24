#!/usr/bin/env python3
"""
Manual data collection script.
Run this to collect data from the API on demand.

Usage:
    python scripts/run_collection.py              # Collect all available
    python scripts/run_collection.py --max 1000   # Limit to 1000 results
    python scripts/run_collection.py --max 5000   # Limit to 5000 results
"""
import sys
import argparse
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.models import init_db
from collector.api_client import SpitogatosClient
from config import MONITORED_AREAS

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Run manual data collection."""
    parser = argparse.ArgumentParser(description="Collect real estate data from spitogatos.gr")
    parser.add_argument(
        "--max", "-m",
        type=int,
        default=None,
        help="Maximum number of results to fetch (default: all available)"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("Real Estate Analytics - Manual Data Collection")
    print("=" * 60)
    
    # Ensure database is initialized
    print("\nInitializing database...")
    init_db()
    
    # Show areas being collected
    print(f"\nCollecting data for {len(MONITORED_AREAS)} areas:")
    for area_id, area_name in MONITORED_AREAS.items():
        print(f"  - {area_name} (ID: {area_id})")
    
    if args.max:
        print(f"\nLimit: {args.max:,} results")
    else:
        print("\nLimit: None (fetching all available)")
    
    print("\nStarting collection...")
    print("-" * 60)
    
    with SpitogatosClient() as client:
        run_stats = client.collect_and_store(max_results=args.max)
    
    print("-" * 60)
    print("\nCollection Summary:")
    print(f"  Status: {run_stats['status']}")
    print(f"  Properties found: {run_stats['properties_found']}")
    print(f"  New properties: {run_stats['new_properties']}")
    print(f"  Updated properties: {run_stats['updated_properties']}")
    print(f"  Price changes detected: {run_stats['price_changes_detected']}")
    if run_stats['completed_at'] and run_stats['started_at']:
        print(f"  Duration: {run_stats['completed_at'] - run_stats['started_at']}")
    
    if run_stats['status'] == "failed":
        print(f"\n  Error: {run_stats.get('error_message', 'Unknown error')}")
        return 1
    
    print("\nCollection completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
