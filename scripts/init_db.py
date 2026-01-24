#!/usr/bin/env python3
"""
Initialize the database and seed with monitored areas.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.models import init_db, get_session, Area
from config import MONITORED_AREAS, DATA_DIR


def main():
    """Initialize database and seed areas."""
    print("Initializing Real Estate Analytics Database...")
    print(f"Database location: {DATA_DIR / 'real_estate.db'}")
    
    # Create tables
    init_db()
    print("Database tables created successfully.")
    
    # Seed monitored areas
    session = get_session()
    try:
        areas_added = 0
        for area_id, area_name in MONITORED_AREAS.items():
            existing = session.query(Area).filter_by(id=area_id).first()
            if not existing:
                area = Area(id=area_id, name=area_name)
                session.add(area)
                areas_added += 1
                print(f"  Added area: {area_name} (ID: {area_id})")
            else:
                print(f"  Area already exists: {area_name} (ID: {area_id})")
        
        session.commit()
        print(f"\nSeeded {areas_added} new areas.")
        print("Database initialization complete!")
        
    except Exception as e:
        session.rollback()
        print(f"Error seeding areas: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
