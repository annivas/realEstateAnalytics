"""
Price trends analysis module.
Analyzes price per square meter trends over time by area and category.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import get_session, Property, PropertySnapshot, Area


class PriceTrendsAnalyzer:
    """Analyzer for price trends over time."""

    def __init__(self):
        self.session = get_session()

    def close(self):
        """Close the database session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_price_per_sqm_trends(
        self,
        days: int = 90,
        area_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        resample: str = "W",  # W=weekly, M=monthly, D=daily
    ) -> pd.DataFrame:
        """
        Get average price per square meter trends over time.
        
        Args:
            days: Number of days to look back
            area_filter: Filter by geography (partial match)
            category_filter: Filter by property category
            resample: Time resampling frequency ('D', 'W', 'M')
            
        Returns:
            DataFrame with date index and avg_price_per_sqm, count columns
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        query = (
            self.session.query(
                PropertySnapshot.collected_at,
                PropertySnapshot.price_per_sqm,
                Property.geography,
                Property.category,
            )
            .join(Property, PropertySnapshot.property_id == Property.id)
            .filter(PropertySnapshot.collected_at >= cutoff_date)
            .filter(PropertySnapshot.price_per_sqm.isnot(None))
            .filter(PropertySnapshot.price_per_sqm > 0)
        )
        
        if area_filter:
            query = query.filter(Property.geography.ilike(f"%{area_filter}%"))
        if category_filter:
            query = query.filter(Property.category == category_filter)
        
        results = query.all()
        
        if not results:
            return pd.DataFrame(columns=["date", "avg_price_per_sqm", "median_price_per_sqm", "count"])
        
        df = pd.DataFrame(results, columns=["date", "price_per_sqm", "geography", "category"])
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        
        # Resample and aggregate
        resampled = df["price_per_sqm"].resample(resample).agg(["mean", "median", "count"])
        resampled.columns = ["avg_price_per_sqm", "median_price_per_sqm", "count"]
        resampled = resampled.reset_index()
        resampled = resampled.dropna()
        
        return resampled

    def get_price_trends_by_area(
        self,
        days: int = 90,
        min_listings: int = 5,
    ) -> pd.DataFrame:
        """
        Get price trends broken down by area.
        
        Returns:
            DataFrame with area, current_avg, previous_avg, change_pct columns
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        midpoint_date = datetime.utcnow() - timedelta(days=days // 2)
        
        # Get all snapshots with area info
        query = (
            self.session.query(
                PropertySnapshot.collected_at,
                PropertySnapshot.price_per_sqm,
                Property.geography,
            )
            .join(Property, PropertySnapshot.property_id == Property.id)
            .filter(PropertySnapshot.collected_at >= cutoff_date)
            .filter(PropertySnapshot.price_per_sqm.isnot(None))
            .filter(PropertySnapshot.price_per_sqm > 0)
        )
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=["date", "price_per_sqm", "geography"])
        df["date"] = pd.to_datetime(df["date"])
        
        # Split into two periods
        df_recent = df[df["date"] >= midpoint_date]
        df_older = df[df["date"] < midpoint_date]
        
        # Calculate averages by area
        recent_avg = df_recent.groupby("geography")["price_per_sqm"].agg(["mean", "count"])
        recent_avg.columns = ["current_avg", "current_count"]
        
        older_avg = df_older.groupby("geography")["price_per_sqm"].agg(["mean", "count"])
        older_avg.columns = ["previous_avg", "previous_count"]
        
        # Merge
        trends = recent_avg.join(older_avg, how="outer").reset_index()
        trends = trends[trends["current_count"] >= min_listings]
        
        # Calculate change
        trends["change_pct"] = (
            (trends["current_avg"] - trends["previous_avg"]) / trends["previous_avg"] * 100
        ).round(2)
        
        trends = trends.sort_values("change_pct", ascending=False)
        
        return trends

    def get_price_distribution(
        self,
        category: Optional[str] = None,
        area_filter: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Get current price distribution statistics.
        
        Returns:
            DataFrame with statistics (min, max, mean, median, std, percentiles)
        """
        # Get latest snapshots
        subquery = (
            self.session.query(
                PropertySnapshot.property_id,
                PropertySnapshot.price,
                PropertySnapshot.price_per_sqm,
            )
            .distinct(PropertySnapshot.property_id)
            .order_by(PropertySnapshot.property_id, PropertySnapshot.collected_at.desc())
            .subquery()
        )
        
        query = (
            self.session.query(
                subquery.c.price,
                subquery.c.price_per_sqm,
                Property.category,
                Property.geography,
                Property.sq_meters,
            )
            .join(Property, subquery.c.property_id == Property.id)
            .filter(Property.is_active == True)
        )
        
        if category:
            query = query.filter(Property.category == category)
        if area_filter:
            query = query.filter(Property.geography.ilike(f"%{area_filter}%"))
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(
            results,
            columns=["price", "price_per_sqm", "category", "geography", "sq_meters"]
        )
        
        stats = {
            "total_listings": len(df),
            "price_min": df["price"].min(),
            "price_max": df["price"].max(),
            "price_mean": df["price"].mean(),
            "price_median": df["price"].median(),
            "price_std": df["price"].std(),
            "price_25pct": df["price"].quantile(0.25),
            "price_75pct": df["price"].quantile(0.75),
            "sqm_price_min": df["price_per_sqm"].min(),
            "sqm_price_max": df["price_per_sqm"].max(),
            "sqm_price_mean": df["price_per_sqm"].mean(),
            "sqm_price_median": df["price_per_sqm"].median(),
            "sqm_min": df["sq_meters"].min(),
            "sqm_max": df["sq_meters"].max(),
            "sqm_mean": df["sq_meters"].mean(),
        }
        
        return pd.DataFrame([stats])

    def get_monthly_summary(self, months: int = 6) -> pd.DataFrame:
        """
        Get monthly summary statistics.
        
        Returns:
            DataFrame with monthly aggregates
        """
        cutoff_date = datetime.utcnow() - timedelta(days=months * 30)
        
        query = (
            self.session.query(
                PropertySnapshot.collected_at,
                PropertySnapshot.price,
                PropertySnapshot.price_per_sqm,
                Property.category,
            )
            .join(Property, PropertySnapshot.property_id == Property.id)
            .filter(PropertySnapshot.collected_at >= cutoff_date)
            .filter(PropertySnapshot.price_per_sqm.isnot(None))
        )
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=["date", "price", "price_per_sqm", "category"])
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M")
        
        monthly = df.groupby("month").agg({
            "price": ["mean", "median", "count"],
            "price_per_sqm": ["mean", "median"],
        })
        
        monthly.columns = [
            "avg_price", "median_price", "listing_count",
            "avg_price_per_sqm", "median_price_per_sqm"
        ]
        
        monthly = monthly.reset_index()
        monthly["month"] = monthly["month"].astype(str)
        
        return monthly
