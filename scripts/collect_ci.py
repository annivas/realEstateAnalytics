#!/usr/bin/env python3
"""
Robust data collection script for CI/GitHub Actions.
- Handles API rate limiting with retries and backoff
- Preserves historical data (never overwrites)
- Tracks property lifecycle (new, updated, removed)
"""
import json
import time
import sqlite3
import os
import random
from datetime import datetime
from pathlib import Path

# Try httpx first, fall back to urllib
try:
    import httpx
    USE_HTTPX = True
except ImportError:
    import urllib.request
    USE_HTTPX = False

# Import monitored areas from config
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MONITORED_AREAS

# Configuration
API_URL = "https://www.spitogatos.gr/n_api/v1/properties/search-results-map"
AREA_IDS = list(MONITORED_AREAS.keys())  # Get area IDs from config
MAX_RESULTS = None  # No limit - collect all available data
MIN_RESPONSE_SIZE = 5000  # Responses smaller than this are likely blocked
MAX_RETRIES = 5  # More retries
BASE_DELAY = 5.0  # Longer delay between requests to avoid rate limiting

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "el-GR,el;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.spitogatos.gr/pwliseis-katoikies/attiki",
    "Origin": "https://www.spitogatos.gr",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def fetch_url(url, attempt=1):
    """Fetch URL with retry logic for rate limiting."""
    # Add jitter to avoid detection
    jitter = random.uniform(0.5, 1.5)
    
    try:
        if USE_HTTPX:
            with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
                response = client.get(url)
                size = len(response.content)
                print(f"  [Attempt {attempt}] Status: {response.status_code}, Size: {size:,} bytes")
                
                # Check for rate limiting (small response)
                if response.status_code == 200 and size < MIN_RESPONSE_SIZE:
                    print(f"  ⚠️  Response too small - likely rate limited")
                    if attempt < MAX_RETRIES:
                        backoff = BASE_DELAY * (2 ** attempt) * jitter
                        print(f"  ⏳ Backing off for {backoff:.1f}s before retry...")
                        time.sleep(backoff)
                        return fetch_url(url, attempt + 1)
                    return None
                
                if response.status_code == 200 and response.content:
                    return response.json()
        else:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()
                size = len(data)
                print(f"  [Attempt {attempt}] Size: {size:,} bytes")
                
                if size < MIN_RESPONSE_SIZE:
                    print(f"  ⚠️  Response too small - likely rate limited")
                    if attempt < MAX_RETRIES:
                        backoff = BASE_DELAY * (2 ** attempt) * jitter
                        print(f"  ⏳ Backing off for {backoff:.1f}s before retry...")
                        time.sleep(backoff)
                        return fetch_url(url, attempt + 1)
                    return None
                
                return json.loads(data.decode())
                
    except Exception as e:
        print(f"  ❌ Fetch error: {e}")
        if attempt < MAX_RETRIES:
            backoff = BASE_DELAY * (2 ** attempt) * jitter
            print(f"  ⏳ Retrying in {backoff:.1f}s...")
            time.sleep(backoff)
            return fetch_url(url, attempt + 1)
    
    return None


def build_url(offset):
    """Build API URL with parameters."""
    area_params = "&".join([f"areaIDs[]={aid}" for aid in AREA_IDS])
    return f"{API_URL}?listingType=sale&category=residential&sortBy=rankingscore&sortOrder=desc&offset={offset}&{area_params}"


def init_database(db_path):
    """Initialize SQLite database with required tables."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY,
            agency_name TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY,
            category TEXT,
            subtype INTEGER,
            buy_or_rent TEXT DEFAULT 'sale',
            geography TEXT,
            latitude REAL,
            longitude REAL,
            sq_meters INTEGER,
            floor_number INTEGER,
            rooms INTEGER,
            bathrooms INTEGER,
            ad_type TEXT,
            agent_id INTEGER,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        );
        
        CREATE TABLE IF NOT EXISTS property_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            collection_run_id INTEGER,
            price INTEGER NOT NULL,
            price_reduced INTEGER DEFAULT 0,
            price_pre_reduction INTEGER,
            price_change_percentage REAL,
            price_per_sqm REAL,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (property_id) REFERENCES properties(id)
        );
        
        CREATE TABLE IF NOT EXISTS collection_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            properties_found INTEGER DEFAULT 0,
            new_properties INTEGER DEFAULT 0,
            updated_properties INTEGER DEFAULT 0,
            removed_properties INTEGER DEFAULT 0,
            price_changes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running'
        );
        
        -- Index for faster lookups
        CREATE INDEX IF NOT EXISTS idx_snapshots_property ON property_snapshots(property_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_collected ON property_snapshots(collected_at);
        CREATE INDEX IF NOT EXISTS idx_properties_active ON properties(is_active);
        CREATE INDEX IF NOT EXISTS idx_properties_geography ON properties(geography);
    """)
    
    conn.commit()
    return conn


def load_existing_data(conn, data_dir):
    """Load existing data from CSV files into database."""
    import csv
    cursor = conn.cursor()
    
    # Load agents
    agents_csv = data_dir / "agents.csv"
    if agents_csv.exists():
        print(f"Loading existing agents from {agents_csv}")
        with open(agents_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO agents (id, agency_name, first_seen, last_seen)
                        VALUES (?, ?, ?, ?)
                    """, (
                        int(row["id"]) if row.get("id") else None,
                        row.get("agency_name"),
                        row.get("first_seen"),
                        row.get("last_seen"),
                    ))
                except:
                    pass
        conn.commit()
    
    # Load properties
    props_csv = data_dir / "properties.csv"
    if props_csv.exists():
        print(f"Loading existing properties from {props_csv}")
        with open(props_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO properties 
                        (id, category, subtype, buy_or_rent, geography, latitude, longitude,
                         sq_meters, floor_number, rooms, bathrooms, ad_type, agent_id,
                         first_seen, last_seen, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(row["id"]) if row.get("id") else None,
                        row.get("category"),
                        int(row["subtype"]) if row.get("subtype") and row["subtype"] not in ('', 'None') else None,
                        row.get("buy_or_rent"),
                        row.get("geography"),
                        float(row["latitude"]) if row.get("latitude") and row["latitude"] not in ('', 'None') else None,
                        float(row["longitude"]) if row.get("longitude") and row["longitude"] not in ('', 'None') else None,
                        int(row["sq_meters"]) if row.get("sq_meters") and row["sq_meters"] not in ('', 'None') else None,
                        int(row["floor_number"]) if row.get("floor_number") and row["floor_number"] not in ('', 'None') else None,
                        int(row["rooms"]) if row.get("rooms") and row["rooms"] not in ('', 'None') else None,
                        int(row["bathrooms"]) if row.get("bathrooms") and row["bathrooms"] not in ('', 'None') else None,
                        row.get("ad_type"),
                        int(row["agent_id"]) if row.get("agent_id") and row["agent_id"] not in ('', 'None') else None,
                        row.get("first_seen"),
                        row.get("last_seen"),
                        1 if row.get("is_active") in ('1', 'True', 'true', True) else 0,
                    ))
                except Exception as e:
                    pass
        conn.commit()
    
    # Load snapshots
    snaps_csv = data_dir / "snapshots.csv"
    if snaps_csv.exists():
        print(f"Loading existing snapshots from {snaps_csv}")
        with open(snaps_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO property_snapshots 
                        (id, property_id, collection_run_id, price, price_reduced,
                         price_pre_reduction, price_change_percentage, price_per_sqm, collected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(row["id"]) if row.get("id") else None,
                        int(row["property_id"]) if row.get("property_id") else None,
                        int(row["collection_run_id"]) if row.get("collection_run_id") and row["collection_run_id"] not in ('', 'None') else 1,
                        int(row["price"]) if row.get("price") and row["price"] not in ('', 'None') else 0,
                        1 if row.get("price_reduced") in ('1', 'True', 'true', True) else 0,
                        int(row["price_pre_reduction"]) if row.get("price_pre_reduction") and row["price_pre_reduction"] not in ('', 'None') else None,
                        float(row["price_change_percentage"]) if row.get("price_change_percentage") and row["price_change_percentage"] not in ('', 'None') else None,
                        float(row["price_per_sqm"]) if row.get("price_per_sqm") and row["price_per_sqm"] not in ('', 'None') else None,
                        row.get("collected_at"),
                    ))
                except:
                    pass
        conn.commit()
    
    # Load collection runs
    runs_csv = data_dir / "collection_runs.csv"
    if runs_csv.exists():
        print(f"Loading existing collection runs from {runs_csv}")
        with open(runs_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO collection_runs 
                        (id, started_at, completed_at, properties_found, new_properties, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        int(row["id"]) if row.get("id") else None,
                        row.get("started_at"),
                        row.get("completed_at"),
                        int(row["properties_found"]) if row.get("properties_found") and row["properties_found"] not in ('', 'None') else 0,
                        int(row["new_properties"]) if row.get("new_properties") and row["new_properties"] not in ('', 'None') else 0,
                        row.get("status"),
                    ))
                except:
                    pass
        conn.commit()
    
    # Reset auto-increment counters
    for table in ["property_snapshots", "collection_runs"]:
        max_id = cursor.execute(f"SELECT MAX(id) FROM {table}").fetchone()[0]
        if max_id:
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name = ?", (table,))
            cursor.execute(f"INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (table, max_id))
    conn.commit()
    
    # Report loaded counts
    print("\n📊 Existing data loaded:")
    for table in ["agents", "properties", "property_snapshots", "collection_runs"]:
        count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count:,} rows")


def collect_data():
    """Main collection function with robust error handling."""
    # Setup paths
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "real_estate.db"
    
    print("=" * 60)
    print("🏠 REAL ESTATE DATA COLLECTION")
    print("=" * 60)
    print(f"📁 Database: {db_path}")
    print(f"🎯 Areas: {AREA_IDS}")
    print(f"📦 Max results: {'unlimited' if MAX_RESULTS is None else f'{MAX_RESULTS:,}'}")
    print("=" * 60)
    
    conn = init_database(str(db_path))
    cursor = conn.cursor()
    
    # Load existing data from CSVs (preserves historical data)
    print("\n📥 Loading existing data...")
    load_existing_data(conn, data_dir)
    
    # Get current active property IDs (to detect removals later)
    cursor.execute("SELECT id FROM properties WHERE is_active = 1")
    previously_active = set(row[0] for row in cursor.fetchall())
    print(f"\n📋 Previously active properties: {len(previously_active):,}")
    
    # Start collection run
    cursor.execute("INSERT INTO collection_runs (status) VALUES ('running')")
    run_id = cursor.lastrowid
    conn.commit()
    print(f"\n🚀 Started collection run #{run_id}")
    print("-" * 60)
    
    offset = 0
    total_fetched = 0
    new_properties = 0
    updated_properties = 0
    price_changes = 0
    seen_property_ids = set()
    consecutive_failures = 0
    max_consecutive_failures = 3
    api_total = None  # Track total available from API for proportional thresholds

    try:
        while MAX_RESULTS is None or total_fetched < MAX_RESULTS:
            url = build_url(offset)
            print(f"\n📡 Fetching offset {offset}...")
            
            # Progressive delays - wait longer as we fetch more pages to avoid rate limits
            # Pages 0-5: normal delay, Pages 6+: increasing delay
            page_num = offset // 300
            progressive_multiplier = 1 + (page_num // 5) * 0.5  # 1x, 1.5x, 2x, etc.
            delay = (BASE_DELAY + random.uniform(1.0, 4.0)) * progressive_multiplier
            print(f"  ⏳ Waiting {delay:.1f}s (page {page_num + 1})...")
            time.sleep(delay)
            
            data = fetch_url(url)
            
            if not data:
                consecutive_failures += 1
                print(f"  ⚠️  No data returned (failure {consecutive_failures}/{max_consecutive_failures})")
                
                if consecutive_failures >= max_consecutive_failures:
                    print(f"\n❌ Too many consecutive failures, stopping collection")
                    break
                
                # Try next offset anyway
                offset += 300
                continue
            
            # Reset failure counter on success
            consecutive_failures = 0
            
            count = data.get("count", 0)
            total = data.get("total", 0)
            clusters = data.get("data", {})

            if offset == 0:
                api_total = total  # Store for proportional removal threshold
                print(f"  📊 Total available in API: {total:,}")
            
            if not clusters or count == 0:
                print("  ℹ️  No more data in response")
                break
            
            # Process properties
            batch_count = 0
            batch_new = 0
            batch_updated = 0
            batch_price_changes = 0
            
            for cluster_key, cluster_data in clusters.items():
                for prop in cluster_data.get("properties", []):
                    prop_id = prop.get("id")
                    if not prop_id:
                        continue
                    
                    seen_property_ids.add(prop_id)
                    
                    # Check if property exists and get last price
                    cursor.execute("""
                        SELECT p.id, ps.price 
                        FROM properties p
                        LEFT JOIN property_snapshots ps ON p.id = ps.property_id
                        WHERE p.id = ?
                        ORDER BY ps.collected_at DESC LIMIT 1
                    """, (prop_id,))
                    existing = cursor.fetchone()
                    
                    # Get agent
                    agent_id = prop.get("agent_id")
                    re_agent = prop.get("reAgent") or {}
                    if agent_id:
                        cursor.execute("""
                            INSERT INTO agents (id, agency_name, last_seen)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                            ON CONFLICT(id) DO UPDATE SET 
                                agency_name = excluded.agency_name,
                                last_seen = CURRENT_TIMESTAMP
                        """, (agent_id, re_agent.get("agencyName")))
                    
                    # Calculate price per sqm
                    sq_meters = prop.get("sq_meters")
                    price = prop.get("price", 0)
                    price_per_sqm = price / sq_meters if sq_meters and sq_meters > 0 else None
                    
                    if existing:
                        # Existing property - update last_seen and check for price change
                        cursor.execute("""
                            UPDATE properties 
                            SET last_seen = CURRENT_TIMESTAMP, is_active = 1
                            WHERE id = ?
                        """, (prop_id,))
                        
                        old_price = existing[1]
                        if old_price and old_price != price:
                            batch_price_changes += 1
                        
                        batch_updated += 1
                    else:
                        # New property
                        cursor.execute("""
                            INSERT INTO properties 
                            (id, category, subtype, buy_or_rent, geography, latitude, longitude,
                             sq_meters, floor_number, rooms, bathrooms, ad_type, agent_id,
                             first_seen, last_seen, is_active)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                        """, (
                            prop_id,
                            prop.get("category"),
                            prop.get("subtype"),
                            "sale" if prop.get("buy_or_rent") == "0" else "rent",
                            prop.get("geography"),
                            prop.get("latitude"),
                            prop.get("longitude"),
                            sq_meters,
                            prop.get("floorNumber"),
                            prop.get("rooms"),
                            prop.get("no_of_bathrooms"),
                            prop.get("adType_code"),
                            agent_id,
                        ))
                        batch_new += 1
                    
                    # Always create a snapshot (this is our historical record)
                    cursor.execute("""
                        INSERT INTO property_snapshots 
                        (property_id, collection_run_id, price, price_reduced, 
                         price_pre_reduction, price_change_percentage, price_per_sqm)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        prop_id,
                        run_id,
                        price,
                        1 if prop.get("priceReduced") else 0,
                        prop.get("pricePreReduction"),
                        prop.get("priceChangePercentage"),
                        price_per_sqm,
                    ))
                    
                    batch_count += 1
                    total_fetched += 1

                    if MAX_RESULTS is not None and total_fetched >= MAX_RESULTS:
                        break

                if MAX_RESULTS is not None and total_fetched >= MAX_RESULTS:
                    break
            
            conn.commit()
            
            new_properties += batch_new
            updated_properties += batch_updated
            price_changes += batch_price_changes
            
            print(f"  ✅ Processed {batch_count} properties ({batch_new} new, {batch_updated} updated, {batch_price_changes} price changes)")
            print(f"     Running total: {total_fetched:,}")
            
            offset += count
            if offset >= total:
                print(f"\n✅ Reached end of available data")
                break
    
    except Exception as e:
        print(f"\n❌ Error during collection: {e}")
        cursor.execute("""
            UPDATE collection_runs 
            SET status = 'failed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (run_id,))
        conn.commit()
        raise
    
    # Mark properties not seen in this run as potentially removed (if we got data)
    removed_properties = 0
    if total_fetched > 0:
        not_seen = previously_active - seen_property_ids
        if not_seen:
            print(f"\n🔍 {len(not_seen)} properties not seen in this collection")
            # Calculate proportional threshold: need at least 50% of API total or minimum 100
            # This prevents false removals when collection fails early
            if api_total and api_total > 0:
                min_threshold = max(100, int(api_total * 0.5))
            else:
                min_threshold = 100  # Fallback if API total unknown
            print(f"  📊 Removal threshold: {min_threshold:,} (50% of {api_total:,} available)" if api_total else f"  📊 Removal threshold: {min_threshold:,}")
            # Only mark as inactive if we collected a significant portion
            if total_fetched >= min_threshold:
                cursor.execute(f"""
                    UPDATE properties SET is_active = 0
                    WHERE id IN ({','.join('?' * len(not_seen))})
                """, list(not_seen))
                removed_properties = len(not_seen)
                print(f"  📤 Marked {removed_properties} properties as inactive (likely sold)")
            else:
                print(f"  ⚠️  Skipping removal marking - only collected {total_fetched:,} of {min_threshold:,} threshold")
    
    # Complete the run
    cursor.execute("""
        UPDATE collection_runs 
        SET status = 'completed', 
            completed_at = CURRENT_TIMESTAMP,
            properties_found = ?,
            new_properties = ?,
            updated_properties = ?,
            removed_properties = ?,
            price_changes = ?
        WHERE id = ?
    """, (total_fetched, new_properties, updated_properties, removed_properties, price_changes, run_id))
    conn.commit()
    
    # Final summary
    print("\n" + "=" * 60)
    print("📊 COLLECTION SUMMARY")
    print("=" * 60)
    print(f"  ✅ Total processed: {total_fetched:,}")
    print(f"  🆕 New properties: {new_properties:,}")
    print(f"  🔄 Updated properties: {updated_properties:,}")
    print(f"  📤 Removed (sold): {removed_properties:,}")
    print(f"  💰 Price changes: {price_changes:,}")
    print("=" * 60)
    
    # Report final database state
    print("\n📁 Final database state:")
    for table in ["agents", "properties", "property_snapshots", "collection_runs"]:
        count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count:,} rows")
    
    active = cursor.execute("SELECT COUNT(*) FROM properties WHERE is_active = 1").fetchone()[0]
    inactive = cursor.execute("SELECT COUNT(*) FROM properties WHERE is_active = 0").fetchone()[0]
    print(f"\n  Active properties: {active:,}")
    print(f"  Inactive (sold): {inactive:,}")
    
    conn.close()
    
    return total_fetched > 0  # Return success status


if __name__ == "__main__":
    success = collect_data()
    exit(0 if success else 1)
