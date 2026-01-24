"""
Area analysis module.
Compares different neighborhoods and geographic regions.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import get_session, Property, PropertySnapshot, Area
from sqlalchemy import func


class AreaAnalyzer:
    """Analyzer for geographic area comparisons."""

    def __init__(self):
        self.session = get_session()

    def close(self):
        """Close the database session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_area_summary(self, min_listings: int = 3) -> pd.DataFrame:
        """
        Get summary statistics for each area.
        
        Returns:
            DataFrame with area statistics
        """
        # Get latest snapshot for each property
        latest_snapshot_subq = (
            self.session.query(
                PropertySnapshot.property_id,
                func.max(PropertySnapshot.collected_at).label("max_date")
            )
            .group_by(PropertySnapshot.property_id)
            .subquery()
        )
        
        query = (
            self.session.query(
                Property.geography,
                PropertySnapshot.price,
                PropertySnapshot.price_per_sqm,
                Property.sq_meters,
                Property.rooms,
                Property.category,
                Property.first_seen,
                Property.latitude,
                Property.longitude,
            )
            .join(PropertySnapshot, Property.id == PropertySnapshot.property_id)
            .join(
                latest_snapshot_subq,
                (PropertySnapshot.property_id == latest_snapshot_subq.c.property_id) &
                (PropertySnapshot.collected_at == latest_snapshot_subq.c.max_date)
            )
            .filter(Property.is_active == True)
            .filter(Property.geography.isnot(None))
        )
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=[
            "geography", "price", "price_per_sqm", "sq_meters",
            "rooms", "category", "first_seen", "latitude", "longitude"
        ])
        
        # Calculate days on market
        df["days_on_market"] = (datetime.utcnow() - df["first_seen"]).dt.days
        
        # Aggregate by area
        area_stats = df.groupby("geography").agg({
            "price": ["count", "mean", "median", "min", "max"],
            "price_per_sqm": ["mean", "median"],
            "sq_meters": ["mean", "median"],
            "rooms": "mean",
            "days_on_market": ["mean", "median"],
            "latitude": "mean",
            "longitude": "mean",
        })
        
        # Flatten column names
        area_stats.columns = [
            "listing_count", "avg_price", "median_price", "min_price", "max_price",
            "avg_price_per_sqm", "median_price_per_sqm",
            "avg_sq_meters", "median_sq_meters",
            "avg_rooms",
            "avg_days_on_market", "median_days_on_market",
            "center_lat", "center_lng",
        ]
        
        area_stats = area_stats.reset_index()
        area_stats = area_stats[area_stats["listing_count"] >= min_listings]
        
        # Round numeric columns
        numeric_cols = area_stats.select_dtypes(include=[np.number]).columns
        area_stats[numeric_cols] = area_stats[numeric_cols].round(2)
        
        return area_stats.sort_values("listing_count", ascending=False)

    def get_area_comparison(
        self,
        areas: List[str],
    ) -> pd.DataFrame:
        """
        Compare specific areas side by side.
        
        Args:
            areas: List of area names (partial match)
            
        Returns:
            DataFrame with comparison metrics
        """
        all_stats = self.get_area_summary(min_listings=1)
        
        # Filter to requested areas
        mask = all_stats["geography"].str.lower().apply(
            lambda x: any(area.lower() in x for area in areas)
        )
        
        return all_stats[mask]

    def get_area_price_heatmap_data(self) -> pd.DataFrame:
        """
        Get data for creating a price heatmap.
        
        Returns:
            DataFrame with lat, lng, and price data for map visualization
        """
        # Get latest snapshot for each property
        latest_snapshot_subq = (
            self.session.query(
                PropertySnapshot.property_id,
                func.max(PropertySnapshot.collected_at).label("max_date")
            )
            .group_by(PropertySnapshot.property_id)
            .subquery()
        )
        
        query = (
            self.session.query(
                Property.id,
                Property.latitude,
                Property.longitude,
                Property.geography,
                PropertySnapshot.price,
                PropertySnapshot.price_per_sqm,
                Property.sq_meters,
                Property.category,
            )
            .join(PropertySnapshot, Property.id == PropertySnapshot.property_id)
            .join(
                latest_snapshot_subq,
                (PropertySnapshot.property_id == latest_snapshot_subq.c.property_id) &
                (PropertySnapshot.collected_at == latest_snapshot_subq.c.max_date)
            )
            .filter(Property.is_active == True)
            .filter(Property.latitude.isnot(None))
            .filter(Property.longitude.isnot(None))
        )
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=[
            "id", "latitude", "longitude", "geography",
            "price", "price_per_sqm", "sq_meters", "category"
        ])
        
        return df

    def get_hottest_areas(
        self,
        days: int = 30,
        metric: str = "new_listings",
        limit: int = 10,
    ) -> pd.DataFrame:
        """
        Identify the hottest areas based on various metrics.
        
        Args:
            days: Period to analyze
            metric: 'new_listings', 'price_growth', or 'activity'
            limit: Number of areas to return
            
        Returns:
            DataFrame with hottest areas
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        if metric == "new_listings":
            # Areas with most new listings
            new_listings = (
                self.session.query(
                    Property.geography,
                    func.count(Property.id).label("new_listings")
                )
                .filter(Property.first_seen >= cutoff_date)
                .filter(Property.geography.isnot(None))
                .group_by(Property.geography)
                .order_by(func.count(Property.id).desc())
                .limit(limit)
                .all()
            )
            
            return pd.DataFrame(new_listings, columns=["geography", "new_listings"])
        
        elif metric == "price_growth":
            # Areas with highest price growth
            # Compare current vs previous period averages
            midpoint = datetime.utcnow() - timedelta(days=days // 2)
            
            query = (
                self.session.query(
                    Property.geography,
                    PropertySnapshot.price_per_sqm,
                    PropertySnapshot.collected_at,
                )
                .join(PropertySnapshot, Property.id == PropertySnapshot.property_id)
                .filter(PropertySnapshot.collected_at >= cutoff_date)
                .filter(PropertySnapshot.price_per_sqm.isnot(None))
                .filter(Property.geography.isnot(None))
            )
            
            results = query.all()
            
            if not results:
                return pd.DataFrame()
            
            df = pd.DataFrame(results, columns=["geography", "price_per_sqm", "date"])
            
            # Split into periods
            recent = df[df["date"] >= midpoint].groupby("geography")["price_per_sqm"].mean()
            older = df[df["date"] < midpoint].groupby("geography")["price_per_sqm"].mean()
            
            growth = ((recent - older) / older * 100).dropna()
            growth = growth.sort_values(ascending=False).head(limit)
            
            return pd.DataFrame({
                "geography": growth.index,
                "price_growth_pct": growth.values.round(2)
            })
        
        elif metric == "activity":
            # Areas with most price changes (high activity)
            query = (
                self.session.query(
                    Property.geography,
                    func.count(PropertySnapshot.id).label("snapshot_count")
                )
                .join(PropertySnapshot, Property.id == PropertySnapshot.property_id)
                .filter(PropertySnapshot.collected_at >= cutoff_date)
                .filter(Property.geography.isnot(None))
                .group_by(Property.geography)
                .order_by(func.count(PropertySnapshot.id).desc())
                .limit(limit)
            )
            
            results = query.all()
            
            return pd.DataFrame(results, columns=["geography", "activity_score"])
        
        return pd.DataFrame()

    def get_area_category_breakdown(self, area_filter: str) -> pd.DataFrame:
        """
        Get property category breakdown for a specific area.
        
        Returns:
            DataFrame with category counts and percentages
        """
        query = (
            self.session.query(
                Property.category,
                func.count(Property.id).label("count")
            )
            .filter(Property.is_active == True)
            .filter(Property.geography.ilike(f"%{area_filter}%"))
            .group_by(Property.category)
        )
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=["category", "count"])
        df["percentage"] = (df["count"] / df["count"].sum() * 100).round(2)
        
        return df.sort_values("count", ascending=False)
