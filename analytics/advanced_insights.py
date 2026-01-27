"""
Advanced analytics for deeper market insights.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlalchemy import func, and_, or_, case

from database.models import (
    get_session, Property, PropertySnapshot, Agent, CollectionRun
)


class AdvancedInsightsAnalyzer:
    """Advanced market insights and analysis."""
    
    def __init__(self):
        self.session = None
    
    def __enter__(self):
        self.session = get_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
    
    # ==================== PRICE BENCHMARKS ====================
    
    def get_price_benchmarks_by_area(self, min_listings: int = 5) -> pd.DataFrame:
        """
        Calculate price benchmarks (fair price range) for each area.
        Returns min, max, avg, median, and percentiles.
        """
        query = """
            SELECT 
                p.geography,
                COUNT(*) as listing_count,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                MIN(ps.price_per_sqm) as min_price_sqm,
                MAX(ps.price_per_sqm) as max_price_sqm,
                AVG(ps.price) as avg_price,
                AVG(p.sq_meters) as avg_size
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 
              AND ps.price_per_sqm IS NOT NULL
              AND p.geography IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(*) >= :min_listings
            ORDER BY listing_count DESC
        """
        
        df = pd.read_sql(query, self.session.bind, params={"min_listings": min_listings})
        
        if df.empty:
            return df
        
        # Calculate fair price range (20th to 80th percentile approximation)
        df["fair_price_low"] = df["avg_price_sqm"] * 0.8
        df["fair_price_high"] = df["avg_price_sqm"] * 1.2
        
        return df
    
    def get_underpriced_properties(self, threshold_pct: float = 20, limit: int = 50) -> pd.DataFrame:
        """Find properties priced significantly below area average."""
        # First get area averages
        area_avg = """
            SELECT p.geography, AVG(ps.price_per_sqm) as area_avg_price_sqm
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 AND ps.price_per_sqm IS NOT NULL AND p.geography IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(*) >= 3
        """
        
        query = f"""
            WITH area_avgs AS ({area_avg})
            SELECT 
                p.id,
                p.geography,
                p.category,
                p.sq_meters,
                p.rooms,
                p.floor_number,
                ps.price,
                ps.price_per_sqm,
                aa.area_avg_price_sqm,
                ((aa.area_avg_price_sqm - ps.price_per_sqm) / aa.area_avg_price_sqm * 100) as discount_pct
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            JOIN area_avgs aa ON p.geography = aa.geography
            WHERE p.is_active = 1 
              AND ps.price_per_sqm IS NOT NULL
              AND ps.price_per_sqm < aa.area_avg_price_sqm * (1 - :threshold/100.0)
            ORDER BY discount_pct DESC
            LIMIT :limit
        """
        
        return pd.read_sql(query, self.session.bind, params={"threshold": threshold_pct, "limit": limit})
    
    # ==================== FLOOR PREMIUM ANALYSIS ====================
    
    def get_floor_premium_analysis(self) -> pd.DataFrame:
        """Analyze price premium by floor number."""
        query = """
            SELECT 
                CASE 
                    WHEN p.floor_number <= 0 THEN 'Ground/Basement'
                    WHEN p.floor_number BETWEEN 1 AND 2 THEN '1-2'
                    WHEN p.floor_number BETWEEN 3 AND 5 THEN '3-5'
                    WHEN p.floor_number BETWEEN 6 AND 10 THEN '6-10'
                    ELSE '10+'
                END as floor_group,
                p.floor_number,
                COUNT(*) as listing_count,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(ps.price) as avg_price,
                AVG(p.sq_meters) as avg_size
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 
              AND ps.price_per_sqm IS NOT NULL
              AND p.floor_number IS NOT NULL
            GROUP BY p.floor_number
            ORDER BY p.floor_number
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if df.empty:
            return df
        
        # Calculate premium vs ground floor
        ground_avg = df[df["floor_number"] <= 0]["avg_price_sqm"].mean()
        if ground_avg and ground_avg > 0:
            df["premium_vs_ground_pct"] = ((df["avg_price_sqm"] - ground_avg) / ground_avg * 100)
        else:
            df["premium_vs_ground_pct"] = 0
        
        return df
    
    def get_floor_premium_summary(self) -> pd.DataFrame:
        """Get summarized floor premium by floor groups."""
        query = """
            SELECT 
                CASE 
                    WHEN p.floor_number <= 0 THEN 'Ground/Basement'
                    WHEN p.floor_number BETWEEN 1 AND 2 THEN 'Low (1-2)'
                    WHEN p.floor_number BETWEEN 3 AND 5 THEN 'Mid (3-5)'
                    WHEN p.floor_number BETWEEN 6 AND 10 THEN 'High (6-10)'
                    ELSE 'Penthouse (10+)'
                END as floor_category,
                COUNT(*) as listing_count,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                MIN(ps.price_per_sqm) as min_price_sqm,
                MAX(ps.price_per_sqm) as max_price_sqm
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 
              AND ps.price_per_sqm IS NOT NULL
              AND p.floor_number IS NOT NULL
            GROUP BY floor_category
            ORDER BY avg_price_sqm
        """
        
        return pd.read_sql(query, self.session.bind)
    
    # ==================== DAYS ON MARKET ====================
    
    def get_days_on_market_analysis(self) -> pd.DataFrame:
        """Analyze days on market patterns."""
        query = """
            SELECT 
                p.id,
                p.geography,
                p.category,
                ps.price,
                ps.price_per_sqm,
                p.first_seen,
                julianday('now') - julianday(p.first_seen) as days_on_market
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if df.empty:
            return df
        
        df["days_on_market"] = df["days_on_market"].fillna(0).astype(int)
        return df
    
    def get_stale_listings(self, min_days: int = 60, limit: int = 50) -> pd.DataFrame:
        """Find listings that have been on market for a long time (motivated sellers)."""
        query = """
            SELECT 
                p.id,
                p.geography,
                p.category,
                p.sq_meters,
                p.rooms,
                ps.price,
                ps.price_per_sqm,
                p.first_seen,
                CAST(julianday('now') - julianday(p.first_seen) AS INTEGER) as days_on_market,
                a.agency_name
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            LEFT JOIN agents a ON p.agent_id = a.id
            WHERE p.is_active = 1
              AND julianday('now') - julianday(p.first_seen) >= :min_days
            ORDER BY days_on_market DESC
            LIMIT :limit
        """
        
        return pd.read_sql(query, self.session.bind, params={"min_days": min_days, "limit": limit})
    
    def get_dom_by_area(self, min_listings: int = 3) -> pd.DataFrame:
        """Get average days on market by area."""
        query = """
            SELECT 
                p.geography,
                COUNT(*) as listing_count,
                AVG(julianday('now') - julianday(p.first_seen)) as avg_days_on_market,
                MIN(julianday('now') - julianday(p.first_seen)) as min_dom,
                MAX(julianday('now') - julianday(p.first_seen)) as max_dom
            FROM properties p
            WHERE p.is_active = 1 AND p.geography IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(*) >= :min_listings
            ORDER BY avg_days_on_market ASC
        """
        
        df = pd.read_sql(query, self.session.bind, params={"min_listings": min_listings})
        
        if not df.empty:
            df["market_speed"] = pd.cut(
                df["avg_days_on_market"], 
                bins=[0, 30, 60, 90, float('inf')],
                labels=["Hot", "Normal", "Slow", "Very Slow"]
            )
        
        return df
    
    # ==================== SIZE EFFICIENCY ====================
    
    def get_size_efficiency_analysis(self) -> pd.DataFrame:
        """Analyze price per sqm by property size brackets."""
        query = """
            SELECT 
                CASE 
                    WHEN p.sq_meters < 50 THEN 'Studio (<50 sqm)'
                    WHEN p.sq_meters BETWEEN 50 AND 80 THEN 'Small (50-80 sqm)'
                    WHEN p.sq_meters BETWEEN 81 AND 120 THEN 'Medium (81-120 sqm)'
                    WHEN p.sq_meters BETWEEN 121 AND 180 THEN 'Large (121-180 sqm)'
                    ELSE 'Very Large (180+ sqm)'
                END as size_category,
                COUNT(*) as listing_count,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(ps.price) as avg_price,
                AVG(p.sq_meters) as avg_size,
                MIN(ps.price) as min_price,
                MAX(ps.price) as max_price
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 
              AND ps.price_per_sqm IS NOT NULL
              AND p.sq_meters IS NOT NULL
            GROUP BY size_category
            ORDER BY avg_size
        """
        
        return pd.read_sql(query, self.session.bind)
    
    # ==================== LISTING TYPE ANALYSIS ====================
    
    def get_listing_type_analysis(self) -> pd.DataFrame:
        """Analyze VIP vs Featured vs Standard listings."""
        query = """
            SELECT 
                COALESCE(p.ad_type, 'standard') as listing_type,
                COUNT(*) as listing_count,
                AVG(ps.price) as avg_price,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(p.sq_meters) as avg_size,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) as reduced_count,
                AVG(julianday('now') - julianday(p.first_seen)) as avg_days_on_market
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1
            GROUP BY listing_type
            ORDER BY listing_count DESC
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if not df.empty:
            total = df["listing_count"].sum()
            df["pct_of_market"] = (df["listing_count"] / total * 100).round(1)
            df["reduction_rate"] = (df["reduced_count"] / df["listing_count"] * 100).round(1)
        
        return df
    
    # ==================== MOTIVATED SELLER SCORE ====================
    
    def get_motivated_seller_scores(self, limit: int = 50) -> pd.DataFrame:
        """
        Calculate a 'motivated seller' score based on multiple factors:
        - Days on market (longer = more motivated)
        - Price reductions (reduced = more motivated)
        - Below area average price (cheaper = more motivated)
        """
        area_avg = """
            SELECT p.geography, AVG(ps.price_per_sqm) as area_avg
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 AND ps.price_per_sqm IS NOT NULL AND p.geography IS NOT NULL
            GROUP BY p.geography
        """
        
        query = f"""
            WITH area_avgs AS ({area_avg})
            SELECT 
                p.id,
                p.geography,
                p.category,
                p.sq_meters,
                p.rooms,
                ps.price,
                ps.price_per_sqm,
                ps.price_reduced,
                CAST(julianday('now') - julianday(p.first_seen) AS INTEGER) as days_on_market,
                aa.area_avg,
                a.agency_name,
                -- Score components (each 0-10)
                MIN(10, CAST(julianday('now') - julianday(p.first_seen) AS INTEGER) / 9.0) as dom_score,
                CASE WHEN ps.price_reduced = 1 THEN 10 ELSE 0 END as reduction_score,
                CASE 
                    WHEN ps.price_per_sqm < aa.area_avg * 0.8 THEN 10
                    WHEN ps.price_per_sqm < aa.area_avg * 0.9 THEN 7
                    WHEN ps.price_per_sqm < aa.area_avg THEN 4
                    ELSE 0 
                END as price_score
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            LEFT JOIN area_avgs aa ON p.geography = aa.geography
            LEFT JOIN agents a ON p.agent_id = a.id
            WHERE p.is_active = 1
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if df.empty:
            return df
        
        # Calculate total score (weighted average)
        df["dom_score"] = df["dom_score"].fillna(0)
        df["reduction_score"] = df["reduction_score"].fillna(0)
        df["price_score"] = df["price_score"].fillna(0)
        
        df["motivated_score"] = (
            df["dom_score"] * 0.4 +      # 40% weight on days on market
            df["reduction_score"] * 0.35 + # 35% weight on price reduction
            df["price_score"] * 0.25       # 25% weight on below-average price
        ).round(1)
        
        df["motivation_level"] = pd.cut(
            df["motivated_score"],
            bins=[0, 3, 5, 7, 10],
            labels=["Low", "Medium", "High", "Very High"]
        )
        
        return df.sort_values("motivated_score", ascending=False).head(limit)
    
    # ==================== INVESTMENT SCORING ====================
    
    def get_investment_area_scores(self, min_listings: int = 5) -> pd.DataFrame:
        """
        Score areas for investment potential based on:
        - Price per sqm (lower = better value)
        - New listings growth (more = growing area)
        - Days on market (lower = liquid market)
        """
        query = """
            SELECT 
                p.geography,
                COUNT(*) as listing_count,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(julianday('now') - julianday(p.first_seen)) as avg_dom,
                SUM(CASE WHEN julianday('now') - julianday(p.first_seen) <= 30 THEN 1 ELSE 0 END) as new_listings_30d,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) as reduced_count
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 AND p.geography IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(*) >= :min_listings
        """
        
        df = pd.read_sql(query, self.session.bind, params={"min_listings": min_listings})
        
        if df.empty:
            return df
        
        # Normalize scores (0-10 scale)
        # Value score: lower price = higher score
        price_min, price_max = df["avg_price_sqm"].min(), df["avg_price_sqm"].max()
        if price_max > price_min:
            df["value_score"] = 10 - ((df["avg_price_sqm"] - price_min) / (price_max - price_min) * 10)
        else:
            df["value_score"] = 5
        
        # Liquidity score: lower DOM = higher score
        dom_min, dom_max = df["avg_dom"].min(), df["avg_dom"].max()
        if dom_max > dom_min:
            df["liquidity_score"] = 10 - ((df["avg_dom"] - dom_min) / (dom_max - dom_min) * 10)
        else:
            df["liquidity_score"] = 5
        
        # Activity score: more new listings = higher score
        activity_max = df["new_listings_30d"].max()
        if activity_max > 0:
            df["activity_score"] = (df["new_listings_30d"] / activity_max * 10)
        else:
            df["activity_score"] = 5
        
        # Overall investment score
        df["investment_score"] = (
            df["value_score"] * 0.4 +
            df["liquidity_score"] * 0.35 +
            df["activity_score"] * 0.25
        ).round(1)
        
        df["investment_rating"] = pd.cut(
            df["investment_score"],
            bins=[0, 4, 6, 8, 10],
            labels=["Avoid", "Fair", "Good", "Excellent"]
        )
        
        return df.sort_values("investment_score", ascending=False)
    
    # ==================== PRICE VELOCITY ====================
    
    def get_price_velocity_by_area(self, days: int = 30) -> pd.DataFrame:
        """
        Calculate price momentum/velocity by area.
        Compares recent prices to older prices.
        """
        # This requires multiple snapshots over time
        # For now, we'll estimate based on current vs initial prices
        query = """
            SELECT 
                p.geography,
                COUNT(DISTINCT p.id) as property_count,
                AVG(ps.price_per_sqm) as current_avg_price_sqm,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) as reductions,
                AVG(ps.price_change_percentage) as avg_price_change
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 
              AND p.geography IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(DISTINCT p.id) >= 3
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if df.empty:
            return df
        
        # Calculate reduction rate as proxy for price pressure
        df["reduction_rate"] = (df["reductions"] / df["property_count"] * 100).round(1)
        
        # Estimate price direction
        df["price_direction"] = df["avg_price_change"].apply(
            lambda x: "Rising" if x and x > 0 else ("Falling" if x and x < 0 else "Stable")
        )
        
        return df.sort_values("reduction_rate", ascending=False)
