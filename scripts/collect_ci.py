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
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9,el;q=0.8",
    "Referer": "https://www.spitogatos.gr/",
    "Origin": "https://www.spitogatos.gr",
}


def fetch_url(url):
    """Fetch URL and return JSON data."""
    if USE_HTTPX:
        with httpx.Client(headers=HEADERS, timeout=30) as client:
            response = client.get(url)
            if response.status_code == 200 and response.content:
                return response.json()
    else:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
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
