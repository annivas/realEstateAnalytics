"""
Alert system module.
Configure and manage market alerts for price drops, new listings, etc.
"""
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import (
    get_session, Property, PropertySnapshot, Alert, AlertHistory,
    WatchlistItem, get_latest_snapshot_subquery
)
from sqlalchemy import func


class AlertManager:
    """Manage and check alerts for market conditions."""

    ALERT_TYPES = {
        "price_drop": "Price Drop Alert",
        "new_listing": "New Listing Alert",
        "market_change": "Market Condition Alert",
        "target_price": "Target Price Alert",
        "area_activity": "Area Activity Alert",
    }

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

    def create_alert(
        self,
        alert_type: str,
        criteria: Dict,
    ) -> Optional[int]:
        """
        Create a new alert.

        Args:
            alert_type: Type of alert (price_drop, new_listing, etc.)
            criteria: Dict with alert criteria (area, price_threshold, etc.)

        Returns:
            Alert ID if created, None if invalid
        """
        if alert_type not in self.ALERT_TYPES:
            return None

        alert = Alert(
            alert_type=alert_type,
            criteria=json.dumps(criteria),
            is_active=True,
        )

        self.session.add(alert)
        self.session.commit()

        return alert.id

    def deactivate_alert(self, alert_id: int) -> bool:
        """Deactivate an alert."""
        alert = self.session.query(Alert).filter(Alert.id == alert_id).first()

        if not alert:
            return False

        alert.is_active = False
        self.session.commit()
        return True

    def get_active_alerts(self) -> pd.DataFrame:
        """Get all active alerts."""
        alerts = (
            self.session.query(Alert)
            .filter(Alert.is_active == True)
            .all()
        )

        if not alerts:
            return pd.DataFrame()

        data = []
        for alert in alerts:
            criteria = json.loads(alert.criteria) if alert.criteria else {}
            data.append({
                "id": alert.id,
                "type": alert.alert_type,
                "type_name": self.ALERT_TYPES.get(alert.alert_type, alert.alert_type),
                "criteria": criteria,
                "created_at": alert.created_at,
                "last_triggered": alert.last_triggered_at,
            })

        return pd.DataFrame(data)

    def check_price_drop_alerts(self, days: int = 7) -> List[Dict]:
        """
        Check for price drops that match alert criteria.

        Returns:
            List of triggered alerts
        """
        # Get alerts of type price_drop
        alerts = (
            self.session.query(Alert)
            .filter(Alert.alert_type == "price_drop")
            .filter(Alert.is_active == True)
            .all()
        )

        if not alerts:
            return []

        triggered = []
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        for alert in alerts:
            criteria = json.loads(alert.criteria) if alert.criteria else {}
            min_reduction_pct = criteria.get("min_reduction_pct", 5)
            area_filter = criteria.get("area")
            max_price = criteria.get("max_price")

            # Query for properties with price reductions
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
                    ps.price,
                    ps.price_per_sqm,
                    ps.price_change_percentage
                FROM properties p
                JOIN property_snapshots ps ON p.id = ps.property_id
                JOIN latest_snapshots ls ON ps.property_id = ls.property_id AND ps.collected_at = ls.max_date
                WHERE p.is_active = 1
                  AND ps.price_reduced = 1
                  AND ps.collected_at >= :cutoff
            """

            params = {"cutoff": cutoff_date}

            if area_filter:
                query += " AND p.geography LIKE :area"
                params["area"] = f"%{area_filter}%"

            if max_price:
                query += " AND ps.price <= :max_price"
                params["max_price"] = max_price

            df = pd.read_sql(query, self.session.bind, params=params)

            if not df.empty:
                # Filter by reduction percentage
                if min_reduction_pct:
                    df = df[abs(df["price_change_percentage"]) >= min_reduction_pct]

                for _, row in df.iterrows():
                    triggered.append({
                        "alert_id": alert.id,
                        "alert_type": "price_drop",
                        "property_id": row["id"],
                        "geography": row["geography"],
                        "message": f"Price dropped {abs(row['price_change_percentage']):.1f}% to €{row['price']:,}",
                        "property_price": row["price"],
                        "reduction_pct": abs(row["price_change_percentage"]),
                    })

                # Update last triggered
                alert.last_triggered_at = datetime.utcnow()

        self.session.commit()
        return triggered

    def check_new_listing_alerts(self, hours: int = 24) -> List[Dict]:
        """
        Check for new listings that match alert criteria.

        Returns:
            List of triggered alerts
        """
        alerts = (
            self.session.query(Alert)
            .filter(Alert.alert_type == "new_listing")
            .filter(Alert.is_active == True)
            .all()
        )

        if not alerts:
            return []

        triggered = []
        cutoff_date = datetime.utcnow() - timedelta(hours=hours)

        for alert in alerts:
            criteria = json.loads(alert.criteria) if alert.criteria else {}
            area_filter = criteria.get("area")
            max_price = criteria.get("max_price")
            max_price_per_sqm = criteria.get("max_price_per_sqm")
            min_sqm = criteria.get("min_sqm")
            category = criteria.get("category")

            # Query for new listings
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
                    ps.price,
                    ps.price_per_sqm,
                    p.first_seen
                FROM properties p
                JOIN property_snapshots ps ON p.id = ps.property_id
                JOIN latest_snapshots ls ON ps.property_id = ls.property_id AND ps.collected_at = ls.max_date
                WHERE p.is_active = 1
                  AND p.first_seen >= :cutoff
            """

            params = {"cutoff": cutoff_date}

            if area_filter:
                query += " AND p.geography LIKE :area"
                params["area"] = f"%{area_filter}%"

            if max_price:
                query += " AND ps.price <= :max_price"
                params["max_price"] = max_price

            if max_price_per_sqm:
                query += " AND ps.price_per_sqm <= :max_sqm_price"
                params["max_sqm_price"] = max_price_per_sqm

            if min_sqm:
                query += " AND p.sq_meters >= :min_sqm"
                params["min_sqm"] = min_sqm

            if category:
                query += " AND p.category = :category"
                params["category"] = category

            df = pd.read_sql(query, self.session.bind, params=params)

            for _, row in df.iterrows():
                triggered.append({
                    "alert_id": alert.id,
                    "alert_type": "new_listing",
                    "property_id": row["id"],
                    "geography": row["geography"],
                    "message": f"New {row['category']} in {row['geography']}: €{row['price']:,} ({row['sq_meters']} sqm)",
                    "property_price": row["price"],
                    "sq_meters": row["sq_meters"],
                })

            if not df.empty:
                alert.last_triggered_at = datetime.utcnow()

        self.session.commit()
        return triggered

    def check_watchlist_alerts(self) -> List[Dict]:
        """
        Check for alerts on watchlist properties.

        Returns:
            List of triggered alerts
        """
        # Get watchlist items with target prices
        query = """
            WITH latest_snapshots AS (
                SELECT property_id, MAX(collected_at) as max_date
                FROM property_snapshots
                GROUP BY property_id
            )
            SELECT
                w.id as watchlist_id,
                w.property_id,
                w.target_price,
                w.notes,
                p.geography,
                p.is_active,
                ps.price as current_price,
                ps.price_reduced
            FROM watchlist w
            JOIN properties p ON w.property_id = p.id
            JOIN property_snapshots ps ON p.id = ps.property_id
            JOIN latest_snapshots ls ON ps.property_id = ls.property_id AND ps.collected_at = ls.max_date
        """

        df = pd.read_sql(query, self.session.bind)

        if df.empty:
            return []

        triggered = []

        for _, row in df.iterrows():
            # Target price reached
            if row["target_price"] and row["current_price"] <= row["target_price"]:
                triggered.append({
                    "alert_type": "target_price",
                    "property_id": row["property_id"],
                    "geography": row["geography"],
                    "message": f"Target price reached! Current: €{row['current_price']:,}, Target: €{row['target_price']:,}",
                    "priority": "high",
                })

            # Price reduced on watched property
            if row["price_reduced"]:
                triggered.append({
                    "alert_type": "watchlist_price_drop",
                    "property_id": row["property_id"],
                    "geography": row["geography"],
                    "message": f"Price reduced on watched property to €{row['current_price']:,}",
                    "priority": "medium",
                })

            # Property sold/removed
            if not row["is_active"]:
                triggered.append({
                    "alert_type": "watchlist_sold",
                    "property_id": row["property_id"],
                    "geography": row["geography"],
                    "message": "Watched property is no longer active (possibly sold)",
                    "priority": "high",
                })

        return triggered

    def check_all_alerts(self) -> Dict:
        """
        Check all active alerts and return triggered ones.

        Returns:
            Dict with all triggered alerts by type
        """
        return {
            "price_drops": self.check_price_drop_alerts(),
            "new_listings": self.check_new_listing_alerts(),
            "watchlist": self.check_watchlist_alerts(),
        }

    def get_alert_history(self, limit: int = 50) -> pd.DataFrame:
        """Get recent alert history."""
        history = (
            self.session.query(AlertHistory)
            .order_by(AlertHistory.triggered_at.desc())
            .limit(limit)
            .all()
        )

        if not history:
            return pd.DataFrame()

        data = []
        for h in history:
            data.append({
                "id": h.id,
                "alert_id": h.alert_id,
                "property_id": h.property_id,
                "message": h.message,
                "triggered_at": h.triggered_at,
            })

        return pd.DataFrame(data)

    def log_triggered_alert(
        self,
        alert_id: int,
        property_id: int,
        message: str
    ):
        """Log a triggered alert to history."""
        history = AlertHistory(
            alert_id=alert_id,
            property_id=property_id,
            message=message,
        )
        self.session.add(history)
        self.session.commit()

    def get_alert_summary(self) -> Dict:
        """Get summary of alert system status."""
        active_count = (
            self.session.query(Alert)
            .filter(Alert.is_active == True)
            .count()
        )

        # Count by type
        type_counts = (
            self.session.query(Alert.alert_type, func.count(Alert.id))
            .filter(Alert.is_active == True)
            .group_by(Alert.alert_type)
            .all()
        )

        type_summary = {t: c for t, c in type_counts}

        # Recent triggers
        recent_triggers = (
            self.session.query(AlertHistory)
            .filter(AlertHistory.triggered_at >= datetime.utcnow() - timedelta(days=7))
            .count()
        )

        return {
            "active_alerts": active_count,
            "alerts_by_type": type_summary,
            "triggers_last_7_days": recent_triggers,
        }


def create_default_alerts():
    """Create some default alerts for a new user."""
    with AlertManager() as manager:
        # Price drop alert for any significant reduction
        manager.create_alert(
            alert_type="price_drop",
            criteria={"min_reduction_pct": 10}
        )

        # New listing alert for Athens
        manager.create_alert(
            alert_type="new_listing",
            criteria={"area": "Athens", "max_price_per_sqm": 3000}
        )
