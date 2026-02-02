"""
Price prediction module.
Uses historical data to forecast future price trends.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from scipy import stats

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import get_session, Property, PropertySnapshot


class PricePredictionAnalyzer:
    """Price forecasting and trend prediction."""

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

    def get_historical_prices(
        self,
        area_filter: Optional[str] = None,
        days: int = 180
    ) -> pd.DataFrame:
        """
        Get historical average prices per sqm by date.

        Returns:
            DataFrame with date and avg_price_per_sqm columns
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        query = """
            SELECT
                DATE(ps.collected_at) as date,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                COUNT(DISTINCT ps.property_id) as property_count
            FROM property_snapshots ps
            JOIN properties p ON ps.property_id = p.id
            WHERE ps.collected_at >= :cutoff
              AND ps.price_per_sqm IS NOT NULL
              AND ps.price_per_sqm > 0
        """

        if area_filter:
            query += " AND p.geography LIKE :area"
            params = {"cutoff": cutoff_date, "area": f"%{area_filter}%"}
        else:
            params = {"cutoff": cutoff_date}

        query += """
            GROUP BY DATE(ps.collected_at)
            ORDER BY date ASC
        """

        df = pd.read_sql(query, self.session.bind, params=params)

        if df.empty:
            return df

        df["date"] = pd.to_datetime(df["date"])
        return df

    def calculate_trend(self, prices: pd.Series) -> Dict:
        """
        Calculate trend statistics using linear regression.

        Returns:
            Dict with slope, intercept, r_squared, trend_direction
        """
        if len(prices) < 3:
            return {
                "slope": 0,
                "intercept": prices.mean() if len(prices) > 0 else 0,
                "r_squared": 0,
                "trend_direction": "insufficient_data"
            }

        x = np.arange(len(prices))
        y = prices.values

        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        # Determine trend direction
        if abs(slope) < 0.5:  # Threshold for "stable"
            direction = "stable"
        elif slope > 0:
            direction = "rising"
        else:
            direction = "falling"

        return {
            "slope": slope,
            "intercept": intercept,
            "r_squared": r_value ** 2,
            "p_value": p_value,
            "std_error": std_err,
            "trend_direction": direction,
            "daily_change": slope,
            "monthly_change": slope * 30,
        }

    def predict_prices(
        self,
        area_filter: Optional[str] = None,
        days_ahead: int = 30,
        history_days: int = 90
    ) -> Dict:
        """
        Predict future prices based on historical trends.

        Args:
            area_filter: Optional area to filter by
            days_ahead: Number of days to predict
            history_days: Days of history to use for prediction

        Returns:
            Dict with predictions and confidence intervals
        """
        # Get historical data
        history = self.get_historical_prices(area_filter=area_filter, days=history_days)

        if history.empty or len(history) < 7:
            return {
                "error": "Insufficient historical data for prediction",
                "data_points": len(history) if not history.empty else 0
            }

        prices = history["avg_price_sqm"]
        dates = history["date"]

        # Calculate trend
        trend = self.calculate_trend(prices)

        # Current price (most recent)
        current_price = prices.iloc[-1]
        current_date = dates.iloc[-1]

        # Generate predictions
        predictions = []
        for day in range(1, days_ahead + 1):
            predicted_date = current_date + timedelta(days=day)
            # Linear extrapolation
            predicted_price = current_price + (trend["slope"] * day)

            # Calculate confidence interval (widens with time)
            std_dev = prices.std()
            confidence_margin = std_dev * np.sqrt(day / len(prices)) * 1.96  # 95% CI

            predictions.append({
                "date": predicted_date,
                "predicted_price": predicted_price,
                "lower_bound": predicted_price - confidence_margin,
                "upper_bound": predicted_price + confidence_margin,
                "confidence": max(0, 1 - (day / (days_ahead * 2)))  # Decreasing confidence
            })

        predictions_df = pd.DataFrame(predictions)

        # Calculate summary statistics
        price_change_30d = trend["slope"] * 30
        price_change_pct = (price_change_30d / current_price * 100) if current_price > 0 else 0

        return {
            "area": area_filter or "All Areas",
            "current_price": current_price,
            "current_date": current_date,
            "trend": trend,
            "predictions": predictions_df,
            "summary": {
                "predicted_30d_change": price_change_30d,
                "predicted_30d_change_pct": price_change_pct,
                "predicted_price_30d": current_price + price_change_30d,
                "model_r_squared": trend["r_squared"],
                "data_points_used": len(history),
            }
        }

    def predict_area_prices(self, min_listings: int = 10) -> pd.DataFrame:
        """
        Predict prices for all areas with sufficient data.

        Returns:
            DataFrame with area predictions
        """
        # Get unique areas
        areas_query = """
            SELECT DISTINCT p.geography, COUNT(DISTINCT p.id) as listing_count
            FROM properties p
            WHERE p.geography IS NOT NULL
            GROUP BY p.geography
            HAVING COUNT(DISTINCT p.id) >= :min_listings
        """

        areas_df = pd.read_sql(areas_query, self.session.bind, params={"min_listings": min_listings})

        if areas_df.empty:
            return pd.DataFrame()

        results = []
        for _, row in areas_df.iterrows():
            area = row["geography"]
            prediction = self.predict_prices(area_filter=area, days_ahead=30, history_days=60)

            if "error" not in prediction:
                results.append({
                    "geography": area,
                    "current_price_sqm": prediction["current_price"],
                    "predicted_price_30d": prediction["summary"]["predicted_price_30d"],
                    "change_pct_30d": prediction["summary"]["predicted_30d_change_pct"],
                    "trend_direction": prediction["trend"]["trend_direction"],
                    "model_confidence": prediction["trend"]["r_squared"],
                    "listing_count": row["listing_count"],
                })

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        return df.sort_values("change_pct_30d", ascending=False)

    def get_seasonal_patterns(self, years: int = 1) -> pd.DataFrame:
        """
        Analyze seasonal patterns in the market.

        Returns:
            DataFrame with monthly averages
        """
        cutoff_date = datetime.utcnow() - timedelta(days=years * 365)

        query = """
            SELECT
                strftime('%m', ps.collected_at) as month,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                COUNT(DISTINCT ps.property_id) as property_count
            FROM property_snapshots ps
            WHERE ps.collected_at >= :cutoff
              AND ps.price_per_sqm IS NOT NULL
              AND ps.price_per_sqm > 0
            GROUP BY strftime('%m', ps.collected_at)
            ORDER BY month
        """

        df = pd.read_sql(query, self.session.bind, params={"cutoff": cutoff_date})

        if df.empty:
            return df

        # Add month names
        month_names = {
            "01": "January", "02": "February", "03": "March", "04": "April",
            "05": "May", "06": "June", "07": "July", "08": "August",
            "09": "September", "10": "October", "11": "November", "12": "December"
        }
        df["month_name"] = df["month"].map(month_names)

        # Calculate deviation from annual average
        annual_avg = df["avg_price_sqm"].mean()
        df["deviation_pct"] = ((df["avg_price_sqm"] - annual_avg) / annual_avg * 100).round(2)

        return df

    def get_market_momentum(self, days: int = 30) -> Dict:
        """
        Calculate market momentum indicators.

        Returns:
            Dict with momentum metrics
        """
        # Get recent vs older data
        recent_cutoff = datetime.utcnow() - timedelta(days=days)
        older_cutoff = datetime.utcnow() - timedelta(days=days * 2)

        query = """
            SELECT
                CASE
                    WHEN ps.collected_at >= :recent THEN 'recent'
                    ELSE 'older'
                END as period,
                AVG(ps.price_per_sqm) as avg_price_sqm,
                COUNT(DISTINCT ps.property_id) as property_count,
                SUM(CASE WHEN ps.price_reduced = 1 THEN 1 ELSE 0 END) as reduced_count
            FROM property_snapshots ps
            WHERE ps.collected_at >= :older
              AND ps.price_per_sqm IS NOT NULL
            GROUP BY period
        """

        df = pd.read_sql(query, self.session.bind, params={
            "recent": recent_cutoff,
            "older": older_cutoff
        })

        if df.empty or len(df) < 2:
            return {"error": "Insufficient data for momentum calculation"}

        recent = df[df["period"] == "recent"].iloc[0] if not df[df["period"] == "recent"].empty else None
        older = df[df["period"] == "older"].iloc[0] if not df[df["period"] == "older"].empty else None

        if recent is None or older is None:
            return {"error": "Missing data for momentum calculation"}

        # Calculate momentum
        price_momentum = (
            (recent["avg_price_sqm"] - older["avg_price_sqm"]) /
            older["avg_price_sqm"] * 100
        ) if older["avg_price_sqm"] > 0 else 0

        inventory_change = (
            (recent["property_count"] - older["property_count"]) /
            older["property_count"] * 100
        ) if older["property_count"] > 0 else 0

        recent_reduction_rate = (
            recent["reduced_count"] / recent["property_count"] * 100
        ) if recent["property_count"] > 0 else 0

        older_reduction_rate = (
            older["reduced_count"] / older["property_count"] * 100
        ) if older["property_count"] > 0 else 0

        # Determine momentum direction
        if price_momentum > 2:
            momentum_signal = "bullish"
            emoji = "🚀"
        elif price_momentum < -2:
            momentum_signal = "bearish"
            emoji = "📉"
        else:
            momentum_signal = "neutral"
            emoji = "➡️"

        return {
            "period_days": days,
            "price_momentum_pct": round(price_momentum, 2),
            "inventory_change_pct": round(inventory_change, 2),
            "recent_reduction_rate": round(recent_reduction_rate, 2),
            "older_reduction_rate": round(older_reduction_rate, 2),
            "reduction_rate_change": round(recent_reduction_rate - older_reduction_rate, 2),
            "momentum_signal": momentum_signal,
            "momentum_emoji": emoji,
            "current_avg_price_sqm": round(recent["avg_price_sqm"], 0),
        }

    def get_price_forecast_summary(self) -> Dict:
        """
        Get a high-level summary of price forecasts for the dashboard.
        """
        # Overall market prediction
        overall = self.predict_prices(days_ahead=30, history_days=60)

        # Momentum
        momentum = self.get_market_momentum(days=14)

        # Top appreciating areas
        area_predictions = self.predict_area_prices(min_listings=5)

        summary = {
            "overall_trend": overall.get("trend", {}).get("trend_direction", "unknown"),
            "predicted_30d_change_pct": overall.get("summary", {}).get("predicted_30d_change_pct", 0),
            "model_confidence": overall.get("summary", {}).get("model_r_squared", 0),
            "momentum": momentum.get("momentum_signal", "unknown"),
            "momentum_emoji": momentum.get("momentum_emoji", ""),
        }

        if not area_predictions.empty:
            top_rising = area_predictions.head(3)
            summary["top_rising_areas"] = top_rising[["geography", "change_pct_30d"]].to_dict("records")

            top_falling = area_predictions.tail(3)
            summary["top_falling_areas"] = top_falling[["geography", "change_pct_30d"]].to_dict("records")

        return summary
