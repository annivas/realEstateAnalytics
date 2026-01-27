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
    
    # ==================== DEMAND ANALYSIS ====================
    
    def get_demand_profile(self, fast_threshold_days: int = 30) -> Dict:
        """
        Analyze what the market wants by comparing fast-selling vs slow-selling properties.
        Returns a profile of high-demand attributes.
        """
        query = """
            SELECT 
                p.id,
                p.geography,
                p.category,
                p.sq_meters,
                p.rooms,
                p.floor_number,
                ps.price,
                ps.price_per_sqm,
                ps.price_reduced,
                p.is_active,
                CAST(julianday('now') - julianday(p.first_seen) AS INTEGER) as days_on_market
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.geography IS NOT NULL
              AND p.sq_meters > 0
              AND ps.price_per_sqm IS NOT NULL
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if df.empty or len(df) < 20:
            return {"error": "Not enough data for demand analysis"}
        
        # Classify properties by market speed
        # Fast = sold quickly or low DOM while active
        # Slow = high DOM while still active
        df["market_speed"] = pd.cut(
            df["days_on_market"],
            bins=[0, fast_threshold_days, 60, 90, float("inf")],
            labels=["Fast", "Moderate", "Slow", "Very Slow"]
        )
        
        fast_props = df[df["market_speed"] == "Fast"]
        slow_props = df[df["market_speed"].isin(["Slow", "Very Slow"])]
        
        profile = {
            "total_analyzed": len(df),
            "fast_selling_count": len(fast_props),
            "slow_selling_count": len(slow_props),
        }
        
        # Analyze each attribute
        if not fast_props.empty and not slow_props.empty:
            # Price analysis
            profile["price"] = {
                "fast_avg": fast_props["price"].mean(),
                "slow_avg": slow_props["price"].mean(),
                "fast_median": fast_props["price"].median(),
                "slow_median": slow_props["price"].median(),
            }
            
            # Price per sqm
            profile["price_per_sqm"] = {
                "fast_avg": fast_props["price_per_sqm"].mean(),
                "slow_avg": slow_props["price_per_sqm"].mean(),
            }
            
            # Size analysis
            profile["size"] = {
                "fast_avg": fast_props["sq_meters"].mean(),
                "slow_avg": slow_props["sq_meters"].mean(),
                "fast_median": fast_props["sq_meters"].median(),
                "slow_median": slow_props["sq_meters"].median(),
            }
            
            # Rooms analysis
            profile["rooms"] = {
                "fast_avg": fast_props["rooms"].mean(),
                "slow_avg": slow_props["rooms"].mean(),
            }
            
            # Floor analysis
            fast_floors = fast_props[fast_props["floor_number"].notna()]
            slow_floors = slow_props[slow_props["floor_number"].notna()]
            if not fast_floors.empty and not slow_floors.empty:
                profile["floor"] = {
                    "fast_avg": fast_floors["floor_number"].mean(),
                    "slow_avg": slow_floors["floor_number"].mean(),
                }
        
        return profile
    
    def get_high_demand_areas(self, min_listings: int = 5) -> pd.DataFrame:
        """
        Identify areas with highest demand based on:
        - Lower average days on market
        - Lower price reduction rate
        - Higher listing turnover
        """
        query = """
            SELECT 
                p.geography,
                COUNT(*) as total_listings,
                AVG(CAST(julianday('now') - julianday(p.first_seen) AS INTEGER)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as reduction_rate,
                SUM(CASE WHEN julianday('now') - julianday(p.first_seen) <= 30 THEN 1 ELSE 0 END) as fast_movers,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(p.sq_meters) as avg_size
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 
              AND p.geography IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(*) >= :min_listings
        """
        
        df = pd.read_sql(query, self.session.bind, params={"min_listings": min_listings})
        
        if df.empty:
            return df
        
        # Calculate demand score (lower DOM + lower reduction = higher demand)
        # Normalize each component to 0-10 scale
        df["dom_score"] = 10 - (df["avg_dom"].clip(0, 90) / 9)  # Lower DOM = higher score
        df["reduction_score"] = 10 - (df["reduction_rate"].clip(0, 50) / 5)  # Lower reduction = higher score
        df["velocity_score"] = (df["fast_movers"] / df["total_listings"] * 10).clip(0, 10)  # Higher fast movers = higher score
        
        df["demand_score"] = (
            df["dom_score"] * 0.4 +
            df["reduction_score"] * 0.3 +
            df["velocity_score"] * 0.3
        ).round(1)
        
        df["demand_level"] = pd.cut(
            df["demand_score"],
            bins=[0, 4, 6, 8, 10],
            labels=["Low", "Moderate", "High", "Very High"]
        )
        
        return df.sort_values("demand_score", ascending=False)
    
    def get_demand_by_size_range(self) -> pd.DataFrame:
        """Analyze demand by property size ranges."""
        query = """
            SELECT 
                CASE 
                    WHEN p.sq_meters < 50 THEN 'Studio/Small (<50 sqm)'
                    WHEN p.sq_meters < 80 THEN '1-2 BR (50-80 sqm)'
                    WHEN p.sq_meters < 120 THEN '2-3 BR (80-120 sqm)'
                    WHEN p.sq_meters < 180 THEN 'Large (120-180 sqm)'
                    ELSE 'Very Large (180+ sqm)'
                END as size_range,
                COUNT(*) as listings,
                AVG(CAST(julianday('now') - julianday(p.first_seen) AS INTEGER)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as reduction_rate,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(ps.price) as avg_price
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 AND p.sq_meters > 0
            GROUP BY size_range
            ORDER BY 
                CASE size_range
                    WHEN 'Studio/Small (<50 sqm)' THEN 1
                    WHEN '1-2 BR (50-80 sqm)' THEN 2
                    WHEN '2-3 BR (80-120 sqm)' THEN 3
                    WHEN 'Large (120-180 sqm)' THEN 4
                    ELSE 5
                END
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if not df.empty:
            # Lower DOM and reduction rate = higher demand
            df["demand_indicator"] = df.apply(
                lambda r: "🔥 High" if r["avg_dom"] < 40 and r["reduction_rate"] < 20 
                else ("📈 Good" if r["avg_dom"] < 60 else "📉 Low"),
                axis=1
            )
        
        return df
    
    def get_demand_by_floor(self) -> pd.DataFrame:
        """Analyze demand by floor level."""
        query = """
            SELECT 
                CASE 
                    WHEN p.floor_number < 0 THEN 'Basement'
                    WHEN p.floor_number = 0 THEN 'Ground Floor'
                    WHEN p.floor_number BETWEEN 1 AND 2 THEN 'Low (1-2)'
                    WHEN p.floor_number BETWEEN 3 AND 5 THEN 'Mid (3-5)'
                    WHEN p.floor_number > 5 THEN 'High (6+)'
                    ELSE 'Unknown'
                END as floor_category,
                p.floor_number as floor_order,
                COUNT(*) as listings,
                AVG(CAST(julianday('now') - julianday(p.first_seen) AS INTEGER)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as reduction_rate,
                AVG(ps.price_per_sqm) as avg_price_sqm
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 AND p.floor_number IS NOT NULL
            GROUP BY floor_category
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if not df.empty:
            df["demand_indicator"] = df.apply(
                lambda r: "🔥 High" if r["avg_dom"] < 40 and r["reduction_rate"] < 20 
                else ("📈 Good" if r["avg_dom"] < 60 else "📉 Low"),
                axis=1
            )
            # Sort by floor order
            floor_order = {"Basement": 0, "Ground Floor": 1, "Low (1-2)": 2, "Mid (3-5)": 3, "High (6+)": 4, "Unknown": 5}
            df["sort_order"] = df["floor_category"].map(floor_order)
            df = df.sort_values("sort_order").drop("sort_order", axis=1)
        
        return df
    
    def get_demand_by_category(self) -> pd.DataFrame:
        """Analyze demand by property category (apartment, house, etc.)."""
        query = """
            SELECT 
                p.category,
                COUNT(*) as listings,
                AVG(CAST(julianday('now') - julianday(p.first_seen) AS INTEGER)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as reduction_rate,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(ps.price) as avg_price,
                AVG(p.sq_meters) as avg_size
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 AND p.category IS NOT NULL
            GROUP BY p.category
            HAVING COUNT(*) >= 3
            ORDER BY avg_dom ASC
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if not df.empty:
            df["demand_indicator"] = df.apply(
                lambda r: "🔥 High" if r["avg_dom"] < 40 and r["reduction_rate"] < 20 
                else ("📈 Good" if r["avg_dom"] < 60 else "📉 Low"),
                axis=1
            )
        
        return df
    
    def get_demand_by_price_range(self) -> pd.DataFrame:
        """Analyze demand by price ranges."""
        query = """
            SELECT 
                CASE 
                    WHEN ps.price < 100000 THEN 'Budget (<€100K)'
                    WHEN ps.price < 200000 THEN 'Entry (€100-200K)'
                    WHEN ps.price < 350000 THEN 'Mid-Range (€200-350K)'
                    WHEN ps.price < 500000 THEN 'Upper (€350-500K)'
                    WHEN ps.price < 750000 THEN 'Premium (€500-750K)'
                    ELSE 'Luxury (€750K+)'
                END as price_range,
                COUNT(*) as listings,
                AVG(CAST(julianday('now') - julianday(p.first_seen) AS INTEGER)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as reduction_rate,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(p.sq_meters) as avg_size
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 AND ps.price > 0
            GROUP BY price_range
            ORDER BY 
                CASE price_range
                    WHEN 'Budget (<€100K)' THEN 1
                    WHEN 'Entry (€100-200K)' THEN 2
                    WHEN 'Mid-Range (€200-350K)' THEN 3
                    WHEN 'Upper (€350-500K)' THEN 4
                    WHEN 'Premium (€500-750K)' THEN 5
                    ELSE 6
                END
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if not df.empty:
            df["demand_indicator"] = df.apply(
                lambda r: "🔥 High" if r["avg_dom"] < 40 and r["reduction_rate"] < 20 
                else ("📈 Good" if r["avg_dom"] < 60 else "📉 Low"),
                axis=1
            )
        
        return df
    
    def get_demand_by_rooms(self) -> pd.DataFrame:
        """Analyze demand by number of rooms."""
        query = """
            SELECT 
                CASE 
                    WHEN p.rooms = 0 OR p.rooms IS NULL THEN 'Studio'
                    WHEN p.rooms = 1 THEN '1 Room'
                    WHEN p.rooms = 2 THEN '2 Rooms'
                    WHEN p.rooms = 3 THEN '3 Rooms'
                    WHEN p.rooms = 4 THEN '4 Rooms'
                    ELSE '5+ Rooms'
                END as room_count,
                COUNT(*) as listings,
                AVG(CAST(julianday('now') - julianday(p.first_seen) AS INTEGER)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as reduction_rate,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(ps.price) as avg_price
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1
            GROUP BY room_count
            ORDER BY 
                CASE room_count
                    WHEN 'Studio' THEN 0
                    WHEN '1 Room' THEN 1
                    WHEN '2 Rooms' THEN 2
                    WHEN '3 Rooms' THEN 3
                    WHEN '4 Rooms' THEN 4
                    ELSE 5
                END
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if not df.empty:
            df["demand_indicator"] = df.apply(
                lambda r: "🔥 High" if r["avg_dom"] < 40 and r["reduction_rate"] < 20 
                else ("📈 Good" if r["avg_dom"] < 60 else "📉 Low"),
                axis=1
            )
        
        return df
    
    def get_market_demand_summary(self) -> Dict:
        """
        Generate a comprehensive summary of what the market wants.
        Returns the top demanded attributes across all dimensions.
        """
        summary = {}
        
        # Best performing areas
        areas = self.get_high_demand_areas(min_listings=3)
        if not areas.empty:
            top_areas = areas.head(5)
            summary["top_areas"] = top_areas[["geography", "demand_score", "avg_dom", "avg_price_sqm"]].to_dict("records")
        
        # Best performing size range
        sizes = self.get_demand_by_size_range()
        if not sizes.empty:
            best_size = sizes.loc[sizes["avg_dom"].idxmin()]
            summary["best_size"] = {
                "range": best_size["size_range"],
                "avg_dom": best_size["avg_dom"],
                "avg_price": best_size["avg_price"],
            }
        
        # Best performing floor
        floors = self.get_demand_by_floor()
        if not floors.empty:
            best_floor = floors.loc[floors["avg_dom"].idxmin()]
            summary["best_floor"] = {
                "level": best_floor["floor_category"],
                "avg_dom": best_floor["avg_dom"],
            }
        
        # Best performing price range
        prices = self.get_demand_by_price_range()
        if not prices.empty:
            best_price = prices.loc[prices["avg_dom"].idxmin()]
            summary["best_price_range"] = {
                "range": best_price["price_range"],
                "avg_dom": best_price["avg_dom"],
            }
        
        # Best performing room count
        rooms = self.get_demand_by_rooms()
        if not rooms.empty:
            best_rooms = rooms.loc[rooms["avg_dom"].idxmin()]
            summary["best_rooms"] = {
                "count": best_rooms["room_count"],
                "avg_dom": best_rooms["avg_dom"],
            }
        
        return summary
    
    # ==================== HISTORICAL / REMOVED LISTINGS ====================
    
    def get_removed_listings(self, limit: int = 50) -> pd.DataFrame:
        """
        Get properties that have been removed from the market (likely sold or delisted).
        These are properties where is_active = 0.
        """
        query = """
            SELECT 
                p.id,
                p.geography,
                p.category,
                p.sq_meters,
                p.rooms,
                p.floor_number,
                ps.price,
                ps.price_per_sqm,
                ps.price_reduced,
                p.first_seen,
                p.last_seen,
                CAST(julianday(p.last_seen) - julianday(p.first_seen) AS INTEGER) as days_on_market,
                a.agency_name
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            LEFT JOIN agents a ON p.agent_id = a.id
            WHERE p.is_active = 0
            ORDER BY p.last_seen DESC
            LIMIT :limit
        """
        
        return pd.read_sql(query, self.session.bind, params={"limit": limit})
    
    def get_removed_listings_summary(self) -> Dict:
        """Get summary statistics of removed/sold listings."""
        query = """
            SELECT 
                COUNT(*) as total_removed,
                AVG(ps.price) as avg_price,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(p.sq_meters) as avg_size,
                AVG(CAST(julianday(p.last_seen) - julianday(p.first_seen) AS INTEGER)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as had_reduction_pct
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 0
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if df.empty or df.iloc[0]["total_removed"] == 0:
            return {}
        
        row = df.iloc[0]
        return {
            "total_removed": int(row["total_removed"]),
            "avg_price": row["avg_price"],
            "avg_price_sqm": row["avg_price_sqm"],
            "avg_size": row["avg_size"],
            "avg_days_to_sell": row["avg_dom"],
            "had_price_reduction_pct": row["had_reduction_pct"],
        }
    
    def get_removed_by_area(self, min_removed: int = 2) -> pd.DataFrame:
        """Analyze removed listings by area - shows which areas have highest turnover."""
        query = """
            SELECT 
                p.geography,
                COUNT(*) as removed_count,
                AVG(ps.price) as avg_sold_price,
                AVG(ps.price_per_sqm) as avg_sold_price_sqm,
                AVG(CAST(julianday(p.last_seen) - julianday(p.first_seen) AS INTEGER)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as reduction_rate
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 0 AND p.geography IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(*) >= :min_removed
            ORDER BY removed_count DESC
        """
        
        return pd.read_sql(query, self.session.bind, params={"min_removed": min_removed})
    
    def get_removed_by_price_range(self) -> pd.DataFrame:
        """Analyze which price ranges sell the most."""
        query = """
            SELECT 
                CASE 
                    WHEN ps.price < 100000 THEN 'Budget (<€100K)'
                    WHEN ps.price < 200000 THEN 'Entry (€100-200K)'
                    WHEN ps.price < 350000 THEN 'Mid-Range (€200-350K)'
                    WHEN ps.price < 500000 THEN 'Upper (€350-500K)'
                    WHEN ps.price < 750000 THEN 'Premium (€500-750K)'
                    ELSE 'Luxury (€750K+)'
                END as price_range,
                COUNT(*) as sold_count,
                AVG(CAST(julianday(p.last_seen) - julianday(p.first_seen) AS INTEGER)) as avg_dom,
                AVG(p.sq_meters) as avg_size
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 0 AND ps.price > 0
            GROUP BY price_range
            ORDER BY 
                CASE price_range
                    WHEN 'Budget (<€100K)' THEN 1
                    WHEN 'Entry (€100-200K)' THEN 2
                    WHEN 'Mid-Range (€200-350K)' THEN 3
                    WHEN 'Upper (€350-500K)' THEN 4
                    WHEN 'Premium (€500-750K)' THEN 5
                    ELSE 6
                END
        """
        
        return pd.read_sql(query, self.session.bind)
    
    def get_removed_by_size(self) -> pd.DataFrame:
        """Analyze which sizes sell the most."""
        query = """
            SELECT 
                CASE 
                    WHEN p.sq_meters < 50 THEN 'Studio/Small (<50 sqm)'
                    WHEN p.sq_meters < 80 THEN '1-2 BR (50-80 sqm)'
                    WHEN p.sq_meters < 120 THEN '2-3 BR (80-120 sqm)'
                    WHEN p.sq_meters < 180 THEN 'Large (120-180 sqm)'
                    ELSE 'Very Large (180+ sqm)'
                END as size_range,
                COUNT(*) as sold_count,
                AVG(CAST(julianday(p.last_seen) - julianday(p.first_seen) AS INTEGER)) as avg_dom,
                AVG(ps.price) as avg_price,
                AVG(ps.price_per_sqm) as avg_price_sqm
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 0 AND p.sq_meters > 0
            GROUP BY size_range
            ORDER BY 
                CASE size_range
                    WHEN 'Studio/Small (<50 sqm)' THEN 1
                    WHEN '1-2 BR (50-80 sqm)' THEN 2
                    WHEN '2-3 BR (80-120 sqm)' THEN 3
                    WHEN 'Large (120-180 sqm)' THEN 4
                    ELSE 5
                END
        """
        
        return pd.read_sql(query, self.session.bind)
    
    def get_sold_vs_active_comparison(self) -> pd.DataFrame:
        """Compare attributes of sold (removed) properties vs still active ones."""
        query = """
            SELECT 
                CASE WHEN p.is_active = 1 THEN 'Active' ELSE 'Sold/Removed' END as status,
                COUNT(*) as count,
                AVG(ps.price) as avg_price,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(p.sq_meters) as avg_size,
                AVG(p.rooms) as avg_rooms,
                AVG(p.floor_number) as avg_floor,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as reduction_rate
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            GROUP BY p.is_active
        """
        
        return pd.read_sql(query, self.session.bind)
    
    def get_removal_timeline(self) -> pd.DataFrame:
        """Get timeline of when properties were removed (sold)."""
        query = """
            SELECT 
                DATE(p.last_seen) as removal_date,
                COUNT(*) as removed_count,
                AVG(ps.price) as avg_price,
                AVG(CAST(julianday(p.last_seen) - julianday(p.first_seen) AS INTEGER)) as avg_dom
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 0 AND p.last_seen IS NOT NULL
            GROUP BY DATE(p.last_seen)
            ORDER BY removal_date DESC
            LIMIT 30
        """
        
        return pd.read_sql(query, self.session.bind)
    
    def get_what_actually_sold(self) -> Dict:
        """
        Comprehensive analysis of what actually sold - the true demand profile.
        Returns insights on sold property attributes.
        """
        sold_summary = self.get_removed_listings_summary()
        
        if not sold_summary:
            return {"error": "No sold/removed listings data available"}
        
        result = {"summary": sold_summary}
        
        # Best selling areas
        by_area = self.get_removed_by_area(min_removed=1)
        if not by_area.empty:
            result["top_selling_areas"] = by_area.head(5).to_dict("records")
        
        # Best selling price ranges
        by_price = self.get_removed_by_price_range()
        if not by_price.empty:
            best_price = by_price.loc[by_price["sold_count"].idxmax()]
            result["best_selling_price_range"] = {
                "range": best_price["price_range"],
                "sold_count": int(best_price["sold_count"]),
                "avg_dom": best_price["avg_dom"],
            }
        
        # Best selling sizes
        by_size = self.get_removed_by_size()
        if not by_size.empty:
            best_size = by_size.loc[by_size["sold_count"].idxmax()]
            result["best_selling_size"] = {
                "range": best_size["size_range"],
                "sold_count": int(best_size["sold_count"]),
                "avg_dom": best_size["avg_dom"],
            }
        
        return result
