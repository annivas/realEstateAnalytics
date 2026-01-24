-- Real Estate Analytics Database Schema
-- This file is for reference only. Tables are created via SQLAlchemy models.

-- Areas table: Geographic areas being monitored
CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY,  -- spitogatos area ID
    name VARCHAR(255) NOT NULL,
    parent_area_id INTEGER REFERENCES areas(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Agents table: Real estate agents/agencies
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY,  -- spitogatos agent ID
    agency_name VARCHAR(255),
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Properties table: Core property listing data
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY,  -- spitogatos property ID
    category VARCHAR(50) NOT NULL,
    subtype INTEGER,
    buy_or_rent VARCHAR(10) DEFAULT 'sale',
    
    -- Location
    geography VARCHAR(255),
    area_id INTEGER REFERENCES areas(id),
    latitude REAL,
    longitude REAL,
    geocode_type VARCHAR(50),
    
    -- Property details
    sq_meters INTEGER,
    floor_number INTEGER,
    rooms INTEGER,
    total_rooms INTEGER,
    bathrooms INTEGER,
    kitchens INTEGER,
    living_rooms INTEGER,
    
    -- Status flags
    within_city_plan BOOLEAN DEFAULT 0,
    agricultural_use BOOLEAN DEFAULT 0,
    new_development BOOLEAN DEFAULT 0,
    has_virtual_tour BOOLEAN DEFAULT 0,
    has_video BOOLEAN DEFAULT 0,
    
    -- Listing info
    ad_type VARCHAR(50),
    agent_id INTEGER REFERENCES agents(id),
    description TEXT,
    main_image_url VARCHAR(500),
    image_count INTEGER DEFAULT 0,
    
    -- Timestamps from API
    first_publish_date DATETIME,
    uploaded DATETIME,
    modified DATETIME,
    
    -- Our tracking timestamps
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- Property snapshots: Historical price and status tracking
CREATE TABLE IF NOT EXISTS property_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    collection_run_id INTEGER NOT NULL REFERENCES collection_runs(id),
    
    -- Price tracking
    price INTEGER NOT NULL,
    price_reduced BOOLEAN DEFAULT 0,
    price_pre_reduction INTEGER,
    price_change_percentage REAL,
    
    -- Calculated fields
    price_per_sqm REAL,
    
    -- Timestamp
    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Collection runs: Track data collection jobs
CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    
    -- Stats
    areas_collected INTEGER DEFAULT 0,
    properties_found INTEGER DEFAULT 0,
    new_properties INTEGER DEFAULT 0,
    updated_properties INTEGER DEFAULT 0,
    price_changes_detected INTEGER DEFAULT 0,
    
    -- Status
    status VARCHAR(50) DEFAULT 'running',
    error_message TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_property_area ON properties(area_id);
CREATE INDEX IF NOT EXISTS idx_property_category ON properties(category);
CREATE INDEX IF NOT EXISTS idx_property_agent ON properties(agent_id);
CREATE INDEX IF NOT EXISTS idx_property_active ON properties(is_active);
CREATE INDEX IF NOT EXISTS idx_property_first_seen ON properties(first_seen);

CREATE INDEX IF NOT EXISTS idx_snapshot_property ON property_snapshots(property_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_collected ON property_snapshots(collected_at);
CREATE INDEX IF NOT EXISTS idx_snapshot_price ON property_snapshots(price);
CREATE INDEX IF NOT EXISTS idx_snapshot_run ON property_snapshots(collection_run_id);

-- Useful views for analytics

-- View: Latest price per property
CREATE VIEW IF NOT EXISTS v_latest_prices AS
SELECT 
    p.id,
    p.category,
    p.geography,
    p.sq_meters,
    p.rooms,
    ps.price,
    ps.price_per_sqm,
    ps.price_reduced,
    ps.collected_at
FROM properties p
JOIN property_snapshots ps ON p.id = ps.property_id
WHERE ps.collected_at = (
    SELECT MAX(collected_at) 
    FROM property_snapshots 
    WHERE property_id = p.id
)
AND p.is_active = 1;

-- View: Price changes over time
CREATE VIEW IF NOT EXISTS v_price_changes AS
SELECT 
    ps1.property_id,
    ps1.price as current_price,
    ps2.price as previous_price,
    ps1.price - ps2.price as price_change,
    ROUND((ps1.price - ps2.price) * 100.0 / ps2.price, 2) as change_percentage,
    ps1.collected_at as current_date,
    ps2.collected_at as previous_date
FROM property_snapshots ps1
JOIN property_snapshots ps2 ON ps1.property_id = ps2.property_id
WHERE ps1.collected_at > ps2.collected_at
AND NOT EXISTS (
    SELECT 1 FROM property_snapshots ps3
    WHERE ps3.property_id = ps1.property_id
    AND ps3.collected_at > ps2.collected_at
    AND ps3.collected_at < ps1.collected_at
);
