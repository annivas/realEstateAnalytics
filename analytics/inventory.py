"""
Inventory analysis module.
Analyzes listing counts, new vs existing listings, and days on market.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import get_session, Property, PropertySnapshot, CollectionRun


class InventoryAnalyzer:
    """Analyzer for market inventory metrics."""

    def __init__(self):
        self.session = get_session()

    def close(self):
        """Close the database session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_inventory_summary(self) -> dict:
        """
        Get current inventory summary statistics.
        
        Returns:
            Dictionary with key inventory metrics
        """
        # Total active listings
        total_active = (
            self.session.query(Property)
            .filter(Property.is_active == True)
            .count()
        )
        
        # Listings by category
        by_category = (
            self.session.query(Property.category, Property.id)
            .filter(Property.is_active == True)
            .all()
        )
        category_counts = pd.DataFrame(by_category, columns=["category", "id"])
        category_counts = category_counts.groupby("category").count().to_dict()["id"]
        
        # New listings in last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)
        new_this_week = (
            self.session.query(Property)
            .filter(Property.first_seen >= week_ago)
            .count()
        )
        
        # New listings in last 30 days
        month_ago = datetime.utcnow() - timedelta(days=30)
        new_this_month = (
            self.session.query(Property)
            .filter(Property.first_seen >= month_ago)
            .count()
        )
        
        # Average days on market for active listings
        active_properties = (
            self.session.query(Property.first_seen)
            .filter(Property.is_active == True)
            .all()
        )
        
        if active_properties:
            days_on_market = [
                (datetime.utcnow() - p.first_seen).days
                for p in active_properties
            ]
            avg_days_on_market = np.mean(days_on_market)
            median_days_on_market = np.median(days_on_market)
        else:
            avg_days_on_market = 0
            median_days_on_market = 0
        
        return {
            "total_active_listings": total_active,
            "listings_by_category": category_counts,
            "new_listings_this_week": new_this_week,
            "new_listings_this_month": new_this_month,
            "avg_days_on_market": round(avg_days_on_market, 1),
            "median_days_on_market": round(median_days_on_market, 1),
        }

    def get_inventory_trends(
        self,
        days: int = 90,
        resample: str = "W",
    ) -> pd.DataFrame:
        """
        Get inventory trends over time.
        
        Args:
            days: Number of days to look back
            resample: Time resampling frequency ('D', 'W', 'M')
            
        Returns:
            DataFrame with date, total_listings, new_listings columns
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get new listings per day
        new_listings = (
            self.session.query(Property.first_seen)
            .filter(Property.first_seen >= cutoff_date)
            .all()
        )
        
        if not new_listings:
            return pd.DataFrame(columns=["date", "new_listings"])
        
        df = pd.DataFrame(new_listings, columns=["first_seen"])
        df["first_seen"] = pd.to_datetime(df["first_seen"])
        df["count"] = 1
        df.set_index("first_seen", inplace=True)
        
        # Resample
        resampled = df["count"].resample(resample).sum().reset_index()
        resampled.columns = ["date", "new_listings"]
        
        # Calculate cumulative total for each period
        resampled["cumulative_new"] = resampled["new_listings"].cumsum()
        
        return resampled

    def get_days_on_market_distribution(
        self,
        category: Optional[str] = None,
        area_filter: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Get distribution of days on market for active listings.
        
        Returns:
            DataFrame with days_on_market and count columns
        """
        query = (
            self.session.query(Property.first_seen, Property.category, Property.geography)
            .filter(Property.is_active == True)
        )
        
        if category:
            query = query.filter(Property.category == category)
        if area_filter:
            query = query.filter(Property.geography.ilike(f"%{area_filter}%"))
        
        results = query.all()
        
        if not results:
            return pd.DataFrame(columns=["days_on_market", "count"])
        
        df = pd.DataFrame(results, columns=["first_seen", "category", "geography"])
        df["days_on_market"] = (datetime.utcnow() - df["first_seen"]).dt.days
        
        # Create bins
        bins = [0, 7, 14, 30, 60, 90, 180, 365, float("inf")]
        labels = ["0-7", "8-14", "15-30", "31-60", "61-90", "91-180", "181-365", "365+"]
        df["dom_bucket"] = pd.cut(df["days_on_market"], bins=bins, labels=labels)
        
        distribution = df.groupby("dom_bucket").size().reset_index(name="count")
        
        return distribution

    def get_collection_history(self, limit: int = 30) -> pd.DataFrame:
        """
        Get history of collection runs.
        
        Returns:
            DataFrame with collection run details
        """
        runs = (
            self.session.query(CollectionRun)
            .order_by(CollectionRun.started_at.desc())
            .limit(limit)
            .all()
        )
        
        if not runs:
            return pd.DataFrame()
        
        data = [
            {
                "id": run.id,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "status": run.status,
                "properties_found": run.properties_found,
                "new_properties": run.new_properties,
                "updated_properties": run.updated_properties,
                "price_changes": run.price_changes_detected,
            }
            for run in runs
        ]
        
        return pd.DataFrame(data)

    def get_listing_velocity(self, weeks: int = 8) -> pd.DataFrame:
        """
        Calculate listing velocity (new listings per week).
        
        Returns:
            DataFrame with week and metrics
        """
        cutoff_date = datetime.utcnow() - timedelta(weeks=weeks)
        
        new_listings = (
            self.session.query(Property.first_seen)
            .filter(Property.first_seen >= cutoff_date)
            .all()
        )
        
        if not new_listings:
            return pd.DataFrame()
        
        df = pd.DataFrame(new_listings, columns=["first_seen"])
        df["first_seen"] = pd.to_datetime(df["first_seen"])
        df["week"] = df["first_seen"].dt.isocalendar().week
        df["year"] = df["first_seen"].dt.year
        
        weekly = df.groupby(["year", "week"]).size().reset_index(name="new_listings")
        weekly["period"] = weekly["year"].astype(str) + "-W" + weekly["week"].astype(str).str.zfill(2)
        
        # Calculate week-over-week change
        weekly["wow_change"] = weekly["new_listings"].diff()
        weekly["wow_pct"] = (weekly["wow_change"] / weekly["new_listings"].shift(1) * 100).round(2)
        
        return weekly[["period", "new_listings", "wow_change", "wow_pct"]]
