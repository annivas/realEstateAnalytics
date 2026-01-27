"""
Investor-focused analytics tools for gaining market edge.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from database.models import get_session, Property, PropertySnapshot, Agent


class InvestorAnalyzer:
    """Tools for real estate investors to gain market edge."""
    
    def __init__(self):
        self.session = None
    
    def __enter__(self):
        self.session = get_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
    
    # ==================== FIRST MOVER ADVANTAGE ====================
    
    def get_new_listings(self, hours: int = 48, limit: int = 50) -> pd.DataFrame:
        """
        Get brand new listings - first mover advantage.
        Properties listed in the last X hours.
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
                p.first_seen,
                CAST((julianday('now') - julianday(p.first_seen)) * 24 AS INTEGER) as hours_listed,
                a.agency_name
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            LEFT JOIN agents a ON p.agent_id = a.id
            WHERE p.is_active = 1
              AND julianday('now') - julianday(p.first_seen) <= :days
            ORDER BY p.first_seen DESC
            LIMIT :limit
        """
        
        return pd.read_sql(query, self.session.bind, params={"days": hours/24, "limit": limit})
    
    def get_new_listings_by_area(self, hours: int = 48) -> pd.DataFrame:
        """Get count of new listings by area."""
        query = """
            SELECT 
                p.geography,
                COUNT(*) as new_listings,
                AVG(ps.price) as avg_price,
                AVG(ps.price_per_sqm) as avg_price_sqm
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1
              AND p.geography IS NOT NULL
              AND julianday('now') - julianday(p.first_seen) <= :days
            GROUP BY p.geography
            ORDER BY new_listings DESC
            LIMIT 20
        """
        
        return pd.read_sql(query, self.session.bind, params={"days": hours/24})
    
    # ==================== INVESTMENT CALCULATOR ====================
    
    def calculate_investment_metrics(
        self,
        purchase_price: float,
        monthly_rent: float,
        down_payment_pct: float = 20,
        interest_rate: float = 4.5,
        loan_term_years: int = 25,
        annual_expenses_pct: float = 25,  # % of rent for expenses
        appreciation_rate: float = 3,
    ) -> Dict:
        """
        Calculate investment metrics for a property.
        
        Returns:
            Dict with cap_rate, cash_on_cash, roi, monthly_cashflow, etc.
        """
        # Annual figures
        annual_rent = monthly_rent * 12
        annual_expenses = annual_rent * (annual_expenses_pct / 100)
        net_operating_income = annual_rent - annual_expenses
        
        # Financing
        down_payment = purchase_price * (down_payment_pct / 100)
        loan_amount = purchase_price - down_payment
        
        # Monthly mortgage payment (if loan)
        if loan_amount > 0 and interest_rate > 0:
            monthly_rate = (interest_rate / 100) / 12
            num_payments = loan_term_years * 12
            monthly_mortgage = loan_amount * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
            annual_mortgage = monthly_mortgage * 12
        else:
            monthly_mortgage = 0
            annual_mortgage = 0
        
        # Cash flow
        annual_cashflow = net_operating_income - annual_mortgage
        monthly_cashflow = annual_cashflow / 12
        
        # Metrics
        cap_rate = (net_operating_income / purchase_price) * 100 if purchase_price > 0 else 0
        cash_on_cash = (annual_cashflow / down_payment) * 100 if down_payment > 0 else 0
        
        # Total ROI (including appreciation)
        annual_appreciation = purchase_price * (appreciation_rate / 100)
        total_annual_return = annual_cashflow + annual_appreciation
        total_roi = (total_annual_return / down_payment) * 100 if down_payment > 0 else 0
        
        # Gross rent multiplier
        grm = purchase_price / annual_rent if annual_rent > 0 else 0
        
        return {
            "purchase_price": purchase_price,
            "down_payment": down_payment,
            "loan_amount": loan_amount,
            "monthly_rent": monthly_rent,
            "annual_rent": annual_rent,
            "annual_expenses": annual_expenses,
            "net_operating_income": net_operating_income,
            "monthly_mortgage": monthly_mortgage,
            "annual_mortgage": annual_mortgage,
            "monthly_cashflow": monthly_cashflow,
            "annual_cashflow": annual_cashflow,
            "cap_rate": cap_rate,
            "cash_on_cash_return": cash_on_cash,
            "total_roi": total_roi,
            "gross_rent_multiplier": grm,
            "break_even_occupancy": (annual_expenses + annual_mortgage) / annual_rent * 100 if annual_rent > 0 else 0,
        }
    
    def estimate_rental_income(self, price_per_sqm: float, sq_meters: int, area: str = None) -> Dict:
        """
        Estimate potential rental income based on market data.
        Uses typical yield rates for Greek market.
        """
        # Typical rental yields in Greece (rough estimates)
        # Athens: 3-5% gross yield
        # Thessaloniki: 4-6%
        # Islands: 5-8% (seasonal)
        
        property_value = price_per_sqm * sq_meters
        
        # Conservative estimate: 4% gross yield
        low_yield = 0.03
        mid_yield = 0.04
        high_yield = 0.05
        
        return {
            "estimated_value": property_value,
            "monthly_rent_low": (property_value * low_yield) / 12,
            "monthly_rent_mid": (property_value * mid_yield) / 12,
            "monthly_rent_high": (property_value * high_yield) / 12,
            "annual_rent_low": property_value * low_yield,
            "annual_rent_mid": property_value * mid_yield,
            "annual_rent_high": property_value * high_yield,
            "yield_assumption_low": low_yield * 100,
            "yield_assumption_mid": mid_yield * 100,
            "yield_assumption_high": high_yield * 100,
        }
    
    # ==================== APPRECIATION RADAR ====================
    
    def get_appreciation_leaders(self, min_listings: int = 5) -> pd.DataFrame:
        """
        Find areas with highest price appreciation potential.
        Based on: new listing activity, price trends, demand indicators.
        """
        query = """
            SELECT 
                p.geography,
                COUNT(*) as total_listings,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                SUM(CASE WHEN julianday('now') - julianday(p.first_seen) <= 30 THEN 1 ELSE 0 END) as new_listings_30d,
                SUM(CASE WHEN julianday('now') - julianday(p.first_seen) <= 7 THEN 1 ELSE 0 END) as new_listings_7d,
                AVG(julianday('now') - julianday(p.first_seen)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) as reduced_count
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 
              AND p.geography IS NOT NULL
              AND ps.price_per_sqm IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(*) >= :min_listings
        """
        
        df = pd.read_sql(query, self.session.bind, params={"min_listings": min_listings})
        
        if df.empty:
            return df
        
        # Calculate appreciation indicators
        # High activity + low DOM + low reduction rate = hot market
        
        # Activity score (more new listings = higher demand)
        max_activity = df["new_listings_30d"].max()
        if max_activity > 0:
            df["activity_score"] = (df["new_listings_30d"] / max_activity) * 10
        else:
            df["activity_score"] = 5
        
        # Velocity score (lower DOM = faster sales = higher demand)
        df["velocity_score"] = 10 - (df["avg_dom"].clip(0, 90) / 9)
        
        # Health score (lower reduction rate = healthy prices)
        df["reduction_rate"] = df["reduced_count"] / df["total_listings"]
        df["health_score"] = 10 - (df["reduction_rate"] * 10).clip(0, 10)
        
        # Overall appreciation potential score
        df["appreciation_score"] = (
            df["activity_score"] * 0.4 +
            df["velocity_score"] * 0.35 +
            df["health_score"] * 0.25
        ).round(1)
        
        # Trend indicator
        df["trend"] = df["appreciation_score"].apply(
            lambda x: "🔥 Hot" if x >= 7 else ("📈 Rising" if x >= 5 else ("➡️ Stable" if x >= 3 else "📉 Cooling"))
        )
        
        return df.sort_values("appreciation_score", ascending=False)
    
    # ==================== DISTRESSED PROPERTY FINDER ====================
    
    def get_distressed_properties(self, limit: int = 50) -> pd.DataFrame:
        """
        Find distressed properties - best negotiation opportunities.
        Criteria: price reduced + long DOM + below area average.
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
                ps.price_change_percentage,
                CAST(julianday('now') - julianday(p.first_seen) AS INTEGER) as days_on_market,
                aa.area_avg,
                CASE WHEN aa.area_avg > 0 THEN ((aa.area_avg - ps.price_per_sqm) / aa.area_avg * 100) ELSE 0 END as below_avg_pct,
                a.agency_name
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            LEFT JOIN area_avgs aa ON p.geography = aa.geography
            LEFT JOIN agents a ON p.agent_id = a.id
            WHERE p.is_active = 1
        """
        
        df = pd.read_sql(query, self.session.bind)
        
        if df.empty:
            return df
        
        # Calculate distress score
        # High DOM score
        df["dom_score"] = (df["days_on_market"].clip(0, 90) / 9).clip(0, 10)
        
        # Price reduction score
        df["reduction_score"] = df["price_reduced"].apply(lambda x: 10 if x else 0)
        
        # Below average score
        df["below_avg_score"] = df["below_avg_pct"].clip(0, 30) / 3
        
        # Total distress score
        df["distress_score"] = (
            df["dom_score"] * 0.35 +
            df["reduction_score"] * 0.40 +
            df["below_avg_score"] * 0.25
        ).round(1)
        
        df["distress_level"] = pd.cut(
            df["distress_score"],
            bins=[0, 3, 5, 7, 10],
            labels=["Low", "Medium", "High", "Very High"]
        )
        
        return df.sort_values("distress_score", ascending=False).head(limit)
    
    # ==================== MARKET TIMING SIGNALS ====================
    
    def get_market_timing_signals(self) -> Dict:
        """
        Calculate market timing indicators.
        Determines if it's a buyer's or seller's market.
        """
        # Get current market stats
        stats_query = """
            SELECT 
                COUNT(*) as total_listings,
                AVG(julianday('now') - julianday(p.first_seen)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) as reduced_count,
                SUM(CASE WHEN julianday('now') - julianday(p.first_seen) <= 7 THEN 1 ELSE 0 END) as new_7d,
                SUM(CASE WHEN julianday('now') - julianday(p.first_seen) <= 30 THEN 1 ELSE 0 END) as new_30d,
                AVG(ps.price_per_sqm) as avg_price_sqm
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1
        """
        
        df = pd.read_sql(stats_query, self.session.bind)
        
        if df.empty or df.iloc[0]["total_listings"] == 0:
            return {"market_type": "Unknown", "confidence": 0}
        
        stats = df.iloc[0]
        
        total = stats["total_listings"]
        avg_dom = stats["avg_dom"] or 30
        reduction_rate = (stats["reduced_count"] / total * 100) if total > 0 else 0
        weekly_new = stats["new_7d"] or 0
        monthly_new = stats["new_30d"] or 0
        
        # Calculate market signals
        signals = {
            "total_inventory": int(total),
            "avg_days_on_market": round(avg_dom, 1),
            "price_reduction_rate": round(reduction_rate, 1),
            "new_listings_7d": int(weekly_new),
            "new_listings_30d": int(monthly_new),
            "avg_price_sqm": round(stats["avg_price_sqm"], 0) if stats["avg_price_sqm"] else 0,
        }
        
        # Determine market type
        # Buyer's market indicators: high DOM, high reduction rate, high inventory
        # Seller's market indicators: low DOM, low reduction rate, low inventory
        
        buyer_signals = 0
        seller_signals = 0
        
        # DOM analysis (< 30 days = seller's, > 60 days = buyer's)
        if avg_dom < 30:
            seller_signals += 2
        elif avg_dom > 60:
            buyer_signals += 2
        else:
            buyer_signals += 1
            seller_signals += 1
        
        # Reduction rate (< 10% = seller's, > 25% = buyer's)
        if reduction_rate < 10:
            seller_signals += 2
        elif reduction_rate > 25:
            buyer_signals += 2
        else:
            buyer_signals += 1
            seller_signals += 1
        
        # New listings velocity
        weekly_rate = (weekly_new / total * 100) if total > 0 else 0
        if weekly_rate > 5:  # High new listing rate = more supply
            buyer_signals += 1
        elif weekly_rate < 2:  # Low new listing rate = tight supply
            seller_signals += 1
        
        # Determine overall market type
        total_signals = buyer_signals + seller_signals
        if total_signals > 0:
            buyer_pct = buyer_signals / total_signals * 100
            seller_pct = seller_signals / total_signals * 100
        else:
            buyer_pct = seller_pct = 50
        
        if buyer_signals > seller_signals + 1:
            market_type = "Buyer's Market"
            recommendation = "Good time to negotiate. Sellers are motivated."
            emoji = "🟢"
        elif seller_signals > buyer_signals + 1:
            market_type = "Seller's Market"
            recommendation = "Act fast on good deals. Competition is high."
            emoji = "🔴"
        else:
            market_type = "Balanced Market"
            recommendation = "Normal conditions. Focus on value."
            emoji = "🟡"
        
        signals.update({
            "market_type": market_type,
            "market_emoji": emoji,
            "buyer_signal_strength": round(buyer_pct, 0),
            "seller_signal_strength": round(seller_pct, 0),
            "recommendation": recommendation,
        })
        
        return signals
    
    def get_market_health_by_area(self, min_listings: int = 3) -> pd.DataFrame:
        """Get market health indicators by area."""
        query = """
            SELECT 
                p.geography,
                COUNT(*) as listings,
                AVG(julianday('now') - julianday(p.first_seen)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as reduction_rate,
                SUM(CASE WHEN julianday('now') - julianday(p.first_seen) <= 7 THEN 1 ELSE 0 END) as new_7d
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1 AND p.geography IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(*) >= :min_listings
        """
        
        df = pd.read_sql(query, self.session.bind, params={"min_listings": min_listings})
        
        if df.empty:
            return df
        
        # Determine market type per area
        def get_area_market_type(row):
            if row["avg_dom"] < 30 and row["reduction_rate"] < 15:
                return "🔴 Seller's"
            elif row["avg_dom"] > 60 or row["reduction_rate"] > 30:
                return "🟢 Buyer's"
            else:
                return "🟡 Balanced"
        
        df["market_type"] = df.apply(get_area_market_type, axis=1)
        
        return df.sort_values("avg_dom")
    
    # ==================== COMPARABLE ANALYSIS ====================
    
    def get_comparables(
        self, 
        geography: str, 
        sq_meters: int, 
        rooms: int = None,
        tolerance_sqm: int = 20,
        limit: int = 10
    ) -> pd.DataFrame:
        """
        Find comparable properties for valuation.
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
                CAST(julianday('now') - julianday(p.first_seen) AS INTEGER) as days_on_market,
                ABS(p.sq_meters - :target_sqm) as size_diff
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            WHERE p.is_active = 1
              AND p.geography = :geography
              AND p.sq_meters BETWEEN :min_sqm AND :max_sqm
            ORDER BY size_diff ASC
            LIMIT :limit
        """
        
        params = {
            "geography": geography,
            "target_sqm": sq_meters,
            "min_sqm": sq_meters - tolerance_sqm,
            "max_sqm": sq_meters + tolerance_sqm,
            "limit": limit,
        }
        
        df = pd.read_sql(query, self.session.bind, params=params)
        
        if not df.empty:
            # Calculate suggested value range
            df["suggested_value"] = df["price_per_sqm"] * sq_meters
        
        return df
