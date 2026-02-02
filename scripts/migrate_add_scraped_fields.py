#!/usr/bin/env python3
"""
Database migration script to add scraped details columns to the properties table.

This script adds new columns for property details scraped from listing pages.
Safe to run multiple times - it will skip columns that already exist.

Usage:
    python scripts/migrate_add_scraped_fields.py
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text, inspect
from database.models import get_engine, Property


# New columns to add (column_name, column_type, nullable)
NEW_COLUMNS = [
    ("construction_year", "INTEGER", True),
    ("energy_class", "VARCHAR(10)", True),
    ("heating_type", "VARCHAR(100)", True),
    ("has_parking", "BOOLEAN", True),
    ("parking_spots", "INTEGER", True),
    ("has_elevator", "BOOLEAN", True),
    ("has_storage", "BOOLEAN", True),
    ("has_garden", "BOOLEAN", True),
    ("garden_sqm", "INTEGER", True),
    ("has_pool", "BOOLEAN", True),
    ("has_air_conditioning", "BOOLEAN", True),
    ("has_fireplace", "BOOLEAN", True),
    ("has_alarm", "BOOLEAN", True),
    ("has_solar_water_heater", "BOOLEAN", True),
    ("orientation", "VARCHAR(50)", True),
    ("view_type", "VARCHAR(100)", True),
    ("condition", "VARCHAR(50)", True),
    ("plot_sqm", "INTEGER", True),
    ("balcony_sqm", "INTEGER", True),
    ("details_scraped_at", "DATETIME", True),
]


def get_existing_columns(engine, table_name: str) -> set:
    """Get set of existing column names for a table."""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return {col["name"] for col in columns}


def add_column(engine, table_name: str, column_name: str, column_type: str):
    """Add a new column to a table."""
    with engine.connect() as conn:
        # SQLite syntax for adding column
        sql = text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        conn.execute(sql)
        conn.commit()


def main():
    print("Starting migration: Add scraped details fields")
    print("=" * 50)

    engine = get_engine()
    table_name = Property.__tablename__

    # Check if table exists, if not initialize database
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        print(f"Table {table_name} does not exist. Initializing database...")
        from database.models import init_db
        init_db()
        print("Database initialized.")
        # After init, all columns should already exist from the model
        print("All columns created from model definition.")
        return

    # Get existing columns
    existing_columns = get_existing_columns(engine, table_name)
    print(f"Existing columns in {table_name}: {len(existing_columns)}")

    # Add missing columns
    added = 0
    skipped = 0

    for column_name, column_type, nullable in NEW_COLUMNS:
        if column_name in existing_columns:
            print(f"  [SKIP] {column_name} - already exists")
            skipped += 1
        else:
            try:
                add_column(engine, table_name, column_name, column_type)
                print(f"  [ADD]  {column_name} ({column_type})")
                added += 1
            except Exception as e:
                print(f"  [ERR]  {column_name} - {e}")

    print("=" * 50)
    print(f"Migration complete: {added} columns added, {skipped} skipped")


if __name__ == "__main__":
    main()
