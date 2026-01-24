"""
Real Estate Analytics Dashboard - Main Streamlit Application
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import init_db, get_session, Property, PropertySnapshot, CollectionRun
from analytics.price_trends import PriceTrendsAnalyzer
from analytics.inventory import InventoryAnalyzer
from analytics.price_reductions import PriceReductionAnalyzer
from analytics.area_analysis import AreaAnalyzer
from analytics.agent_analysis import AgentAnalyzer
from config import MONITORED_AREAS

from dashboard.components.metrics import render_metric_cards, render_stat_box
from dashboard.components.charts import (
    render_price_trend_chart,
    render_inventory_chart,
    render_price_distribution,
    render_area_comparison,
    render_category_pie_chart,
    render_days_on_market_chart,
    render_agent_comparison_chart,
)
from dashboard.components.maps import render_property_map, render_area_heatmap, render_simple_scatter_map
from dashboard.components.tables import (
    render_deals_table,
    render_agent_table,
    render_area_table,
    render_collection_history_table,
)

# Page configuration
st.set_page_config(
    page_title="Real Estate Analytics",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.5rem 1rem;
    }
</style>
""", unsafe_allow_html=True)


def get_quick_stats():
    """Get quick statistics for the sidebar."""
    session = get_session()
    try:
        total_properties = session.query(Property).filter(Property.is_active == True).count()
        
        week_ago = datetime.utcnow() - timedelta(days=7)
        new_this_week = session.query(Property).filter(Property.first_seen >= week_ago).count()
        
        last_run = (
            session.query(CollectionRun)
            .filter(CollectionRun.status == "completed")
            .order_by(CollectionRun.completed_at.desc())
            .first()
        )
        
        return {
            "total_properties": total_properties,
            "new_this_week": new_this_week,
            "last_collection": last_run.completed_at if last_run else None,
        }
    finally:
        session.close()


def render_sidebar():
    """Render the sidebar with navigation and filters."""
    st.sidebar.title("Real Estate Analytics")
    st.sidebar.markdown("---")
    
    # Quick stats
    stats = get_quick_stats()
    st.sidebar.metric("Total Listings", f"{stats['total_properties']:,}")
    st.sidebar.metric("New This Week", f"{stats['new_this_week']:,}")
    
    if stats["last_collection"]:
        st.sidebar.caption(f"Last updated: {stats['last_collection'].strftime('%Y-%m-%d %H:%M')}")
    else:
        st.sidebar.caption("No data collected yet")
    
    st.sidebar.markdown("---")
    
    # Navigation
    page = st.sidebar.radio(
        "Navigate",
        ["Overview", "Price Trends", "Deal Finder", "Area Analysis", "Agent Insights", "Data Collection"],
        label_visibility="collapsed",
    )
    
    st.sidebar.markdown("---")
    
    # Monitored areas
    st.sidebar.subheader("Monitored Areas")
    for area_id, area_name in MONITORED_AREAS.items():
        st.sidebar.text(f"• {area_name}")
    
    return page


def render_overview_page():
    """Render the overview/dashboard page."""
    st.title("Market Overview")
    st.markdown("Real-time insights into the real estate market")
    
    # Key metrics
    with InventoryAnalyzer() as inventory:
        summary = inventory.get_inventory_summary()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Active Listings",
            f"{summary.get('total_active_listings', 0):,}",
        )
    
    with col2:
        st.metric(
            "New This Week",
            f"{summary.get('new_listings_this_week', 0):,}",
        )
    
    with col3:
        st.metric(
            "New This Month",
            f"{summary.get('new_listings_this_month', 0):,}",
        )
    
    with col4:
        st.metric(
            "Avg Days on Market",
            f"{summary.get('avg_days_on_market', 0):.0f}",
        )
    
    st.markdown("---")
    
    # Charts row
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Price Trends")
        with PriceTrendsAnalyzer() as analyzer:
            trends_df = analyzer.get_price_per_sqm_trends(days=90, resample="W")
        render_price_trend_chart(trends_df, "Average Price per sqm (Last 90 Days)")
    
    with col2:
        st.subheader("New Listings")
        with InventoryAnalyzer() as analyzer:
            inventory_df = analyzer.get_inventory_trends(days=90, resample="W")
        render_inventory_chart(inventory_df, "New Listings per Week")
    
    st.markdown("---")
    
    # Area and category breakdown
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Top Areas by Listings")
        with AreaAnalyzer() as analyzer:
            area_df = analyzer.get_area_summary(min_listings=2)
        render_area_comparison(area_df, metric="listing_count")
    
    with col2:
        st.subheader("Property Types")
        if summary.get("listings_by_category"):
            cat_df = pd.DataFrame([
                {"category": k, "count": v}
                for k, v in summary["listings_by_category"].items()
            ])
            render_category_pie_chart(cat_df)
        else:
            st.info("No category data available yet.")
    
    # Map
    st.markdown("---")
    st.subheader("Property Map")
    
    with AreaAnalyzer() as analyzer:
        map_df = analyzer.get_area_price_heatmap_data()
    
    if not map_df.empty:
        render_simple_scatter_map(map_df, color_col="price_per_sqm")
    else:
        st.info("No location data available for map.")


def render_price_trends_page():
    """Render the price trends analysis page."""
    st.title("Price Trends Analysis")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        days = st.selectbox("Time Period", [30, 60, 90, 180, 365], index=2)
    
    with col2:
        resample = st.selectbox("Group By", ["Daily", "Weekly", "Monthly"], index=1)
        resample_map = {"Daily": "D", "Weekly": "W", "Monthly": "M"}
    
    with col3:
        area_filter = st.text_input("Filter by Area (optional)", "")
    
    st.markdown("---")
    
    # Price trends chart
    with PriceTrendsAnalyzer() as analyzer:
        trends_df = analyzer.get_price_per_sqm_trends(
            days=days,
            area_filter=area_filter if area_filter else None,
            resample=resample_map[resample],
        )
        
        distribution = analyzer.get_price_distribution(area_filter=area_filter if area_filter else None)
        
        monthly = analyzer.get_monthly_summary(months=6)
        
        by_area = analyzer.get_price_trends_by_area(days=days)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Price per sqm Over Time")
        render_price_trend_chart(trends_df)
    
    with col2:
        st.subheader("Price Distribution")
        if not distribution.empty:
            stats = distribution.iloc[0]
            
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("Avg Price/sqm", f"EUR {stats.get('sqm_price_mean', 0):,.0f}")
            with col_b:
                st.metric("Median Price/sqm", f"EUR {stats.get('sqm_price_median', 0):,.0f}")
            with col_c:
                st.metric("Total Listings", f"{stats.get('total_listings', 0):,}")
    
    st.markdown("---")
    
    # Area price trends
    st.subheader("Price Trends by Area")
    
    if not by_area.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Price Changes by Area**")
            by_area_display = by_area.copy()
            by_area_display["current_avg"] = by_area_display["current_avg"].apply(lambda x: f"EUR {x:,.0f}")
            by_area_display["change_pct"] = by_area_display["change_pct"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A")
            st.dataframe(
                by_area_display[["geography", "current_avg", "change_pct", "current_count"]].rename(
                    columns={"geography": "Area", "current_avg": "Avg Price/sqm", "change_pct": "Change %", "current_count": "Listings"}
                ),
                use_container_width=True,
                hide_index=True,
            )
        
        with col2:
            render_area_comparison(
                pd.DataFrame({
                    "geography": by_area["geography"],
                    "avg_price_per_sqm": by_area["current_avg"],
                }),
                metric="avg_price_per_sqm"
            )
    else:
        st.info("Not enough data to compare periods. Collect more data over time.")
    
    # Monthly summary
    st.markdown("---")
    st.subheader("Monthly Summary")
    
    if not monthly.empty:
        st.dataframe(
            monthly.rename(columns={
                "month": "Month",
                "avg_price": "Avg Price",
                "median_price": "Median Price",
                "listing_count": "Listings",
                "avg_price_per_sqm": "Avg EUR/sqm",
                "median_price_per_sqm": "Median EUR/sqm",
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Monthly summary not available yet.")


def render_deal_finder_page():
    """Render the deal finder page."""
    st.title("Deal Finder")
    st.markdown("Find properties with price reductions and potential bargains")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        days = st.slider("Look back days", 7, 90, 30)
    
    with col2:
        min_reduction = st.slider("Minimum reduction %", 0, 30, 5)
    
    with col3:
        max_results = st.slider("Max results", 10, 100, 50)
    
    st.markdown("---")
    
    # Price reduction stats
    with PriceReductionAnalyzer() as analyzer:
        stats = analyzer.get_price_reduction_stats(days=days)
        recent_drops = analyzer.get_recent_price_drops(
            days=days,
            min_reduction_pct=min_reduction,
            limit=max_results,
        )
        deals = analyzer.get_deal_alerts(
            max_price_per_sqm_percentile=25,
            min_days_on_market=30,
        )
    
    # Stats row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Reductions", f"{stats.get('total_reductions', 0):,}")
    
    with col2:
        st.metric("Avg Reduction", f"{stats.get('avg_reduction_pct', 0):.1f}%")
    
    with col3:
        st.metric("Max Reduction", f"{stats.get('max_reduction_pct', 0):.1f}%")
    
    with col4:
        st.metric("Total Value Reduced", f"EUR {stats.get('total_value_reduced', 0):,.0f}")
    
    st.markdown("---")
    
    # Tabs for different deal views
    tab1, tab2 = st.tabs(["Recent Price Drops", "Undervalued Properties"])
    
    with tab1:
        st.subheader(f"Properties with Price Reductions (Last {days} Days)")
        render_deals_table(recent_drops)
    
    with tab2:
        st.subheader("Potential Deals - Below Market Value")
        st.markdown("Properties in the bottom 25% for price/sqm that have been listed for 30+ days")
        render_deals_table(deals)


def render_area_analysis_page():
    """Render the area analysis page."""
    st.title("Area Analysis")
    st.markdown("Compare different neighborhoods and areas")
    
    with AreaAnalyzer() as analyzer:
        area_summary = analyzer.get_area_summary(min_listings=2)
        heatmap_data = analyzer.get_area_price_heatmap_data()
        hottest_new = analyzer.get_hottest_areas(days=30, metric="new_listings")
        hottest_growth = analyzer.get_hottest_areas(days=60, metric="price_growth")
    
    # Area summary table
    st.subheader("Area Overview")
    render_area_table(area_summary)
    
    st.markdown("---")
    
    # Hot areas
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Hottest Areas (New Listings)")
        if not hottest_new.empty:
            st.dataframe(
                hottest_new.rename(columns={"geography": "Area", "new_listings": "New Listings (30d)"}),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No data available.")
    
    with col2:
        st.subheader("Fastest Price Growth")
        if not hottest_growth.empty:
            hottest_growth["price_growth_pct"] = hottest_growth["price_growth_pct"].apply(lambda x: f"{x:+.1f}%")
            st.dataframe(
                hottest_growth.rename(columns={"geography": "Area", "price_growth_pct": "Price Growth (60d)"}),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Not enough historical data for comparison.")
    
    st.markdown("---")
    
    # Map
    st.subheader("Area Price Map")
    if not heatmap_data.empty:
        render_simple_scatter_map(heatmap_data, color_col="price_per_sqm")
    else:
        st.info("No location data available for map.")
    
    st.markdown("---")
    
    # Area comparison
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Price per sqm by Area")
        render_area_comparison(area_summary, metric="avg_price_per_sqm")
    
    with col2:
        st.subheader("Average Days on Market by Area")
        render_area_comparison(area_summary, metric="avg_days_on_market")


def render_agent_insights_page():
    """Render the agent insights page."""
    st.title("Agent Insights")
    st.markdown("Analyze real estate agent and agency performance")
    
    with AgentAnalyzer() as analyzer:
        agent_summary = analyzer.get_agent_summary(min_listings=2)
        top_by_listings = analyzer.get_top_agents(metric="listing_count", limit=10)
        top_by_value = analyzer.get_top_agents(metric="total_value", limit=10)
        market_share = analyzer.get_market_share()
        pricing_comparison = analyzer.get_agent_pricing_comparison(min_listings=3)
    
    # Summary stats
    if not agent_summary.empty:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Agents", f"{len(agent_summary):,}")
        
        with col2:
            avg_listings = agent_summary["listing_count"].mean()
            st.metric("Avg Listings/Agent", f"{avg_listings:.1f}")
        
        with col3:
            top_agent = agent_summary.iloc[0]["agency_name"] if not agent_summary.empty else "N/A"
            st.metric("Top Agent", top_agent[:20] + "..." if len(str(top_agent)) > 20 else top_agent)
        
        with col4:
            if not market_share.empty:
                top_share = market_share.iloc[0]["market_share_pct"]
                st.metric("Top Market Share", f"{top_share:.1f}%")
    
    st.markdown("---")
    
    # Agent leaderboard
    st.subheader("Agent Leaderboard")
    render_agent_table(agent_summary)
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Top Agents by Listings")
        render_agent_comparison_chart(top_by_listings, metric="listing_count")
    
    with col2:
        st.subheader("Top Agents by Total Value")
        render_agent_comparison_chart(top_by_value, metric="total_value")
    
    st.markdown("---")
    
    # Pricing strategies
    st.subheader("Agent Pricing Strategies")
    
    if not pricing_comparison.empty:
        # Show pricing strategy breakdown
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.dataframe(
                pricing_comparison[["agency_name", "listing_count", "avg_price_per_sqm", "vs_market_avg_pct", "pricing_strategy"]].rename(
                    columns={
                        "agency_name": "Agency",
                        "listing_count": "Listings",
                        "avg_price_per_sqm": "Avg EUR/sqm",
                        "vs_market_avg_pct": "vs Market %",
                        "pricing_strategy": "Strategy",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        
        with col2:
            strategy_counts = pricing_comparison["pricing_strategy"].value_counts()
            st.markdown("**Pricing Strategy Distribution**")
            for strategy, count in strategy_counts.items():
                st.write(f"• {strategy.title()}: {count} agents")
    else:
        st.info("Not enough data for pricing analysis.")


def render_data_collection_page():
    """Render the data collection management page."""
    st.title("Data Collection")
    st.markdown("Monitor and manage data collection")
    
    with InventoryAnalyzer() as analyzer:
        collection_history = analyzer.get_collection_history(limit=20)
    
    # Collection stats
    if not collection_history.empty:
        latest = collection_history.iloc[0]
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Last Run Status", latest.get("status", "N/A").title())
        
        with col2:
            st.metric("Properties Found", f"{latest.get('properties_found', 0):,}")
        
        with col3:
            st.metric("New Properties", f"{latest.get('new_properties', 0):,}")
        
        with col4:
            st.metric("Price Changes", f"{latest.get('price_changes', 0):,}")
    
    st.markdown("---")
    
    # Collection history
    st.subheader("Collection History")
    render_collection_history_table(collection_history)
    
    st.markdown("---")
    
    # Instructions
    st.subheader("How to Collect Data")
    
    with st.expander("Manual Collection"):
        st.markdown("""
        Run the following command to collect data manually:
        
        ```bash
        python scripts/run_collection.py
        ```
        
        This will fetch all listings from the configured areas and store them in the database.
        """)
    
    with st.expander("Scheduled Collection"):
        st.markdown("""
        To set up automated data collection, run the scheduler:
        
        ```bash
        python collector/scheduler.py --run-now
        ```
        
        Options:
        - `--hour`: Hour to run (0-23)
        - `--minute`: Minute to run (0-59)
        - `--days`: Days to run ('*' for all, 'mon-fri' for weekdays)
        - `--run-now`: Run immediately on start
        """)
    
    with st.expander("Configuration"):
        st.markdown("""
        Edit `config.py` to modify:
        
        - **MONITORED_AREAS**: Add or remove area IDs to track
        - **COLLECTION_SCHEDULE**: Change default collection times
        - **REQUEST_DELAY_SECONDS**: Adjust API rate limiting
        """)


def main():
    """Main application entry point."""
    # Initialize database
    init_db()
    
    # Render sidebar and get selected page
    page = render_sidebar()
    
    # Render selected page
    if page == "Overview":
        render_overview_page()
    elif page == "Price Trends":
        render_price_trends_page()
    elif page == "Deal Finder":
        render_deal_finder_page()
    elif page == "Area Analysis":
        render_area_analysis_page()
    elif page == "Agent Insights":
        render_agent_insights_page()
    elif page == "Data Collection":
        render_data_collection_page()


if __name__ == "__main__":
    main()
