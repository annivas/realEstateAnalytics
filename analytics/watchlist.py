"""
Watchlist management module.
Track specific properties and get alerts on price changes.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import (
    get_session, Property, PropertySnapshot, WatchlistItem,
    get_latest_snapshot_subquery
)
from sqlalchemy import func


class WatchlistAnalyzer:
    """Manage property watchlist and track price changes."""

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

    def add_to_watchlist(
        self,
        property_id: int,
        notes: str = None,
        target_price: int = None
    ) -> bool:
        """
        Add a property to the watchlist.

        Args:
            property_id: The property ID to watch
            notes: Optional notes about the property
            target_price: Optional target price for alerts

        Returns:
            True if added successfully, False if already exists
        """
        # Check if already in watchlist
        existing = (
            self.session.query(WatchlistItem)
            .filter(WatchlistItem.property_id == property_id)
            .first()
        )

        if existing:
            return False

        # Check if property exists
        property_exists = (
            self.session.query(Property)
            .filter(Property.id == property_id)
            .first()
        )

        if not property_exists:
            return False

        # Add to watchlist
        item = WatchlistItem(
            property_id=property_id,
            notes=notes,
            target_price=target_price
        )
        self.session.add(item)
        self.session.commit()

        return True

    def remove_from_watchlist(self, property_id: int) -> bool:
        """
        Remove a property from the watchlist.

        Returns:
            True if removed, False if not found
        """
        item = (
            self.session.query(WatchlistItem)
            .filter(WatchlistItem.property_id == property_id)
            .first()
        )

        if not item:
            return False

        self.session.delete(item)
        self.session.commit()
        return True

    def update_watchlist_item(
        self,
        property_id: int,
        notes: str = None,
        target_price: int = None
    ) -> bool:
        """Update notes or target price for a watchlist item."""
        item = (
            self.session.query(WatchlistItem)
            .filter(WatchlistItem.property_id == property_id)
            .first()
        )

        if not item:
            return False

        if notes is not None:
            item.notes = notes
        if target_price is not None:
            item.target_price = target_price

        self.session.commit()
        return True

    def get_watchlist(self) -> pd.DataFrame:
        """
        Get all properties in the watchlist with current prices and price history.

        Returns:
            DataFrame with watchlist properties and their details
        """
        # Get latest snapshot subquery
        latest_snapshot_subq = get_latest_snapshot_subquery(self.session)

        query = (
            self.session.query(
                WatchlistItem.id.label("watchlist_id"),
                WatchlistItem.property_id,
                WatchlistItem.notes,
                WatchlistItem.target_price,
                WatchlistItem.added_at,
                Property.geography,
                Property.category,
                Property.sq_meters,
                Property.rooms,
                Property.first_seen,
                Property.is_active,
                PropertySnapshot.price,
                PropertySnapshot.price_per_sqm,
                PropertySnapshot.price_reduced,
            )
            .join(Property, WatchlistItem.property_id == Property.id)
            .join(PropertySnapshot, Property.id == PropertySnapshot.property_id)
            .join(
                latest_snapshot_subq,
                (PropertySnapshot.property_id == latest_snapshot_subq.c.property_id) &
                (PropertySnapshot.collected_at == latest_snapshot_subq.c.max_date)
            )
        )

        results = query.all()

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results, columns=[
            "watchlist_id", "property_id", "notes", "target_price", "added_at",
            "geography", "category", "sq_meters", "rooms", "first_seen",
            "is_active", "current_price", "price_per_sqm", "price_reduced"
        ])

        # Calculate days on market
        df["days_on_market"] = (datetime.utcnow() - df["first_seen"]).dt.days

        # Calculate distance to target
        df["distance_to_target"] = np.where(
            df["target_price"].notna(),
            df["current_price"] - df["target_price"],
            np.nan
        )

        df["target_reached"] = df["distance_to_target"] <= 0

        return df

    def get_property_price_history(self, property_id: int) -> pd.DataFrame:
        """
        Get price history for a specific property.

        Returns:
            DataFrame with date and price columns
        """
        query = (
            self.session.query(
                PropertySnapshot.collected_at,
                PropertySnapshot.price,
                PropertySnapshot.price_per_sqm,
                PropertySnapshot.price_reduced,
                PropertySnapshot.price_pre_reduction,
            )
            .filter(PropertySnapshot.property_id == property_id)
            .order_by(PropertySnapshot.collected_at.asc())
        )

        results = query.all()

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results, columns=[
            "date", "price", "price_per_sqm", "price_reduced", "price_pre_reduction"
        ])

        # Calculate price changes
        df["price_change"] = df["price"].diff()
        df["price_change_pct"] = (df["price_change"] / df["price"].shift(1) * 100).round(2)

        return df

    def get_watchlist_with_history(self) -> List[Dict]:
        """
        Get watchlist items with their price history for sparkline charts.

        Returns:
            List of dicts with property info and price history
        """
        watchlist = self.get_watchlist()

        if watchlist.empty:
            return []

        results = []
        for _, row in watchlist.iterrows():
            history = self.get_property_price_history(row["property_id"])

            item = row.to_dict()
            item["price_history"] = history["price"].tolist() if not history.empty else []
            item["price_dates"] = history["date"].tolist() if not history.empty else []

            # Calculate price change since added
            if not history.empty:
                history_since_added = history[history["date"] >= row["added_at"]]
                if len(history_since_added) >= 2:
                    first_price = history_since_added["price"].iloc[0]
                    last_price = history_since_added["price"].iloc[-1]
                    item["price_change_since_added"] = last_price - first_price
                    item["price_change_pct_since_added"] = (
                        (last_price - first_price) / first_price * 100
                    ) if first_price > 0 else 0
                else:
                    item["price_change_since_added"] = 0
                    item["price_change_pct_since_added"] = 0
            else:
                item["price_change_since_added"] = 0
                item["price_change_pct_since_added"] = 0

            results.append(item)

        return results

    def get_watchlist_alerts(self) -> List[Dict]:
        """
        Get alerts for watchlist items (price drops, target reached, etc.)

        Returns:
            List of alert dicts
        """
        watchlist = self.get_watchlist()

        if watchlist.empty:
            return []

        alerts = []

        for _, row in watchlist.iterrows():
            # Target price reached
            if row.get("target_reached"):
                alerts.append({
                    "type": "target_reached",
                    "property_id": row["property_id"],
                    "geography": row["geography"],
                    "message": f"Target price reached! Current: €{row['current_price']:,}, Target: €{row['target_price']:,}",
                    "priority": "high"
                })

            # Price reduction
            if row.get("price_reduced"):
                alerts.append({
                    "type": "price_reduced",
                    "property_id": row["property_id"],
                    "geography": row["geography"],
                    "message": f"Price reduced to €{row['current_price']:,}",
                    "priority": "medium"
                })

            # Property sold/inactive
            if not row.get("is_active"):
                alerts.append({
                    "type": "property_inactive",
                    "property_id": row["property_id"],
                    "geography": row["geography"],
                    "message": "Property is no longer active (possibly sold)",
                    "priority": "high"
                })

        return sorted(alerts, key=lambda x: x["priority"] == "high", reverse=True)

    def get_watchlist_summary(self) -> Dict:
        """Get summary statistics for the watchlist."""
        watchlist = self.get_watchlist()

        if watchlist.empty:
            return {
                "total_items": 0,
                "active_properties": 0,
                "targets_reached": 0,
                "price_reductions": 0,
                "total_value": 0,
            }

        return {
            "total_items": len(watchlist),
            "active_properties": watchlist["is_active"].sum(),
            "targets_reached": watchlist["target_reached"].sum() if "target_reached" in watchlist else 0,
            "price_reductions": watchlist["price_reduced"].sum(),
            "total_value": watchlist["current_price"].sum(),
            "avg_price": watchlist["current_price"].mean(),
            "avg_days_on_market": watchlist["days_on_market"].mean(),
        }

    def is_in_watchlist(self, property_id: int) -> bool:
        """Check if a property is in the watchlist."""
        return (
            self.session.query(WatchlistItem)
            .filter(WatchlistItem.property_id == property_id)
            .first()
        ) is not None
