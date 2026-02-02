#!/usr/bin/env python3
"""
Scrape detailed property information from listing pages.

This script fetches additional property details (construction year, energy class,
amenities, etc.) that aren't available through the API.

Usage:
    python scripts/scrape_details.py                    # Scrape all unscraped properties
    python scripts/scrape_details.py --max 100          # Limit to 100 properties
    python scripts/scrape_details.py --property 123456  # Scrape specific property
    python scripts/scrape_details.py --force            # Re-scrape already scraped properties
    python scripts/scrape_details.py --visible          # Run with visible browser (for debugging)
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import Property, get_session, init_db
from collector.listing_scraper import ListingScraper


def get_properties_to_scrape(session, max_count: int = None, force: bool = False,
                              property_id: int = None) -> list:
    """
    Get list of properties that need scraping.

    Args:
        session: Database session
        max_count: Maximum number of properties to return
        force: If True, include already-scraped properties
        property_id: If specified, only return this property

    Returns:
        List of Property objects
    """
    query = session.query(Property).filter(Property.is_active == True)

    if property_id:
        query = query.filter(Property.id == property_id)
    elif not force:
        # Only get properties that haven't been scraped yet
        query = query.filter(Property.details_scraped_at == None)

    # Order by newest first (most likely to still be active)
    query = query.order_by(Property.last_seen.desc())

    if max_count:
        query = query.limit(max_count)

    return query.all()


def update_property_with_scraped_data(session, property: Property, data: dict) -> bool:
    """
    Update a property record with scraped data.

    Args:
        session: Database session
        property: Property object to update
        data: Dictionary of scraped data

    Returns:
        True if property was updated, False if listing was removed
    """
    if data.get("listing_removed"):
        property.is_active = False
        property.details_scraped_at = datetime.utcnow()
        return False

    # Map scraped data to model fields
    field_mappings = {
        "construction_year": "construction_year",
        "energy_class": "energy_class",
        "heating_type": "heating_type",
        "has_parking": "has_parking",
        "parking_spots": "parking_spots",
        "has_elevator": "has_elevator",
        "has_storage": "has_storage",
        "has_garden": "has_garden",
        "garden_sqm": "garden_sqm",
        "has_pool": "has_pool",
        "has_air_conditioning": "has_air_conditioning",
        "has_fireplace": "has_fireplace",
        "has_alarm": "has_alarm",
        "has_solar_water_heater": "has_solar_water_heater",
        "orientation": "orientation",
        "view_type": "view_type",
        "condition": "condition",
        "plot_sqm": "plot_sqm",
        "balcony_sqm": "balcony_sqm",
    }

    for data_key, model_field in field_mappings.items():
        if data_key in data and data[data_key] is not None:
            setattr(property, model_field, data[data_key])

    property.details_scraped_at = datetime.utcnow()
    return True


def progress_callback(current: int, total: int, property_id: int):
    """Print progress updates."""
    pct = (current / total) * 100
    print(f"[{current}/{total}] ({pct:.1f}%) Scraping property {property_id}...")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape detailed property information from listing pages"
    )
    parser.add_argument(
        "--max", type=int, default=None,
        help="Maximum number of properties to scrape"
    )
    parser.add_argument(
        "--property", type=int, default=None,
        help="Scrape a specific property ID"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-scrape already scraped properties"
    )
    parser.add_argument(
        "--visible", action="store_true",
        help="Run with visible browser (for debugging)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="Commit to database every N properties (default: 50)"
    )
    args = parser.parse_args()

    # Initialize database
    print("Initializing database...")
    init_db()
    session = get_session()

    # Get properties to scrape
    print("Finding properties to scrape...")
    properties = get_properties_to_scrape(
        session,
        max_count=args.max,
        force=args.force,
        property_id=args.property
    )

    if not properties:
        print("No properties to scrape.")
        return

    print(f"Found {len(properties)} properties to scrape")

    # Statistics
    stats = {
        "scraped": 0,
        "updated": 0,
        "removed": 0,
        "failed": 0,
    }

    # Scrape with browser
    headless = not args.visible
    print(f"Starting browser ({'headless' if headless else 'visible'} mode)...")

    try:
        with ListingScraper(headless=headless) as scraper:
            property_ids = [p.id for p in properties]
            property_map = {p.id: p for p in properties}

            for i, property_id in enumerate(property_ids):
                progress_callback(i + 1, len(property_ids), property_id)

                data = scraper.scrape_listing(property_id)
                stats["scraped"] += 1

                if data:
                    property = property_map[property_id]
                    if update_property_with_scraped_data(session, property, data):
                        stats["updated"] += 1

                        # Print some of the extracted data
                        extracted = []
                        if data.get("construction_year"):
                            extracted.append(f"year={data['construction_year']}")
                        if data.get("energy_class"):
                            extracted.append(f"energy={data['energy_class']}")
                        if data.get("heating_type"):
                            extracted.append(f"heating={data['heating_type'][:20]}")
                        if extracted:
                            print(f"  -> Extracted: {', '.join(extracted)}")
                    else:
                        stats["removed"] += 1
                        print(f"  -> Listing removed")
                else:
                    stats["failed"] += 1
                    print(f"  -> Failed to scrape")

                # Batch commit
                if (i + 1) % args.batch_size == 0:
                    print(f"  Committing batch...")
                    session.commit()

                # Wait between requests
                if i < len(property_ids) - 1:
                    scraper._wait_random_delay()

        # Final commit
        session.commit()

    except KeyboardInterrupt:
        print("\n\nInterrupted! Saving progress...")
        session.commit()
        print("Progress saved.")

    except Exception as e:
        print(f"\nError: {e}")
        session.rollback()
        raise

    finally:
        session.close()

    # Print summary
    print("\n" + "=" * 50)
    print("SCRAPING COMPLETE")
    print("=" * 50)
    print(f"Properties scraped: {stats['scraped']}")
    print(f"Successfully updated: {stats['updated']}")
    print(f"Listings removed: {stats['removed']}")
    print(f"Failed to scrape: {stats['failed']}")


if __name__ == "__main__":
    main()
