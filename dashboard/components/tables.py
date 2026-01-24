"""
Table components for the dashboard.
"""
import pandas as pd
import streamlit as st


def render_deals_table(df: pd.DataFrame, show_image: bool = True):
    """
    Render a table of deal opportunities.
    
    Args:
        df: DataFrame with deal data
        show_image: Whether to show property images
    """
    if df.empty:
        st.info("No deals found matching your criteria.")
        return
    
    # Format columns for display
    display_df = df.copy()
    
    # Format price columns
    if "current_price" in display_df.columns:
        display_df["current_price"] = display_df["current_price"].apply(lambda x: f"EUR {x:,.0f}")
    if "price" in display_df.columns:
        display_df["price"] = display_df["price"].apply(lambda x: f"EUR {x:,.0f}")
    if "original_price" in display_df.columns:
        display_df["original_price"] = display_df["original_price"].apply(lambda x: f"EUR {x:,.0f}" if pd.notna(x) else "N/A")
    if "savings" in display_df.columns:
        display_df["savings"] = display_df["savings"].apply(lambda x: f"EUR {x:,.0f}" if pd.notna(x) else "N/A")
    if "price_per_sqm" in display_df.columns:
        display_df["price_per_sqm"] = display_df["price_per_sqm"].apply(lambda x: f"EUR {x:,.0f}/sqm")
    
    # Format percentage columns
    if "reduction_pct" in display_df.columns:
        display_df["reduction_pct"] = display_df["reduction_pct"].apply(lambda x: f"{x:.1f}%")
    if "vs_market_median" in display_df.columns:
        display_df["vs_market_median"] = display_df["vs_market_median"].apply(lambda x: f"{x:+.1f}%")
    
    # Select columns to display
    display_columns = [
        col for col in [
            "id", "category", "geography", "sq_meters", "rooms",
            "current_price", "price", "original_price", "reduction_pct",
            "price_per_sqm", "savings", "vs_market_median", "days_on_market"
        ]
        if col in display_df.columns
    ]
    
    # Rename columns for display
    column_names = {
        "id": "ID",
        "category": "Type",
        "geography": "Area",
        "sq_meters": "Size (sqm)",
        "rooms": "Rooms",
        "current_price": "Current Price",
        "price": "Price",
        "original_price": "Original Price",
        "reduction_pct": "Reduction",
        "price_per_sqm": "Price/sqm",
        "savings": "Savings",
        "vs_market_median": "vs Market",
        "days_on_market": "Days Listed",
    }
    
    display_df = display_df[display_columns].rename(columns=column_names)
    
    # Display table
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )


def render_agent_table(df: pd.DataFrame):
    """
    Render a table of agent statistics.
    
    Args:
        df: DataFrame with agent data
    """
    if df.empty:
        st.info("No agent data available.")
        return
    
    display_df = df.copy()
    
    # Format columns
    if "agency_name" in display_df.columns:
        display_df["agency_name"] = display_df["agency_name"].fillna("Unknown Agency")
    
    if "total_value" in display_df.columns:
        display_df["total_value"] = display_df["total_value"].apply(lambda x: f"EUR {x:,.0f}")
    if "avg_price" in display_df.columns:
        display_df["avg_price"] = display_df["avg_price"].apply(lambda x: f"EUR {x:,.0f}")
    if "avg_price_per_sqm" in display_df.columns:
        display_df["avg_price_per_sqm"] = display_df["avg_price_per_sqm"].apply(lambda x: f"EUR {x:,.0f}")
    
    if "avg_days_on_market" in display_df.columns:
        display_df["avg_days_on_market"] = display_df["avg_days_on_market"].apply(lambda x: f"{x:.0f} days")
    if "avg_quality_score" in display_df.columns:
        display_df["avg_quality_score"] = display_df["avg_quality_score"].apply(lambda x: f"{x:.1f}")
    if "vtour_pct" in display_df.columns:
        display_df["vtour_pct"] = display_df["vtour_pct"].apply(lambda x: f"{x:.0f}%")
    if "market_share_pct" in display_df.columns:
        display_df["market_share_pct"] = display_df["market_share_pct"].apply(lambda x: f"{x:.1f}%")
    
    # Select columns
    display_columns = [
        col for col in [
            "agency_name", "listing_count", "total_value", "avg_price",
            "avg_price_per_sqm", "avg_days_on_market", "avg_quality_score",
            "vtour_pct", "market_share_pct"
        ]
        if col in display_df.columns
    ]
    
    column_names = {
        "agency_name": "Agency",
        "listing_count": "Listings",
        "total_value": "Total Value",
        "avg_price": "Avg Price",
        "avg_price_per_sqm": "Avg Price/sqm",
        "avg_days_on_market": "Avg DOM",
        "avg_quality_score": "Quality Score",
        "vtour_pct": "Virtual Tours",
        "market_share_pct": "Market Share",
    }
    
    display_df = display_df[display_columns].rename(columns=column_names)
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )


def render_area_table(df: pd.DataFrame):
    """
    Render a table of area statistics.
    
    Args:
        df: DataFrame with area data
    """
    if df.empty:
        st.info("No area data available.")
        return
    
    display_df = df.copy()
    
    # Format columns
    if "avg_price" in display_df.columns:
        display_df["avg_price"] = display_df["avg_price"].apply(lambda x: f"EUR {x:,.0f}")
    if "median_price" in display_df.columns:
        display_df["median_price"] = display_df["median_price"].apply(lambda x: f"EUR {x:,.0f}")
    if "avg_price_per_sqm" in display_df.columns:
        display_df["avg_price_per_sqm"] = display_df["avg_price_per_sqm"].apply(lambda x: f"EUR {x:,.0f}")
    if "median_price_per_sqm" in display_df.columns:
        display_df["median_price_per_sqm"] = display_df["median_price_per_sqm"].apply(lambda x: f"EUR {x:,.0f}")
    if "avg_sq_meters" in display_df.columns:
        display_df["avg_sq_meters"] = display_df["avg_sq_meters"].apply(lambda x: f"{x:.0f}")
    if "avg_days_on_market" in display_df.columns:
        display_df["avg_days_on_market"] = display_df["avg_days_on_market"].apply(lambda x: f"{x:.0f}")
    
    display_columns = [
        col for col in [
            "geography", "listing_count", "avg_price", "median_price",
            "avg_price_per_sqm", "median_price_per_sqm", "avg_sq_meters",
            "avg_days_on_market"
        ]
        if col in display_df.columns
    ]
    
    column_names = {
        "geography": "Area",
        "listing_count": "Listings",
        "avg_price": "Avg Price",
        "median_price": "Median Price",
        "avg_price_per_sqm": "Avg EUR/sqm",
        "median_price_per_sqm": "Median EUR/sqm",
        "avg_sq_meters": "Avg Size",
        "avg_days_on_market": "Avg DOM",
    }
    
    display_df = display_df[display_columns].rename(columns=column_names)
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )


def render_collection_history_table(df: pd.DataFrame):
    """
    Render a table of collection run history.
    
    Args:
        df: DataFrame with collection run data
    """
    if df.empty:
        st.info("No collection history available.")
        return
    
    display_df = df.copy()
    
    # Format datetime columns
    if "started_at" in display_df.columns:
        display_df["started_at"] = pd.to_datetime(display_df["started_at"]).dt.strftime("%Y-%m-%d %H:%M")
    
    # Add status indicator
    if "status" in display_df.columns:
        display_df["status"] = display_df["status"].apply(
            lambda x: "Completed" if x == "completed" else ("Failed" if x == "failed" else "Running")
        )
    
    display_columns = [
        col for col in [
            "started_at", "status", "properties_found", "new_properties",
            "updated_properties", "price_changes"
        ]
        if col in display_df.columns
    ]
    
    column_names = {
        "started_at": "Date",
        "status": "Status",
        "properties_found": "Found",
        "new_properties": "New",
        "updated_properties": "Updated",
        "price_changes": "Price Changes",
    }
    
    display_df = display_df[display_columns].rename(columns=column_names)
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )
