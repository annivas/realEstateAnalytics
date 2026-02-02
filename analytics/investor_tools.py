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
        self.session = get_session()

    def close(self):
        """Close the database session."""
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    # ==================== FIRST MOVER ADVANTAGE ====================
    
    def get_new_listings(self, hours: int = 48, limit: int = 50) -> pd.DataFrame:
        """
        Get brand new listings - first mover advantage.
        Properties listed in the last X hours.
        """
        # Use latest snapshot to avoid duplicates
        query = """
            WITH latest_snapshots AS (
                SELECT property_id, MAX(collected_at) as max_date
                FROM property_snapshots
                GROUP BY property_id
            )
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
            JOIN latest_snapshots ls ON ps.property_id = ls.property_id AND ps.collected_at = ls.max_date
            LEFT JOIN agents a ON p.agent_id = a.id
            WHERE p.is_active = 1
              AND julianday('now') - julianday(p.first_seen) <= :days
            ORDER BY p.first_seen DESC
            LIMIT :limit
        """

        return pd.read_sql(query, self.session.bind, params={"days": hours/24, "limit": limit})
    
    def get_new_listings_by_area(self, hours: int = 48) -> pd.DataFrame:
        """Get count of new listings by area."""
        # Use latest snapshot to avoid duplicates
        query = """
            WITH latest_snapshots AS (
                SELECT property_id, MAX(collected_at) as max_date
                FROM property_snapshots
                GROUP BY property_id
            )
            SELECT
                p.geography,
                COUNT(DISTINCT p.id) as new_listings,
                AVG(ps.price) as avg_price,
                AVG(ps.price_per_sqm) as avg_price_sqm
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            JOIN latest_snapshots ls ON ps.property_id = ls.property_id AND ps.collected_at = ls.max_date
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

    def get_rental_yield_analysis(self, min_listings: int = 5) -> pd.DataFrame:
        """
        Analyze estimated rental yields by area based on market data.

        Uses price-to-rent ratios and market indicators to estimate yields.

        Returns:
            DataFrame with area yield estimates and investment metrics
        """
        # Get area statistics for yield estimation
        query = """
            WITH latest_snapshots AS (
                SELECT property_id, MAX(collected_at) as max_date
                FROM property_snapshots
                GROUP BY property_id
            )
            SELECT
                p.geography,
                COUNT(DISTINCT p.id) as listing_count,
                AVG(ps.price) as avg_price,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                AVG(p.sq_meters) as avg_size,
                AVG(julianday('now') - julianday(p.first_seen)) as avg_dom,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) as reduced_count
            FROM properties p
            JOIN property_snapshots ps ON p.id = ps.property_id
            JOIN latest_snapshots ls ON ps.property_id = ls.property_id AND ps.collected_at = ls.max_date
            WHERE p.is_active = 1
              AND p.geography IS NOT NULL
              AND ps.price_per_sqm IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(DISTINCT p.id) >= :min_listings
        """

        df = pd.read_sql(query, self.session.bind, params={"min_listings": min_listings})

        if df.empty:
            return df

        # Calculate estimated yields based on market factors
        # Higher yield estimates for:
        # - Areas with higher DOM (more supply, landlord-friendly)
        # - Areas with more price reductions (negotiable)
        # - Lower price per sqm areas (better value)

        # Base yield assumptions for Athens region
        base_yield = 0.04  # 4% base gross yield

        # Price factor: cheaper areas have higher yields
        price_max = df["avg_price_sqm"].max()
        price_min = df["avg_price_sqm"].min()
        if price_max > price_min:
            df["price_factor"] = 1 + ((price_max - df["avg_price_sqm"]) / (price_max - price_min) * 0.02)
        else:
            df["price_factor"] = 1.0

        # Market factor: areas with higher DOM suggest rental-friendly
        dom_avg = df["avg_dom"].mean()
        df["market_factor"] = 1 + ((df["avg_dom"] - dom_avg) / 100).clip(-0.01, 0.01)

        # Calculate estimated gross yield
        df["estimated_gross_yield"] = (base_yield * df["price_factor"] * df["market_factor"] * 100).round(2)
        df["estimated_gross_yield"] = df["estimated_gross_yield"].clip(2.5, 7.0)

        # Calculate estimated monthly rent
        df["estimated_monthly_rent"] = (
            df["avg_price"] * (df["estimated_gross_yield"] / 100) / 12
        ).round(0)

        # Calculate rent per sqm
        df["estimated_rent_per_sqm"] = (
            df["estimated_monthly_rent"] / df["avg_size"]
        ).round(1)

        # Net yield (assuming 25% expenses)
        df["estimated_net_yield"] = (df["estimated_gross_yield"] * 0.75).round(2)

        # GRM (Gross Rent Multiplier)
        df["grm_years"] = (df["avg_price"] / (df["estimated_monthly_rent"] * 12)).round(1)

        # Investment rating based on yield
        df["investment_rating"] = pd.cut(
            df["estimated_net_yield"],
            bins=[0, 2.5, 3.5, 4.5, 10],
            labels=["Low Yield", "Moderate", "Good", "Excellent"]
        )

        return df.sort_values("estimated_gross_yield", ascending=False)

    def calculate_rental_property_roi(
        self,
        property_id: int = None,
        price: float = None,
        sq_meters: float = None,
        area: str = None,
        monthly_rent: float = None,
    ) -> Dict:
        """
        Calculate comprehensive ROI for a rental property.

        Can use either a property ID to look up details, or manual inputs.

        Returns:
            Dict with comprehensive investment analysis
        """
        # If property_id provided, look up details
        if property_id:
            query = """
                WITH latest_snapshots AS (
                    SELECT property_id, MAX(collected_at) as max_date
                    FROM property_snapshots
                    GROUP BY property_id
                )
                SELECT
                    p.id, p.geography, p.sq_meters, ps.price, ps.price_per_sqm
                FROM properties p
                JOIN property_snapshots ps ON p.id = ps.property_id
                JOIN latest_snapshots ls ON ps.property_id = ls.property_id AND ps.collected_at = ls.max_date
                WHERE p.id = :property_id
            """
            result = pd.read_sql(query, self.session.bind, params={"property_id": property_id})

            if result.empty:
                return {"error": "Property not found"}

            prop = result.iloc[0]
            price = prop["price"]
            sq_meters = prop["sq_meters"]
            area = prop["geography"]

        if not all([price, sq_meters]):
            return {"error": "Missing required inputs (price, sq_meters)"}

        # Estimate rent if not provided
        if not monthly_rent:
            # Use area analysis to estimate yield
            yield_analysis = self.get_rental_yield_analysis(min_listings=3)

            if not yield_analysis.empty and area:
                area_data = yield_analysis[yield_analysis["geography"].str.contains(area, case=False, na=False)]
                if not area_data.empty:
                    estimated_yield = area_data.iloc[0]["estimated_gross_yield"] / 100
                else:
                    estimated_yield = 0.04  # Default 4%
            else:
                estimated_yield = 0.04

            monthly_rent = (price * estimated_yield) / 12
        else:
            estimated_yield = (monthly_rent * 12) / price

        # Calculate all metrics
        annual_rent = monthly_rent * 12
        gross_yield = (annual_rent / price) * 100

        # Expense assumptions
        vacancy_rate = 0.05  # 5% vacancy
        management_fee = 0.08  # 8% property management
        maintenance = 0.01  # 1% of value for maintenance
        insurance = 0.002  # 0.2% of value
        property_tax = 0.01  # 1% ENFIA

        annual_expenses = (
            annual_rent * vacancy_rate +
            annual_rent * management_fee +
            price * maintenance +
            price * insurance +
            price * property_tax
        )

        noi = annual_rent - annual_expenses
        net_yield = (noi / price) * 100

        # Financing scenarios
        scenarios = {}
        for dp_pct in [20, 30, 50, 100]:
            dp = price * (dp_pct / 100)
            loan = price - dp

            if loan > 0:
                rate = 0.045  # 4.5% interest
                term = 25 * 12
                monthly_rate = rate / 12
                mortgage = loan * (monthly_rate * (1 + monthly_rate)**term) / ((1 + monthly_rate)**term - 1)
                annual_mortgage = mortgage * 12
            else:
                mortgage = 0
                annual_mortgage = 0

            annual_cashflow = noi - annual_mortgage
            coc = (annual_cashflow / dp) * 100 if dp > 0 else 0

            scenarios[f"{dp_pct}pct_down"] = {
                "down_payment": dp,
                "loan_amount": loan,
                "monthly_mortgage": mortgage,
                "annual_cashflow": annual_cashflow,
                "monthly_cashflow": annual_cashflow / 12,
                "cash_on_cash": coc,
            }

        return {
            "property_id": property_id,
            "area": area,
            "price": price,
            "sq_meters": sq_meters,
            "price_per_sqm": price / sq_meters if sq_meters else 0,
            "estimated_monthly_rent": monthly_rent,
            "annual_rent": annual_rent,
            "gross_yield": gross_yield,
            "annual_expenses": annual_expenses,
            "noi": noi,
            "net_yield": net_yield,
            "cap_rate": net_yield,  # Cap rate = net yield for all-cash
            "grm": price / annual_rent if annual_rent > 0 else 0,
            "financing_scenarios": scenarios,
            "expense_breakdown": {
                "vacancy": annual_rent * vacancy_rate,
                "management": annual_rent * management_fee,
                "maintenance": price * maintenance,
                "insurance": price * insurance,
                "property_tax": price * property_tax,
            }
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
