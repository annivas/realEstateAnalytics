"""
Price reduction analysis module.
Tracks price drops and identifies potential deals.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import get_session, Property, PropertySnapshot


class PriceReductionAnalyzer:
    """Analyzer for price reductions and deals."""

    def __init__(self):
        self.session = get_session()

    def close(self):
        """Close the database session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_recent_price_drops(
        self,
        days: int = 30,
        min_reduction_pct: float = 5.0,
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        Get properties with recent price reductions.
        
        Args:
            days: Look back period in days
            min_reduction_pct: Minimum reduction percentage to include
            limit: Maximum number of results
            
        Returns:
            DataFrame with property details and price change info
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get snapshots with price reductions flagged by API
        flagged_reductions = (
            self.session.query(
                Property.id,
                Property.category,
                Property.geography,
                Property.sq_meters,
                Property.rooms,
                Property.main_image_url,
                Property.latitude,
                Property.longitude,
                PropertySnapshot.price,
                PropertySnapshot.price_pre_reduction,
                PropertySnapshot.price_change_percentage,
                PropertySnapshot.collected_at,
            )
            .join(PropertySnapshot, Property.id == PropertySnapshot.property_id)
            .filter(PropertySnapshot.collected_at >= cutoff_date)
            .filter(PropertySnapshot.price_reduced == True)
            .filter(Property.is_active == True)
            .order_by(PropertySnapshot.collected_at.desc())
            .limit(limit)
            .all()
        )
        
        if not flagged_reductions:
            return pd.DataFrame()
        
        df = pd.DataFrame(flagged_reductions, columns=[
            "id", "category", "geography", "sq_meters", "rooms",
            "image_url", "latitude", "longitude",
            "current_price", "original_price", "change_pct", "date"
        ])
        
        # Calculate reduction percentage if not provided
        df["reduction_pct"] = df.apply(
            lambda row: row["change_pct"] if row["change_pct"] 
            else ((row["original_price"] - row["current_price"]) / row["original_price"] * 100 
                  if row["original_price"] else 0),
            axis=1
        )
        
        # Filter by minimum reduction
        df = df[abs(df["reduction_pct"]) >= min_reduction_pct]
        
        # Calculate price per sqm
        df["price_per_sqm"] = (df["current_price"] / df["sq_meters"]).round(0)
        
        # Calculate savings
        df["savings"] = df["original_price"] - df["current_price"]
        
        return df.sort_values("reduction_pct", ascending=True)

    def detect_price_changes(
        self,
        days: int = 7,
    ) -> pd.DataFrame:
        """
        Detect price changes by comparing consecutive snapshots.
        
        This catches price changes that weren't flagged by the API.
        
        Returns:
            DataFrame with properties that had price changes
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get all snapshots in the period
        snapshots = (
            self.session.query(
                PropertySnapshot.property_id,
                PropertySnapshot.price,
                PropertySnapshot.collected_at,
            )
            .filter(PropertySnapshot.collected_at >= cutoff_date - timedelta(days=days))
            .order_by(PropertySnapshot.property_id, PropertySnapshot.collected_at)
            .all()
        )
        
        if not snapshots:
            return pd.DataFrame()
        
        df = pd.DataFrame(snapshots, columns=["property_id", "price", "date"])
        
        # Find price changes
        df["prev_price"] = df.groupby("property_id")["price"].shift(1)
        df["price_change"] = df["price"] - df["prev_price"]
        df["change_pct"] = (df["price_change"] / df["prev_price"] * 100).round(2)
        
        # Filter to only rows with price changes
        changes = df[df["price_change"].notna() & (df["price_change"] != 0)].copy()
        
        if changes.empty:
            return pd.DataFrame()
        
        # Get property details
        property_ids = changes["property_id"].unique().tolist()
        properties = (
            self.session.query(
                Property.id,
                Property.category,
                Property.geography,
                Property.sq_meters,
            )
            .filter(Property.id.in_(property_ids))
            .all()
        )
        
        prop_df = pd.DataFrame(properties, columns=["property_id", "category", "geography", "sq_meters"])
        
        result = changes.merge(prop_df, on="property_id")
        
        # Categorize changes
        result["change_type"] = result["price_change"].apply(
            lambda x: "decrease" if x < 0 else "increase"
        )
        
        return result.sort_values("change_pct")

    def get_deal_alerts(
        self,
        max_price_per_sqm_percentile: float = 25,
        min_days_on_market: int = 30,
    ) -> pd.DataFrame:
        """
        Identify potential deals based on price per sqm and time on market.
        
        Properties priced below market average that have been listed for a while
        might be more negotiable.
        
        Returns:
            DataFrame with potential deals
        """
        # Get latest price for all active properties
        # Using a subquery to get the most recent snapshot for each property
        from sqlalchemy import func
        
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
                Property.category,
                Property.geography,
                Property.sq_meters,
                Property.rooms,
                Property.first_seen,
                Property.main_image_url,
                Property.latitude,
                Property.longitude,
                PropertySnapshot.price,
                PropertySnapshot.price_per_sqm,
            )
            .join(PropertySnapshot, Property.id == PropertySnapshot.property_id)
            .join(
                latest_snapshot_subq,
                (PropertySnapshot.property_id == latest_snapshot_subq.c.property_id) &
                (PropertySnapshot.collected_at == latest_snapshot_subq.c.max_date)
            )
            .filter(Property.is_active == True)
            .filter(PropertySnapshot.price_per_sqm.isnot(None))
            .filter(PropertySnapshot.price_per_sqm > 0)
        )
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=[
            "id", "category", "geography", "sq_meters", "rooms",
            "first_seen", "image_url", "latitude", "longitude",
            "price", "price_per_sqm"
        ])
        
        # Calculate days on market
        df["days_on_market"] = (datetime.utcnow() - df["first_seen"]).dt.days
        
        # Calculate price per sqm percentile
        df["price_percentile"] = df["price_per_sqm"].rank(pct=True) * 100
        
        # Filter for potential deals
        deals = df[
            (df["price_percentile"] <= max_price_per_sqm_percentile) &
            (df["days_on_market"] >= min_days_on_market)
        ].copy()
        
        # Add market comparison
        market_median = df["price_per_sqm"].median()
        deals["vs_market_median"] = (
            (deals["price_per_sqm"] - market_median) / market_median * 100
        ).round(2)
        
        return deals.sort_values("price_percentile")

    def get_price_reduction_stats(self, days: int = 30) -> dict:
        """
        Get summary statistics about price reductions.
        
        Returns:
            Dictionary with reduction statistics
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Count reductions flagged by API
        flagged_count = (
            self.session.query(PropertySnapshot)
            .filter(PropertySnapshot.collected_at >= cutoff_date)
            .filter(PropertySnapshot.price_reduced == True)
            .count()
        )
        
        # Get reduction amounts
        reductions = (
            self.session.query(
                PropertySnapshot.price,
                PropertySnapshot.price_pre_reduction,
                PropertySnapshot.price_change_percentage,
            )
            .filter(PropertySnapshot.collected_at >= cutoff_date)
            .filter(PropertySnapshot.price_reduced == True)
            .filter(PropertySnapshot.price_pre_reduction.isnot(None))
            .all()
        )
        
        if reductions:
            df = pd.DataFrame(reductions, columns=["price", "original", "change_pct"])
            df["reduction_amount"] = df["original"] - df["price"]
            df["reduction_pct"] = abs(df["change_pct"])
            
            avg_reduction_amount = df["reduction_amount"].mean()
            avg_reduction_pct = df["reduction_pct"].mean()
            max_reduction_pct = df["reduction_pct"].max()
            total_value_reduced = df["reduction_amount"].sum()
        else:
            avg_reduction_amount = 0
            avg_reduction_pct = 0
            max_reduction_pct = 0
            total_value_reduced = 0
        
        # Total active listings for context
        total_active = (
            self.session.query(Property)
            .filter(Property.is_active == True)
            .count()
        )
        
        return {
            "period_days": days,
            "total_reductions": flagged_count,
            "total_active_listings": total_active,
            "reduction_rate_pct": round(flagged_count / total_active * 100, 2) if total_active else 0,
            "avg_reduction_amount": round(avg_reduction_amount, 0),
            "avg_reduction_pct": round(avg_reduction_pct, 2),
            "max_reduction_pct": round(max_reduction_pct, 2),
            "total_value_reduced": round(total_value_reduced, 0),
        }
