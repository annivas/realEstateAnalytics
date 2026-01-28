#!/usr/bin/env python3
"""
Simplified data collection script for CI/GitHub Actions.
Collects data and stores directly without complex dependencies.
"""
import json
import time
import sqlite3
import os
from datetime import datetime
from pathlib import Path

# Try httpx first, fall back to urllib
try:
    import httpx
    USE_HTTPX = True
except ImportError:
    import urllib.request
    USE_HTTPX = False

# Configuration
API_URL = "https://www.spitogatos.gr/n_api/v1/properties/search-results-map"
AREA_IDS = [105103]  # Athens Region
MAX_RESULTS = 5000
REQUEST_DELAY = 1.0

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
}


def fetch_url(url):
    """Fetch URL and return JSON data."""
    try:
        if USE_HTTPX:
            with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
                response = client.get(url)
                print(f"  Response status: {response.status_code}, size: {len(response.content)} bytes")
                if response.status_code == 200 and response.content:
                    return response.json()
                else:
                    print(f"  Response text: {response.text[:500] if response.text else 'empty'}")
        else:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()
                print(f"  Response size: {len(data)} bytes")
                return json.loads(data.decode())
    except Exception as e:
        print(f"  Fetch error: {e}")
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
            status TEXT DEFAULT 'running'
        );
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
    
    # Load snapshots (critical for historical data!)
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
    
    # Reset auto-increment counters to continue after existing data
    # This prevents ID conflicts when adding new records
    for table in ["property_snapshots", "collection_runs"]:
        max_id = cursor.execute(f"SELECT MAX(id) FROM {table}").fetchone()[0]
        if max_id:
            cursor.execute(f"UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (max_id, table))
    conn.commit()
    
    # Report loaded counts
    for table in ["agents", "properties", "property_snapshots", "collection_runs"]:
        count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows loaded")


def collect_data():
    """Main collection function."""
    # Setup paths
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "real_estate.db"
    
    print(f"Database: {db_path}")
    print(f"Collecting from {len(AREA_IDS)} areas, max {MAX_RESULTS} results")
    print("-" * 50)
    
    conn = init_database(str(db_path))
    cursor = conn.cursor()
    
    # Load existing data from CSVs first (preserves historical data!)
    print("\nLoading existing data...")
    load_existing_data(conn, data_dir)
    print("-" * 50)
    
    # Start collection run
    cursor.execute("INSERT INTO collection_runs (status) VALUES ('running')")
    run_id = cursor.lastrowid
    conn.commit()
    
    offset = 0
    total_fetched = 0
    new_properties = 0
    
    try:
        while total_fetched < MAX_RESULTS:
            url = build_url(offset)
            print(f"Fetching offset {offset}...")
            
            data = fetch_url(url)
            if not data:
                print("No data returned, stopping")
                break
            
            count = data.get("count", 0)
            total = data.get("total", 0)
            clusters = data.get("data", {})
            
            if offset == 0:
                print(f"Total available: {total:,}")
            
            if not clusters or count == 0:
                print("No more data")
                break
            
            # Process properties
            batch_count = 0
            for cluster_key, cluster_data in clusters.items():
                for prop in cluster_data.get("properties", []):
                    prop_id = prop.get("id")
                    if not prop_id:
                        continue
                    
                    # Check if property exists
                    cursor.execute("SELECT id FROM properties WHERE id = ?", (prop_id,))
                    exists = cursor.fetchone()
                    
                    # Get agent
                    agent_id = prop.get("agent_id")
                    re_agent = prop.get("reAgent") or {}
                    if agent_id:
                        cursor.execute("""
                            INSERT OR REPLACE INTO agents (id, agency_name, last_seen)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                        """, (agent_id, re_agent.get("agencyName")))
                    
                    # Insert/update property
                    sq_meters = prop.get("sq_meters")
                    price = prop.get("price", 0)
                    price_per_sqm = price / sq_meters if sq_meters and sq_meters > 0 else None
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO properties 
                        (id, category, subtype, buy_or_rent, geography, latitude, longitude,
                         sq_meters, floor_number, rooms, bathrooms, ad_type, agent_id, 
                         last_seen, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
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
                    
                    # Add snapshot
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
                    
                    if not exists:
                        new_properties += 1
                    
                    batch_count += 1
                    total_fetched += 1
                    
                    if total_fetched >= MAX_RESULTS:
                        break
                
                if total_fetched >= MAX_RESULTS:
                    break
            
            conn.commit()
            print(f"  Processed {batch_count} properties ({total_fetched:,} total)")
            
            offset += count
            if offset >= total:
                break
            
            time.sleep(REQUEST_DELAY)
    
    except Exception as e:
        print(f"Error: {e}")
        cursor.execute("""
            UPDATE collection_runs 
            SET status = 'failed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (run_id,))
        conn.commit()
        raise
    
    # Complete the run
    cursor.execute("""
        UPDATE collection_runs 
        SET status = 'completed', 
            completed_at = CURRENT_TIMESTAMP,
            properties_found = ?,
            new_properties = ?
        WHERE id = ?
    """, (total_fetched, new_properties, run_id))
    conn.commit()
    
    print("-" * 50)
    print(f"Collection complete!")
    print(f"  Total processed: {total_fetched:,}")
    print(f"  New properties: {new_properties:,}")
    
    conn.close()


if __name__ == "__main__":
    collect_data()
