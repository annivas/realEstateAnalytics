"""
SQLAlchemy models for real estate analytics database.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
from config import DATABASE_URL

Base = declarative_base()


class Area(Base):
    """Geographic areas being monitored."""
    __tablename__ = "areas"

    id = Column(Integer, primary_key=True)  # spitogatos area ID
    name = Column(String(255), nullable=False)
    parent_area_id = Column(Integer, ForeignKey("areas.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    properties = relationship("Property", back_populates="area")
    parent = relationship("Area", remote_side=[id], backref="children")

    def __repr__(self):
        return f"<Area(id={self.id}, name='{self.name}')>"


class Agent(Base):
    """Real estate agents/agencies."""
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)  # spitogatos agent ID
    agency_name = Column(String(255), nullable=True)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    properties = relationship("Property", back_populates="agent")

    def __repr__(self):
        return f"<Agent(id={self.id}, agency='{self.agency_name}')>"


class Property(Base):
    """Core property listing data."""
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True)  # spitogatos property ID
    category = Column(String(50), nullable=False)  # house, apartment, etc.
    subtype = Column(Integer, nullable=True)
    buy_or_rent = Column(String(10), default="sale")
    
    # Location
    geography = Column(String(255), nullable=True)  # Human-readable location
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    geocode_type = Column(String(50), nullable=True)
    
    # Property details
    sq_meters = Column(Integer, nullable=True)
    floor_number = Column(Integer, nullable=True)
    rooms = Column(Integer, nullable=True)
    total_rooms = Column(Integer, nullable=True)
    bathrooms = Column(Integer, nullable=True)
    kitchens = Column(Integer, nullable=True)
    living_rooms = Column(Integer, nullable=True)
    
    # Status flags
    within_city_plan = Column(Boolean, default=False)
    agricultural_use = Column(Boolean, default=False)
    new_development = Column(Boolean, default=False)
    has_virtual_tour = Column(Boolean, default=False)
    has_video = Column(Boolean, default=False)
    
    # Listing info
    ad_type = Column(String(50), nullable=True)  # vip, featured, standard
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    description = Column(Text, nullable=True)
    main_image_url = Column(String(500), nullable=True)
    image_count = Column(Integer, default=0)
    
    # Timestamps from API
    first_publish_date = Column(DateTime, nullable=True)
    uploaded = Column(DateTime, nullable=True)
    modified = Column(DateTime, nullable=True)
    
    # Our tracking timestamps
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    area = relationship("Area", back_populates="properties")
    agent = relationship("Agent", back_populates="properties")
    snapshots = relationship("PropertySnapshot", back_populates="property", order_by="PropertySnapshot.collected_at")

    # Indexes for common queries
    __table_args__ = (
        Index("idx_property_area", "area_id"),
        Index("idx_property_category", "category"),
        Index("idx_property_agent", "agent_id"),
        Index("idx_property_active", "is_active"),
        Index("idx_property_first_seen", "first_seen"),
    )

    def __repr__(self):
        return f"<Property(id={self.id}, category='{self.category}', sq_meters={self.sq_meters})>"


class PropertySnapshot(Base):
    """Historical price and status snapshots for properties."""
    __tablename__ = "property_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    collection_run_id = Column(Integer, ForeignKey("collection_runs.id"), nullable=False)
    
    # Price tracking
    price = Column(Integer, nullable=False)
    price_reduced = Column(Boolean, default=False)
    price_pre_reduction = Column(Integer, nullable=True)
    price_change_percentage = Column(Float, nullable=True)
    
    # Calculated fields
    price_per_sqm = Column(Float, nullable=True)
    
    # Timestamp
    collected_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    property = relationship("Property", back_populates="snapshots")
    collection_run = relationship("CollectionRun", back_populates="snapshots")

    # Indexes
    __table_args__ = (
        Index("idx_snapshot_property", "property_id"),
        Index("idx_snapshot_collected", "collected_at"),
        Index("idx_snapshot_price", "price"),
        Index("idx_snapshot_run", "collection_run_id"),
    )

    def __repr__(self):
        return f"<PropertySnapshot(property_id={self.property_id}, price={self.price}, date={self.collected_at})>"


class CollectionRun(Base):
    """Track data collection runs."""
    __tablename__ = "collection_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Stats
    areas_collected = Column(Integer, default=0)
    properties_found = Column(Integer, default=0)
    new_properties = Column(Integer, default=0)
    updated_properties = Column(Integer, default=0)
    price_changes_detected = Column(Integer, default=0)
    
    # Status
    status = Column(String(50), default="running")  # running, completed, failed
    error_message = Column(Text, nullable=True)

    # Relationships
    snapshots = relationship("PropertySnapshot", back_populates="collection_run")

    def __repr__(self):
        return f"<CollectionRun(id={self.id}, status='{self.status}', properties={self.properties_found})>"


# Database connection utilities
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, echo=False)
    return _engine


def get_session() -> Session:
    """Get a new database session."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def init_db():
    """Initialize the database by creating all tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    
    # Load seed data if database is empty
    try:
        _load_seed_data()
    except Exception as e:
        print(f"Note: Could not load seed data: {e}")
    
    return engine


def _load_seed_data():
    """Load seed data from CSV files if database is empty."""
    import csv
    from pathlib import Path
    
    session = get_session()
    try:
        # Check if we already have data
        if session.query(Property).count() > 0:
            return
        
        data_dir = Path(__file__).parent.parent / "data"
        
        # Helper functions
        def safe_int(val):
            if not val or val == '' or val == 'None':
                return None
            try:
                return int(float(val))
            except:
                return None
        
        def safe_float(val):
            if not val or val == '' or val == 'None':
                return None
            try:
                return float(val)
            except:
                return None
        
        # Create default collection run
        run = CollectionRun(id=1, status="completed", properties_found=0)
        session.merge(run)
        session.commit()
        
        # Load agents
        agents_csv = data_dir / "agents.csv"
        if agents_csv.exists():
            with open(agents_csv, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if safe_int(row.get("id")):
                        session.merge(Agent(
                            id=safe_int(row["id"]),
                            agency_name=row.get("agency_name") or None,
                        ))
            session.commit()
        
        # Load properties
        props_csv = data_dir / "properties.csv"
        if props_csv.exists():
            with open(props_csv, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if safe_int(row.get("id")):
                        session.merge(Property(
                            id=safe_int(row["id"]),
                            category=row.get("category") or "unknown",
                            subtype=safe_int(row.get("subtype")),
                            buy_or_rent=row.get("buy_or_rent") or "sale",
                            geography=row.get("geography") or None,
                            latitude=safe_float(row.get("latitude")),
                            longitude=safe_float(row.get("longitude")),
                            sq_meters=safe_int(row.get("sq_meters")),
                            floor_number=safe_int(row.get("floor_number")),
                            rooms=safe_int(row.get("rooms")),
                            bathrooms=safe_int(row.get("bathrooms")),
                            ad_type=row.get("ad_type") or None,
                            agent_id=safe_int(row.get("agent_id")),
                            is_active=row.get("is_active") in ("1", "True", "true"),
                        ))
            session.commit()
        
        # Load snapshots
        snaps_csv = data_dir / "snapshots.csv"
        if snaps_csv.exists():
            with open(snaps_csv, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if safe_int(row.get("id")) and safe_int(row.get("property_id")):
                        session.merge(PropertySnapshot(
                            id=safe_int(row["id"]),
                            property_id=safe_int(row["property_id"]),
                            collection_run_id=safe_int(row.get("collection_run_id")) or 1,
                            price=safe_int(row.get("price")) or 0,
                            price_per_sqm=safe_float(row.get("price_per_sqm")),
                        ))
            session.commit()
        
        count = session.query(Property).count()
        if count > 0:
            print(f"Loaded {count} properties from seed data")
    
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
