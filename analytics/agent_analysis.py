"""
Agent/agency analysis module.
Analyzes real estate agent and agency performance metrics.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import get_session, Property, PropertySnapshot, Agent
from sqlalchemy import func


class AgentAnalyzer:
    """Analyzer for real estate agent and agency metrics."""

    def __init__(self):
        self.session = get_session()

    def close(self):
        """Close the database session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_agent_summary(self, min_listings: int = 2) -> pd.DataFrame:
        """
        Get summary statistics for each agent/agency.
        
        Returns:
            DataFrame with agent statistics
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
                Agent.id,
                Agent.agency_name,
                Property.id.label("property_id"),
                PropertySnapshot.price,
                PropertySnapshot.price_per_sqm,
                Property.sq_meters,
                Property.category,
                Property.ad_type,
                Property.has_virtual_tour,
                Property.image_count,
                Property.first_seen,
            )
            .join(Property, Agent.id == Property.agent_id)
            .join(PropertySnapshot, Property.id == PropertySnapshot.property_id)
            .join(
                latest_snapshot_subq,
                (PropertySnapshot.property_id == latest_snapshot_subq.c.property_id) &
                (PropertySnapshot.collected_at == latest_snapshot_subq.c.max_date)
            )
            .filter(Property.is_active == True)
        )
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=[
            "agent_id", "agency_name", "property_id", "price", "price_per_sqm",
            "sq_meters", "category", "ad_type", "has_vtour", "image_count", "first_seen"
        ])
        
        # Calculate days on market
        df["days_on_market"] = (datetime.utcnow() - df["first_seen"]).dt.days
        
        # Calculate quality score (0-100)
        df["quality_score"] = (
            (df["ad_type"].map({"vip": 30, "featured": 20, "standard": 10}).fillna(10)) +
            (df["has_vtour"].astype(int) * 20) +
            (df["image_count"].clip(0, 20) * 2.5)
        )
        
        # Aggregate by agent
        agent_stats = df.groupby(["agent_id", "agency_name"]).agg({
            "property_id": "count",
            "price": ["sum", "mean", "median"],
            "price_per_sqm": ["mean", "median"],
            "sq_meters": "mean",
            "days_on_market": "mean",
            "quality_score": "mean",
            "has_vtour": "sum",
        })
        
        # Flatten column names
        agent_stats.columns = [
            "listing_count", "total_value", "avg_price", "median_price",
            "avg_price_per_sqm", "median_price_per_sqm",
            "avg_sq_meters", "avg_days_on_market",
            "avg_quality_score", "vtour_count",
        ]
        
        agent_stats = agent_stats.reset_index()
        agent_stats = agent_stats[agent_stats["listing_count"] >= min_listings]
        
        # Calculate vtour percentage
        agent_stats["vtour_pct"] = (
            agent_stats["vtour_count"] / agent_stats["listing_count"] * 100
        ).round(1)
        
        # Round numeric columns
        numeric_cols = ["total_value", "avg_price", "median_price", "avg_price_per_sqm",
                       "median_price_per_sqm", "avg_sq_meters", "avg_days_on_market",
                       "avg_quality_score"]
        agent_stats[numeric_cols] = agent_stats[numeric_cols].round(2)
        
        return agent_stats.sort_values("listing_count", ascending=False)

    def get_top_agents(
        self,
        metric: str = "listing_count",
        limit: int = 10,
    ) -> pd.DataFrame:
        """
        Get top agents by a specific metric.
        
        Args:
            metric: 'listing_count', 'total_value', 'avg_quality_score'
            limit: Number of agents to return
            
        Returns:
            DataFrame with top agents
        """
        all_agents = self.get_agent_summary(min_listings=1)
        
        if all_agents.empty:
            return pd.DataFrame()
        
        valid_metrics = ["listing_count", "total_value", "avg_quality_score", "avg_price"]
        if metric not in valid_metrics:
            metric = "listing_count"
        
        return all_agents.nlargest(limit, metric)

    def get_agent_portfolio(self, agent_id: int) -> pd.DataFrame:
        """
        Get detailed portfolio for a specific agent.
        
        Returns:
            DataFrame with all properties for the agent
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
                Property.category,
                Property.geography,
                Property.sq_meters,
                Property.rooms,
                Property.ad_type,
                Property.first_seen,
                Property.main_image_url,
                PropertySnapshot.price,
                PropertySnapshot.price_per_sqm,
            )
            .join(PropertySnapshot, Property.id == PropertySnapshot.property_id)
            .join(
                latest_snapshot_subq,
                (PropertySnapshot.property_id == latest_snapshot_subq.c.property_id) &
                (PropertySnapshot.collected_at == latest_snapshot_subq.c.max_date)
            )
            .filter(Property.agent_id == agent_id)
            .filter(Property.is_active == True)
        )
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=[
            "id", "category", "geography", "sq_meters", "rooms",
            "ad_type", "first_seen", "image_url", "price", "price_per_sqm"
        ])
        
        df["days_on_market"] = (datetime.utcnow() - df["first_seen"]).dt.days
        
        return df.sort_values("price", ascending=False)

    def get_agent_pricing_comparison(self, min_listings: int = 3) -> pd.DataFrame:
        """
        Compare how agents price properties vs market average.
        
        Returns:
            DataFrame with agent pricing compared to market
        """
        agent_stats = self.get_agent_summary(min_listings=min_listings)
        
        if agent_stats.empty:
            return pd.DataFrame()
        
        # Calculate market averages
        market_avg_price_sqm = agent_stats["avg_price_per_sqm"].mean()
        market_median_price_sqm = agent_stats["median_price_per_sqm"].median()
        
        # Calculate deviation from market
        agent_stats["vs_market_avg_pct"] = (
            (agent_stats["avg_price_per_sqm"] - market_avg_price_sqm) / market_avg_price_sqm * 100
        ).round(2)
        
        agent_stats["vs_market_median_pct"] = (
            (agent_stats["median_price_per_sqm"] - market_median_price_sqm) / market_median_price_sqm * 100
        ).round(2)
        
        # Categorize pricing strategy
        agent_stats["pricing_strategy"] = agent_stats["vs_market_avg_pct"].apply(
            lambda x: "premium" if x > 10 else ("discount" if x < -10 else "market")
        )
        
        return agent_stats[[
            "agent_id", "agency_name", "listing_count",
            "avg_price_per_sqm", "vs_market_avg_pct", "vs_market_median_pct",
            "pricing_strategy", "avg_quality_score"
        ]].sort_values("vs_market_avg_pct", ascending=False)

    def get_market_share(self) -> pd.DataFrame:
        """
        Calculate market share by agent/agency.
        
        Returns:
            DataFrame with market share percentages
        """
        # Total active listings by agent
        query = (
            self.session.query(
                Agent.id,
                Agent.agency_name,
                func.count(Property.id).label("listing_count")
            )
            .join(Property, Agent.id == Property.agent_id)
            .filter(Property.is_active == True)
            .group_by(Agent.id, Agent.agency_name)
            .order_by(func.count(Property.id).desc())
        )
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=["agent_id", "agency_name", "listing_count"])
        
        total_listings = df["listing_count"].sum()
        df["market_share_pct"] = (df["listing_count"] / total_listings * 100).round(2)
        df["cumulative_share_pct"] = df["market_share_pct"].cumsum().round(2)
        
        return df

    def get_new_agent_activity(self, days: int = 30) -> pd.DataFrame:
        """
        Get recent activity for agents (new listings posted).
        
        Returns:
            DataFrame with agent activity in the period
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        query = (
            self.session.query(
                Agent.id,
                Agent.agency_name,
                func.count(Property.id).label("new_listings")
            )
            .join(Property, Agent.id == Property.agent_id)
            .filter(Property.first_seen >= cutoff_date)
            .group_by(Agent.id, Agent.agency_name)
            .order_by(func.count(Property.id).desc())
        )
        
        results = query.all()
        
        if not results:
            return pd.DataFrame()
        
        return pd.DataFrame(results, columns=["agent_id", "agency_name", "new_listings"])
