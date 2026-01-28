"""
Real Estate Analytics Dashboard - Main Streamlit Application
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path

# Ensure the parent directory is in the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Ensure data directory exists
data_dir = project_root / "data"
data_dir.mkdir(exist_ok=True)

from database.models import init_db, get_session, Property, PropertySnapshot, CollectionRun
from analytics.price_trends import PriceTrendsAnalyzer
from analytics.inventory import InventoryAnalyzer
from analytics.price_reductions import PriceReductionAnalyzer
from analytics.area_analysis import AreaAnalyzer
from analytics.agent_analysis import AgentAnalyzer
from analytics.advanced_insights import AdvancedInsightsAnalyzer
from analytics.investor_tools import InvestorAnalyzer
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

# Custom CSS - works with both light and dark themes
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    .stMetric {
        background-color: rgba(28, 131, 225, 0.1);
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid rgba(28, 131, 225, 0.2);
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
        
        week_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
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
        ["Investor Dashboard", "Deal Finder", "Market History", "Market Intelligence", "Property Insights", "Area Analysis", "Agent Insights", "Data Collection"],
        label_visibility="collapsed",
    )
    
    st.sidebar.markdown("---")
    
    # Monitored areas
    st.sidebar.subheader("Monitored Areas")
    for area_id, area_name in MONITORED_AREAS.items():
        st.sidebar.text(f"• {area_name}")
    
    return page


def render_investor_dashboard():
    """Render the investor-focused dashboard with edge-gaining tools."""
    st.title("🎯 Investor Dashboard")
    st.markdown("Tools and insights to gain an edge in the real estate market")
    
    with InvestorAnalyzer() as analyzer:
        # Market Timing Signal - Top of page
        st.subheader("📊 Market Timing Signal")
        
        signals = analyzer.get_market_timing_signals()
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            market_type = signals.get("market_type", "Unknown")
            emoji = signals.get("market_emoji", "⚪")
            st.markdown(f"### {emoji} {market_type}")
            st.markdown(f"*{signals.get('recommendation', '')}*")
        
        with col2:
            st.metric("Avg Days on Market", f"{signals.get('avg_days_on_market', 0):.0f}")
            st.metric("Price Reduction Rate", f"{signals.get('price_reduction_rate', 0):.1f}%")
        
        with col3:
            st.metric("Active Inventory", f"{signals.get('total_inventory', 0):,}")
            st.metric("New This Week", f"{signals.get('new_listings_7d', 0):,}")
        
        st.markdown("---")
        
        # Tabs for different investor tools
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🚀 First Mover", 
            "💰 Investment Calc",
            "📈 Appreciation Radar", 
            "🔥 Distressed Props",
            "🗺️ Area Signals"
        ])
        
        # TAB 1: First Mover - New Listings
        with tab1:
            st.subheader("🚀 New Listings - First Mover Advantage")
            st.markdown("Be first to see new properties. Contact agents before other investors.")
            
            hours = st.selectbox("Show listings from last:", [24, 48, 72, 168], index=1, 
                               format_func=lambda x: f"{x} hours" if x < 168 else "7 days")
            
            new_listings = analyzer.get_new_listings(hours=hours, limit=30)
            
            if not new_listings.empty:
                # Summary
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("New Listings", len(new_listings))
                with col2:
                    avg_price = new_listings["price"].mean()
                    st.metric("Avg Price", f"€{avg_price:,.0f}")
                with col3:
                    avg_sqm = new_listings["price_per_sqm"].mean()
                    st.metric("Avg €/sqm", f"€{avg_sqm:,.0f}" if pd.notna(avg_sqm) else "N/A")
                
                st.markdown("---")
                
                # Listings table
                display_df = new_listings[["id", "geography", "category", "sq_meters", "rooms", 
                                          "price", "price_per_sqm", "hours_listed", "agency_name"]].copy()
                display_df["link"] = display_df["id"].apply(lambda x: f"https://www.spitogatos.gr/aggelia/11{x}")
                display_df = display_df[["id", "link", "geography", "category", "sq_meters", "rooms", 
                                        "price", "price_per_sqm", "hours_listed", "agency_name"]]
                display_df.columns = ["ID", "Link", "Area", "Type", "Size", "Rooms", "Price", "€/sqm", "Hours Listed", "Agent"]
                display_df["Price"] = display_df["Price"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["€/sqm"] = display_df["€/sqm"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["Agent"] = display_df["Agent"].apply(lambda x: str(x)[:15] + "..." if x and len(str(x)) > 15 else x)
                
                st.dataframe(
                    display_df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Link": st.column_config.LinkColumn("Link", display_text="View")
                    }
                )
                
                # New listings by area
                st.markdown("**Hot Areas (Most New Listings)**")
                area_new = analyzer.get_new_listings_by_area(hours=hours)
                if not area_new.empty:
                    for _, row in area_new.head(5).iterrows():
                        st.write(f"📍 **{row['geography']}**: {int(row['new_listings'])} new listings")
            else:
                st.info(f"No new listings in the last {hours} hours.")
        
        # TAB 2: Investment Calculator
        with tab2:
            st.subheader("💰 Investment Calculator")
            st.markdown("Calculate ROI, cap rate, and cash flow for potential investments")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Property Details**")
                purchase_price = st.number_input("Purchase Price (€)", value=250000, step=10000)
                sq_meters = st.number_input("Size (sqm)", value=80, step=5)
                monthly_rent = st.number_input("Expected Monthly Rent (€)", value=800, step=50)
            
            with col2:
                st.markdown("**Financing**")
                down_payment_pct = st.slider("Down Payment (%)", 10, 100, 20)
                interest_rate = st.slider("Interest Rate (%)", 1.0, 10.0, 4.5, 0.1)
                loan_term = st.selectbox("Loan Term (years)", [15, 20, 25, 30], index=2)
            
            expenses_pct = st.slider("Annual Expenses (% of rent)", 10, 40, 25, 
                                    help="Include: maintenance, insurance, vacancy, property tax")
            
            if st.button("Calculate Investment Metrics", type="primary"):
                metrics = analyzer.calculate_investment_metrics(
                    purchase_price=purchase_price,
                    monthly_rent=monthly_rent,
                    down_payment_pct=down_payment_pct,
                    interest_rate=interest_rate,
                    loan_term_years=loan_term,
                    annual_expenses_pct=expenses_pct,
                )
                
                st.markdown("---")
                st.markdown("### 📊 Investment Analysis")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    cap_rate = metrics["cap_rate"]
                    cap_color = "green" if cap_rate >= 5 else ("orange" if cap_rate >= 3 else "red")
                    st.metric("Cap Rate", f"{cap_rate:.2f}%")
                    st.caption("NOI / Purchase Price")
                
                with col2:
                    coc = metrics["cash_on_cash_return"]
                    st.metric("Cash-on-Cash", f"{coc:.2f}%")
                    st.caption("Annual Cash / Down Payment")
                
                with col3:
                    roi = metrics["total_roi"]
                    st.metric("Total ROI", f"{roi:.2f}%")
                    st.caption("Including 3% appreciation")
                
                with col4:
                    cashflow = metrics["monthly_cashflow"]
                    cf_color = "green" if cashflow > 0 else "red"
                    st.metric("Monthly Cash Flow", f"€{cashflow:,.0f}")
                
                st.markdown("---")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Income & Expenses**")
                    st.write(f"• Annual Rent: €{metrics['annual_rent']:,.0f}")
                    st.write(f"• Annual Expenses: €{metrics['annual_expenses']:,.0f}")
                    st.write(f"• NOI: €{metrics['net_operating_income']:,.0f}")
                    st.write(f"• Annual Mortgage: €{metrics['annual_mortgage']:,.0f}")
                    st.write(f"• **Net Cash Flow: €{metrics['annual_cashflow']:,.0f}**")
                
                with col2:
                    st.markdown("**Key Metrics**")
                    st.write(f"• Down Payment: €{metrics['down_payment']:,.0f}")
                    st.write(f"• Loan Amount: €{metrics['loan_amount']:,.0f}")
                    st.write(f"• Monthly Mortgage: €{metrics['monthly_mortgage']:,.0f}")
                    st.write(f"• GRM: {metrics['gross_rent_multiplier']:.1f} years")
                    st.write(f"• Break-even Occupancy: {metrics['break_even_occupancy']:.0f}%")
                
                # Investment verdict
                st.markdown("---")
                if cap_rate >= 5 and cashflow > 0:
                    st.success("✅ **Strong Investment** - Good cap rate and positive cash flow")
                elif cap_rate >= 3 and cashflow >= 0:
                    st.warning("⚠️ **Moderate Investment** - Acceptable returns, consider negotiating price")
                else:
                    st.error("❌ **Weak Investment** - Low returns or negative cash flow")
        
        # TAB 3: Appreciation Radar
        with tab3:
            st.subheader("📈 Appreciation Radar")
            st.markdown("Areas with highest appreciation potential based on market signals")
            
            appreciation_df = analyzer.get_appreciation_leaders(min_listings=3)
            
            if not appreciation_df.empty:
                # Top areas chart
                import plotly.express as px
                
                top_10 = appreciation_df.head(10)
                fig = px.bar(
                    top_10,
                    x="geography",
                    y="appreciation_score",
                    color="appreciation_score",
                    color_continuous_scale="RdYlGn",
                    title="Top 10 Areas by Appreciation Potential"
                )
                fig.update_layout(showlegend=False, xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
                
                # Detailed table
                st.markdown("**Area Details**")
                display_df = appreciation_df[["geography", "appreciation_score", "trend", 
                                             "total_listings", "avg_price_sqm", "avg_dom", 
                                             "new_listings_30d"]].head(15)
                display_df.columns = ["Area", "Score", "Trend", "Listings", "Avg €/sqm", "Avg DOM", "New (30d)"]
                display_df["Avg €/sqm"] = display_df["Avg €/sqm"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["Avg DOM"] = display_df["Avg DOM"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "N/A")
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                # Legend
                st.markdown("""
                **Score Components:**
                - 🔥 Activity (40%): New listing volume
                - ⚡ Velocity (35%): How fast properties sell
                - 💪 Health (25%): Low price reduction rate
                """)
            else:
                st.info("Not enough data for appreciation analysis.")
        
        # TAB 4: Distressed Properties
        with tab4:
            st.subheader("🔥 Distressed Properties")
            st.markdown("Maximum negotiation leverage - motivated sellers")
            
            distressed_df = analyzer.get_distressed_properties(limit=30)
            
            if not distressed_df.empty:
                # Summary stats
                col1, col2, col3, col4 = st.columns(4)
                
                high_distress = len(distressed_df[distressed_df["distress_level"].isin(["High", "Very High"])])
                with col1:
                    st.metric("High Distress", high_distress)
                with col2:
                    avg_dom = distressed_df["days_on_market"].mean()
                    st.metric("Avg Days Listed", f"{avg_dom:.0f}")
                with col3:
                    reduced_pct = distressed_df["price_reduced"].mean() * 100
                    st.metric("Price Reduced", f"{reduced_pct:.0f}%")
                with col4:
                    avg_below = distressed_df["below_avg_pct"].mean()
                    st.metric("Avg Below Market", f"{avg_below:.1f}%")
                
                st.markdown("---")
                
                # Distressed properties table
                display_df = distressed_df[["id", "geography", "category", "sq_meters", "price", 
                                           "price_per_sqm", "days_on_market", "below_avg_pct",
                                           "distress_score", "distress_level"]].copy()
                display_df["link"] = display_df["id"].apply(lambda x: f"https://www.spitogatos.gr/aggelia/11{x}")
                display_df = display_df[["id", "link", "geography", "category", "sq_meters", "price", 
                                        "price_per_sqm", "days_on_market", "below_avg_pct",
                                        "distress_score", "distress_level"]]
                display_df.columns = ["ID", "Link", "Area", "Type", "Size", "Price", "€/sqm", "Days", "Below Avg %", "Score", "Level"]
                display_df["Price"] = display_df["Price"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["€/sqm"] = display_df["€/sqm"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["Below Avg %"] = display_df["Below Avg %"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
                
                st.dataframe(
                    display_df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Link": st.column_config.LinkColumn("Link", display_text="View"),
                        "Score": st.column_config.ProgressColumn(
                            "Score",
                            min_value=0,
                            max_value=10,
                            format="%.1f"
                        )
                    }
                )
                
                st.markdown("""
                **Distress Indicators:**
                - 📅 Long days on market (35%)
                - 📉 Price already reduced (40%)
                - 💰 Below area average (25%)
                """)
            else:
                st.info("No distressed properties found.")
        
        # TAB 5: Area Market Signals
        with tab5:
            st.subheader("🗺️ Market Signals by Area")
            st.markdown("Identify buyer's and seller's markets in each neighborhood")
            
            area_signals = analyzer.get_market_health_by_area(min_listings=3)
            
            if not area_signals.empty:
                # Group by market type
                col1, col2, col3 = st.columns(3)
                
                buyers = area_signals[area_signals["market_type"].str.contains("Buyer")]
                sellers = area_signals[area_signals["market_type"].str.contains("Seller")]
                balanced = area_signals[area_signals["market_type"].str.contains("Balanced")]
                
                with col1:
                    st.markdown("### 🟢 Buyer's Markets")
                    st.caption("Good for negotiating")
                    if not buyers.empty:
                        for _, row in buyers.head(8).iterrows():
                            st.write(f"• {row['geography']}")
                            st.caption(f"  DOM: {row['avg_dom']:.0f}d, Reduced: {row['reduction_rate']:.0f}%")
                    else:
                        st.write("None identified")
                
                with col2:
                    st.markdown("### 🟡 Balanced Markets")
                    st.caption("Normal conditions")
                    if not balanced.empty:
                        for _, row in balanced.head(8).iterrows():
                            st.write(f"• {row['geography']}")
                            st.caption(f"  DOM: {row['avg_dom']:.0f}d, Reduced: {row['reduction_rate']:.0f}%")
                    else:
                        st.write("None identified")
                
                with col3:
                    st.markdown("### 🔴 Seller's Markets")
                    st.caption("Act fast on deals")
                    if not sellers.empty:
                        for _, row in sellers.head(8).iterrows():
                            st.write(f"• {row['geography']}")
                            st.caption(f"  DOM: {row['avg_dom']:.0f}d, Reduced: {row['reduction_rate']:.0f}%")
                    else:
                        st.write("None identified")
                
                st.markdown("---")
                
                # Full table
                st.markdown("**All Areas**")
                display_df = area_signals[["geography", "market_type", "listings", "avg_dom", "reduction_rate", "new_7d"]]
                display_df.columns = ["Area", "Market Type", "Listings", "Avg DOM", "Reduction %", "New (7d)"]
                display_df["Avg DOM"] = display_df["Avg DOM"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "N/A")
                display_df["Reduction %"] = display_df["Reduction %"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("Not enough data for area analysis.")


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


def render_market_history_page():
    """Render the market history page showing sold/removed listings."""
    st.title("📜 Market History")
    st.markdown("Track removed listings (likely sold) to understand actual market demand")
    
    with AdvancedInsightsAnalyzer() as analyzer:
        # Summary stats
        summary = analyzer.get_removed_listings_summary()
        
        if summary:
            st.subheader("📊 Historical Summary")
            
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("Total Removed", f"{summary.get('total_removed', 0):,}")
            with col2:
                avg_price = summary.get('avg_price')
                st.metric("Avg Sold Price", f"€{avg_price:,.0f}" if avg_price else "N/A")
            with col3:
                avg_sqm = summary.get('avg_price_sqm')
                st.metric("Avg €/sqm", f"€{avg_sqm:,.0f}" if avg_sqm else "N/A")
            with col4:
                avg_dom = summary.get('avg_days_to_sell')
                st.metric("Avg Days to Sell", f"{avg_dom:.0f}" if avg_dom else "N/A")
            with col5:
                reduction_pct = summary.get('had_price_reduction_pct')
                st.metric("Had Price Cut", f"{reduction_pct:.0f}%" if reduction_pct else "N/A")
            
            st.markdown("---")
        
        # Tabs for different views
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📋 Recent Removals", 
            "📊 Sold vs Active",
            "📍 By Area", 
            "💰 By Price",
            "📐 By Size"
        ])
        
        # Tab 1: Recent removed listings
        with tab1:
            st.subheader("Recently Removed Listings")
            st.markdown("Properties that left the market (likely sold or delisted)")
            
            removed_df = analyzer.get_removed_listings(limit=50)
            
            if not removed_df.empty:
                display_df = removed_df[["id", "geography", "category", "sq_meters", "rooms",
                                        "price", "price_per_sqm", "days_on_market", "agency_name"]].copy()
                display_df["link"] = display_df["id"].apply(lambda x: f"https://www.spitogatos.gr/aggelia/11{x}")
                display_df = display_df[["id", "link", "geography", "category", "sq_meters", "rooms",
                                        "price", "price_per_sqm", "days_on_market", "agency_name"]]
                display_df.columns = ["ID", "Link", "Area", "Type", "Size", "Rooms", "Price", "€/sqm", "Days Listed", "Agent"]
                display_df["Price"] = display_df["Price"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["€/sqm"] = display_df["€/sqm"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["Agent"] = display_df["Agent"].apply(lambda x: str(x)[:15] + "..." if x and len(str(x)) > 15 else x)
                
                st.dataframe(
                    display_df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Link": st.column_config.LinkColumn("Link", display_text="View")
                    }
                )
            else:
                st.info("No removed listings recorded yet. Historical data will accumulate over time.")
        
        # Tab 2: Sold vs Active comparison
        with tab2:
            st.subheader("Sold vs Active Comparison")
            st.markdown("Compare attributes of properties that sold vs those still on market")
            
            comparison_df = analyzer.get_sold_vs_active_comparison()
            
            if not comparison_df.empty and len(comparison_df) == 2:
                col1, col2 = st.columns(2)
                
                sold_row = comparison_df[comparison_df["status"] == "Sold/Removed"].iloc[0] if len(comparison_df[comparison_df["status"] == "Sold/Removed"]) > 0 else None
                active_row = comparison_df[comparison_df["status"] == "Active"].iloc[0] if len(comparison_df[comparison_df["status"] == "Active"]) > 0 else None
                
                if sold_row is not None and active_row is not None:
                    with col1:
                        st.markdown("### ✅ What Sold")
                        st.metric("Count", f"{int(sold_row['count']):,}")
                        st.metric("Avg Price", f"€{sold_row['avg_price']:,.0f}" if pd.notna(sold_row['avg_price']) else "N/A")
                        st.metric("Avg €/sqm", f"€{sold_row['avg_price_sqm']:,.0f}" if pd.notna(sold_row['avg_price_sqm']) else "N/A")
                        st.metric("Avg Size", f"{sold_row['avg_size']:.0f} sqm" if pd.notna(sold_row['avg_size']) else "N/A")
                        st.metric("Avg Rooms", f"{sold_row['avg_rooms']:.1f}" if pd.notna(sold_row['avg_rooms']) else "N/A")
                        st.metric("Had Price Cut", f"{sold_row['reduction_rate']:.0f}%" if pd.notna(sold_row['reduction_rate']) else "N/A")
                    
                    with col2:
                        st.markdown("### 🏠 Still Active")
                        st.metric("Count", f"{int(active_row['count']):,}")
                        st.metric("Avg Price", f"€{active_row['avg_price']:,.0f}" if pd.notna(active_row['avg_price']) else "N/A")
                        st.metric("Avg €/sqm", f"€{active_row['avg_price_sqm']:,.0f}" if pd.notna(active_row['avg_price_sqm']) else "N/A")
                        st.metric("Avg Size", f"{active_row['avg_size']:.0f} sqm" if pd.notna(active_row['avg_size']) else "N/A")
                        st.metric("Avg Rooms", f"{active_row['avg_rooms']:.1f}" if pd.notna(active_row['avg_rooms']) else "N/A")
                        st.metric("Has Price Cut", f"{active_row['reduction_rate']:.0f}%" if pd.notna(active_row['reduction_rate']) else "N/A")
                    
                    # Insights
                    st.markdown("---")
                    st.markdown("### 💡 Key Insights")
                    
                    insights = []
                    if sold_row['avg_price'] and active_row['avg_price']:
                        if sold_row['avg_price'] < active_row['avg_price']:
                            diff_pct = (active_row['avg_price'] - sold_row['avg_price']) / active_row['avg_price'] * 100
                            insights.append(f"📉 Sold properties were **{diff_pct:.0f}% cheaper** on average than current listings")
                        else:
                            diff_pct = (sold_row['avg_price'] - active_row['avg_price']) / active_row['avg_price'] * 100
                            insights.append(f"📈 Sold properties were **{diff_pct:.0f}% more expensive** on average")
                    
                    if sold_row['avg_size'] and active_row['avg_size']:
                        if sold_row['avg_size'] < active_row['avg_size']:
                            insights.append(f"📐 Smaller properties sell faster (Sold avg: {sold_row['avg_size']:.0f}sqm vs Active avg: {active_row['avg_size']:.0f}sqm)")
                        else:
                            insights.append(f"📐 Larger properties are selling (Sold avg: {sold_row['avg_size']:.0f}sqm)")
                    
                    for insight in insights:
                        st.write(insight)
                else:
                    st.dataframe(comparison_df, use_container_width=True, hide_index=True)
            else:
                st.info("Need both active and removed listings for comparison.")
        
        # Tab 3: Removed by Area
        with tab3:
            st.subheader("Sales by Area")
            st.markdown("Which areas have the highest turnover (most sales)?")
            
            by_area = analyzer.get_removed_by_area(min_removed=1)
            
            if not by_area.empty:
                import plotly.express as px
                
                fig = px.bar(
                    by_area.head(15),
                    x="geography",
                    y="removed_count",
                    color="avg_dom",
                    color_continuous_scale="RdYlGn_r",
                    title="Sales Count by Area (color = avg days to sell)"
                )
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
                
                display_df = by_area[["geography", "removed_count", "avg_sold_price", 
                                     "avg_sold_price_sqm", "avg_dom", "reduction_rate"]].head(20)
                display_df.columns = ["Area", "Sold", "Avg Price", "Avg €/sqm", "Avg Days", "Reduced %"]
                display_df["Avg Price"] = display_df["Avg Price"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["Avg €/sqm"] = display_df["Avg €/sqm"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["Avg Days"] = display_df["Avg Days"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "N/A")
                display_df["Reduced %"] = display_df["Reduced %"].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else "N/A")
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("No area sales data available yet.")
        
        # Tab 4: Removed by Price Range
        with tab4:
            st.subheader("Sales by Price Range")
            st.markdown("Which price points have the most buyer activity?")
            
            by_price = analyzer.get_removed_by_price_range()
            
            if not by_price.empty:
                import plotly.express as px
                
                fig = px.bar(
                    by_price,
                    x="price_range",
                    y="sold_count",
                    color="avg_dom",
                    color_continuous_scale="RdYlGn_r",
                    title="Sales by Price Range (color = avg days to sell)"
                )
                st.plotly_chart(fig, use_container_width=True)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Sales Volume**")
                    for _, row in by_price.iterrows():
                        pct = row['sold_count'] / by_price['sold_count'].sum() * 100
                        st.write(f"• **{row['price_range']}**: {row['sold_count']} ({pct:.0f}%)")
                
                with col2:
                    st.markdown("**Avg Time to Sell**")
                    for _, row in by_price.iterrows():
                        emoji = "🔥" if row['avg_dom'] and row['avg_dom'] < 40 else ("📈" if row['avg_dom'] and row['avg_dom'] < 60 else "🐌")
                        dom_str = f"{row['avg_dom']:.0f} days" if pd.notna(row['avg_dom']) else "N/A"
                        st.write(f"{emoji} **{row['price_range']}**: {dom_str}")
            else:
                st.info("No price range sales data available yet.")
        
        # Tab 5: Removed by Size
        with tab5:
            st.subheader("Sales by Size")
            st.markdown("Which property sizes are buyers actually purchasing?")
            
            by_size = analyzer.get_removed_by_size()
            
            if not by_size.empty:
                import plotly.express as px
                
                fig = px.bar(
                    by_size,
                    x="size_range",
                    y="sold_count",
                    color="avg_dom",
                    color_continuous_scale="RdYlGn_r",
                    title="Sales by Size (color = avg days to sell)"
                )
                st.plotly_chart(fig, use_container_width=True)
                
                display_df = by_size[["size_range", "sold_count", "avg_price", "avg_price_sqm", "avg_dom"]]
                display_df.columns = ["Size Range", "Sold", "Avg Price", "Avg €/sqm", "Avg Days"]
                display_df["Avg Price"] = display_df["Avg Price"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["Avg €/sqm"] = display_df["Avg €/sqm"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["Avg Days"] = display_df["Avg Days"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "N/A")
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                # Most popular size
                best_seller = by_size.loc[by_size["sold_count"].idxmax()]
                st.success(f"**Most Popular Size**: {best_seller['size_range']} with {int(best_seller['sold_count'])} sales")
            else:
                st.info("No size sales data available yet.")
        
        st.markdown("---")
        st.markdown("""
        **Note:** Removed listings are properties that were in our database but are no longer available 
        on the market. This typically means they were sold, but could also indicate delisting for other reasons.
        Historical data improves as the system collects more snapshots over time.
        """)


def render_deal_finder_page():
    """Render the deal finder page."""
    st.title("Deal Finder")
    st.markdown("Find properties with price reductions, motivated sellers, and potential bargains")
    
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
    
    # Get motivated seller scores
    with AdvancedInsightsAnalyzer() as analyzer:
        motivated_sellers = analyzer.get_motivated_seller_scores(limit=max_results)
    
    # Stats row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Reductions", f"{stats.get('total_reductions', 0):,}")
    
    with col2:
        st.metric("Avg Reduction", f"{stats.get('avg_reduction_pct', 0):.1f}%")
    
    with col3:
        st.metric("Max Reduction", f"{stats.get('max_reduction_pct', 0):.1f}%")
    
    with col4:
        st.metric("Total Value Reduced", f"€{stats.get('total_value_reduced', 0):,.0f}")
    
    st.markdown("---")
    
    # Tabs for different deal views
    tab1, tab2, tab3 = st.tabs(["🔥 Motivated Sellers", "📉 Price Drops", "💎 Undervalued"])
    
    with tab1:
        st.subheader("Motivated Seller Score")
        st.markdown("""
        Properties ranked by seller motivation based on:
        - **Days on market** (40%) - longer = more motivated
        - **Price reductions** (35%) - reduced prices indicate motivation
        - **Below area average** (25%) - already priced to sell
        """)
        
        if not motivated_sellers.empty:
            display_df = motivated_sellers[["id", "geography", "category", "sq_meters", "price", 
                                           "price_per_sqm", "days_on_market", "motivated_score", 
                                           "motivation_level"]].copy()
            display_df["link"] = display_df["id"].apply(lambda x: f"https://www.spitogatos.gr/aggelia/11{x}")
            display_df = display_df[["id", "link", "geography", "category", "sq_meters", "price", 
                                    "price_per_sqm", "days_on_market", "motivated_score", "motivation_level"]]
            display_df.columns = ["ID", "Link", "Area", "Type", "Size", "Price", "€/sqm", "Days Listed", "Score", "Level"]
            display_df["Price"] = display_df["Price"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
            display_df["€/sqm"] = display_df["€/sqm"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
            
            # Color code by motivation level
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="View"),
                    "Score": st.column_config.ProgressColumn(
                        "Score",
                        min_value=0,
                        max_value=10,
                        format="%.1f"
                    ),
                    "Level": st.column_config.TextColumn("Level")
                }
            )
            
            # Summary stats
            st.markdown("---")
            col1, col2, col3, col4 = st.columns(4)
            levels = motivated_sellers["motivation_level"].value_counts()
            with col1:
                st.metric("Very High", levels.get("Very High", 0))
            with col2:
                st.metric("High", levels.get("High", 0))
            with col3:
                st.metric("Medium", levels.get("Medium", 0))
            with col4:
                st.metric("Low", levels.get("Low", 0))
        else:
            st.info("No data available for motivated seller analysis.")
    
    with tab2:
        st.subheader(f"Properties with Price Reductions (Last {days} Days)")
        render_deals_table(recent_drops)
    
    with tab3:
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
    st.markdown("Data is automatically collected twice daily at 6 AM and 6 PM UTC")
    
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


def render_market_intelligence_page():
    """Render the market intelligence page with advanced insights."""
    st.title("Market Intelligence")
    st.markdown("Advanced market analysis and investment insights")
    
    with AdvancedInsightsAnalyzer() as analyzer:
        # Investment Scores
        st.subheader("🎯 Investment Area Scores")
        st.markdown("Areas ranked by investment potential (value + liquidity + activity)")
        
        investment_df = analyzer.get_investment_area_scores(min_listings=3)
        
        if not investment_df.empty:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Show top investment areas
                display_df = investment_df[["geography", "investment_score", "investment_rating", 
                                           "listing_count", "avg_price_sqm", "avg_dom"]].head(15)
                display_df.columns = ["Area", "Score", "Rating", "Listings", "Avg €/sqm", "Avg DOM"]
                display_df["Avg €/sqm"] = display_df["Avg €/sqm"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
                display_df["Avg DOM"] = display_df["Avg DOM"].apply(lambda x: f"{x:.0f} days" if pd.notna(x) else "N/A")
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            with col2:
                st.markdown("**Rating Breakdown**")
                rating_counts = investment_df["investment_rating"].value_counts()
                for rating, count in rating_counts.items():
                    emoji = {"Excellent": "🌟", "Good": "✅", "Fair": "⚠️", "Avoid": "❌"}.get(rating, "")
                    st.write(f"{emoji} {rating}: {count} areas")
        else:
            st.info("Not enough data for investment analysis.")
        
        st.markdown("---")
        
        # Market Demand Analysis
        st.subheader("🔥 What The Market Wants")
        st.markdown("Identify high-demand attributes by analyzing what sells fastest")
        
        # Summary cards
        demand_summary = analyzer.get_market_demand_summary()
        
        if demand_summary:
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                if "best_size" in demand_summary:
                    st.metric("Best Size", demand_summary["best_size"]["range"])
                    st.caption(f"Avg {demand_summary['best_size']['avg_dom']:.0f} days")
            
            with col2:
                if "best_floor" in demand_summary:
                    st.metric("Best Floor", demand_summary["best_floor"]["level"])
                    st.caption(f"Avg {demand_summary['best_floor']['avg_dom']:.0f} days")
            
            with col3:
                if "best_price_range" in demand_summary:
                    st.metric("Best Price Range", demand_summary["best_price_range"]["range"])
                    st.caption(f"Avg {demand_summary['best_price_range']['avg_dom']:.0f} days")
            
            with col4:
                if "best_rooms" in demand_summary:
                    st.metric("Best Room Count", demand_summary["best_rooms"]["count"])
                    st.caption(f"Avg {demand_summary['best_rooms']['avg_dom']:.0f} days")
            
            with col5:
                if "top_areas" in demand_summary and demand_summary["top_areas"]:
                    st.metric("Top Area", demand_summary["top_areas"][0]["geography"][:15])
                    st.caption(f"Score: {demand_summary['top_areas'][0]['demand_score']}")
        
        # Detailed tabs
        demand_tab1, demand_tab2, demand_tab3, demand_tab4, demand_tab5 = st.tabs([
            "📍 By Area", "📐 By Size", "🏢 By Floor", "💰 By Price", "🚪 By Rooms"
        ])
        
        with demand_tab1:
            high_demand_areas = analyzer.get_high_demand_areas(min_listings=3)
            if not high_demand_areas.empty:
                import plotly.express as px
                
                fig = px.bar(
                    high_demand_areas.head(15),
                    x="geography",
                    y="demand_score",
                    color="demand_score",
                    color_continuous_scale="RdYlGn",
                    title="Demand Score by Area (Higher = More Demand)"
                )
                fig.update_layout(xaxis_tickangle=-45, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
                
                display_df = high_demand_areas[["geography", "demand_score", "demand_level", 
                                               "total_listings", "avg_dom", "reduction_rate"]].head(15)
                display_df.columns = ["Area", "Demand Score", "Level", "Listings", "Avg DOM", "Reduction %"]
                display_df["Avg DOM"] = display_df["Avg DOM"].apply(lambda x: f"{x:.0f} days" if pd.notna(x) else "N/A")
                display_df["Reduction %"] = display_df["Reduction %"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("Not enough area data for demand analysis.")
        
        with demand_tab2:
            size_demand = analyzer.get_demand_by_size_range()
            if not size_demand.empty:
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    import plotly.express as px
                    fig = px.bar(
                        size_demand,
                        x="size_range",
                        y="avg_dom",
                        color="demand_indicator",
                        title="Avg Days on Market by Size (Lower = Higher Demand)",
                        color_discrete_map={"🔥 High": "#2ecc71", "📈 Good": "#f1c40f", "📉 Low": "#e74c3c"}
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("**Size Demand Analysis**")
                    for _, row in size_demand.iterrows():
                        st.write(f"{row['demand_indicator']} **{row['size_range']}**")
                        st.caption(f"DOM: {row['avg_dom']:.0f}d | €{row['avg_price_sqm']:,.0f}/sqm")
            else:
                st.info("Not enough data for size analysis.")
        
        with demand_tab3:
            floor_demand = analyzer.get_demand_by_floor()
            if not floor_demand.empty:
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    import plotly.express as px
                    fig = px.bar(
                        floor_demand,
                        x="floor_category",
                        y="avg_dom",
                        color="demand_indicator",
                        title="Avg Days on Market by Floor (Lower = Higher Demand)",
                        color_discrete_map={"🔥 High": "#2ecc71", "📈 Good": "#f1c40f", "📉 Low": "#e74c3c"}
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("**Floor Demand Analysis**")
                    for _, row in floor_demand.iterrows():
                        st.write(f"{row['demand_indicator']} **{row['floor_category']}**")
                        st.caption(f"DOM: {row['avg_dom']:.0f}d | €{row['avg_price_sqm']:,.0f}/sqm")
            else:
                st.info("Not enough data for floor analysis.")
        
        with demand_tab4:
            price_demand = analyzer.get_demand_by_price_range()
            if not price_demand.empty:
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    import plotly.express as px
                    fig = px.bar(
                        price_demand,
                        x="price_range",
                        y="avg_dom",
                        color="demand_indicator",
                        title="Avg Days on Market by Price Range",
                        color_discrete_map={"🔥 High": "#2ecc71", "📈 Good": "#f1c40f", "📉 Low": "#e74c3c"}
                    )
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("**Price Range Demand**")
                    for _, row in price_demand.iterrows():
                        st.write(f"{row['demand_indicator']} **{row['price_range']}**")
                        st.caption(f"DOM: {row['avg_dom']:.0f}d | {row['listings']} listings")
            else:
                st.info("Not enough data for price analysis.")
        
        with demand_tab5:
            rooms_demand = analyzer.get_demand_by_rooms()
            if not rooms_demand.empty:
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    import plotly.express as px
                    fig = px.bar(
                        rooms_demand,
                        x="room_count",
                        y="avg_dom",
                        color="demand_indicator",
                        title="Avg Days on Market by Room Count",
                        color_discrete_map={"🔥 High": "#2ecc71", "📈 Good": "#f1c40f", "📉 Low": "#e74c3c"}
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("**Room Count Demand**")
                    for _, row in rooms_demand.iterrows():
                        st.write(f"{row['demand_indicator']} **{row['room_count']}**")
                        st.caption(f"DOM: {row['avg_dom']:.0f}d | Avg €{row['avg_price']:,.0f}")
            else:
                st.info("Not enough data for room analysis.")
        
        st.markdown("""
        **How to read this:**
        - 🔥 **High Demand**: Sells in <40 days with <20% price reductions
        - 📈 **Good Demand**: Sells in 40-60 days
        - 📉 **Low Demand**: Takes >60 days to sell
        
        *Lower days on market (DOM) indicates higher buyer demand for that attribute.*
        """)
        
        st.markdown("---")
        
        # Price Benchmarks
        st.subheader("📊 Price Benchmarks by Area")
        st.markdown("Fair price ranges for each neighborhood")
        
        benchmarks_df = analyzer.get_price_benchmarks_by_area(min_listings=3)
        
        if not benchmarks_df.empty:
            display_df = benchmarks_df[["geography", "listing_count", "avg_price_sqm", 
                                       "fair_price_low", "fair_price_high"]].head(20)
            display_df.columns = ["Area", "Listings", "Avg €/sqm", "Fair Low", "Fair High"]
            for col in ["Avg €/sqm", "Fair Low", "Fair High"]:
                display_df[col] = display_df[col].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("Not enough data for price benchmarks.")
        
        st.markdown("---")
        
        # Underpriced Properties
        st.subheader("💰 Underpriced Properties")
        st.markdown("Properties significantly below area average")
        
        underpriced_df = analyzer.get_underpriced_properties(threshold_pct=15, limit=20)
        
        if not underpriced_df.empty:
            display_df = underpriced_df[["id", "geography", "category", "sq_meters", "price", 
                                        "price_per_sqm", "area_avg_price_sqm", "discount_pct"]].copy()
            display_df["link"] = display_df["id"].apply(lambda x: f"https://www.spitogatos.gr/aggelia/11{x}")
            display_df = display_df[["id", "link", "geography", "category", "sq_meters", "price", 
                                    "price_per_sqm", "area_avg_price_sqm", "discount_pct"]]
            display_df.columns = ["ID", "Link", "Area", "Type", "Size", "Price", "€/sqm", "Area Avg", "Discount %"]
            display_df["Price"] = display_df["Price"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
            display_df["€/sqm"] = display_df["€/sqm"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
            display_df["Area Avg"] = display_df["Area Avg"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
            display_df["Discount %"] = display_df["Discount %"].apply(lambda x: f"-{x:.1f}%" if pd.notna(x) else "N/A")
            st.dataframe(
                display_df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="View")
                }
            )
        else:
            st.info("No underpriced properties found.")
        
        st.markdown("---")
        
        # Market Speed by Area
        st.subheader("⚡ Market Speed by Area")
        st.markdown("How fast properties sell in each area")
        
        dom_df = analyzer.get_dom_by_area(min_listings=3)
        
        if not dom_df.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Fastest Markets (Hot)**")
                fast = dom_df[dom_df["market_speed"] == "Hot"].head(10)
                if not fast.empty:
                    for _, row in fast.iterrows():
                        st.write(f"🔥 {row['geography']}: {row['avg_days_on_market']:.0f} days avg")
                else:
                    st.write("No hot markets found")
            
            with col2:
                st.markdown("**Slowest Markets**")
                slow = dom_df[dom_df["market_speed"].isin(["Slow", "Very Slow"])].head(10)
                if not slow.empty:
                    for _, row in slow.iterrows():
                        st.write(f"🐌 {row['geography']}: {row['avg_days_on_market']:.0f} days avg")
                else:
                    st.write("No slow markets found")
        else:
            st.info("Not enough data for market speed analysis.")
        
        st.markdown("---")
        
        # Listing Type Analysis
        st.subheader("📋 Listing Type Analysis")
        st.markdown("VIP vs Featured vs Standard listings comparison")
        
        listing_df = analyzer.get_listing_type_analysis()
        
        if not listing_df.empty:
            col1, col2, col3 = st.columns(3)
            
            for i, (_, row) in enumerate(listing_df.iterrows()):
                col = [col1, col2, col3][i % 3]
                with col:
                    lt = row["listing_type"].upper() if row["listing_type"] else "STANDARD"
                    st.metric(lt, f"{row['listing_count']:,} listings")
                    st.caption(f"Avg Price: €{row['avg_price']:,.0f}")
                    st.caption(f"Avg €/sqm: €{row['avg_price_sqm']:,.0f}" if pd.notna(row['avg_price_sqm']) else "")
                    st.caption(f"Reduction Rate: {row['reduction_rate']:.1f}%")
        else:
            st.info("No listing type data available.")


def render_property_insights_page():
    """Render property insights page with floor and size analysis."""
    st.title("Property Insights")
    st.markdown("Detailed analysis of property characteristics and pricing")
    
    with AdvancedInsightsAnalyzer() as analyzer:
        # Floor Premium Analysis
        st.subheader("🏢 Floor Premium Analysis")
        st.markdown("How does floor level affect price?")
        
        floor_df = analyzer.get_floor_premium_summary()
        
        if not floor_df.empty:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Bar chart
                import plotly.express as px
                fig = px.bar(
                    floor_df, 
                    x="floor_category", 
                    y="avg_price_sqm",
                    title="Average Price per sqm by Floor Level",
                    labels={"floor_category": "Floor Level", "avg_price_sqm": "Avg €/sqm"}
                )
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown("**Statistics**")
                for _, row in floor_df.iterrows():
                    st.write(f"**{row['floor_category']}**")
                    st.caption(f"{row['listing_count']} listings, €{row['avg_price_sqm']:,.0f}/sqm")
        else:
            st.info("No floor data available.")
        
        st.markdown("---")
        
        # Size Efficiency Analysis
        st.subheader("📐 Size vs Price Analysis")
        st.markdown("How does property size affect price per sqm?")
        
        size_df = analyzer.get_size_efficiency_analysis()
        
        if not size_df.empty:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                import plotly.express as px
                fig = px.bar(
                    size_df,
                    x="size_category",
                    y="avg_price_sqm",
                    title="Price per sqm by Property Size",
                    labels={"size_category": "Size Category", "avg_price_sqm": "Avg €/sqm"}
                )
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown("**Key Finding**")
                if len(size_df) >= 2:
                    smallest = size_df.iloc[0]
                    largest = size_df.iloc[-1]
                    if smallest["avg_price_sqm"] > largest["avg_price_sqm"]:
                        premium = ((smallest["avg_price_sqm"] / largest["avg_price_sqm"]) - 1) * 100
                        st.info(f"Smaller properties have a **{premium:.0f}% premium** per sqm compared to larger ones.")
                    else:
                        st.info("Larger properties have similar or higher price per sqm.")
                
                st.markdown("**By Size**")
                for _, row in size_df.iterrows():
                    st.write(f"**{row['size_category']}**")
                    st.caption(f"{row['listing_count']} listings, €{row['avg_price_sqm']:,.0f}/sqm")
        else:
            st.info("No size data available.")
        
        st.markdown("---")
        
        # Detailed Floor Analysis
        st.subheader("📈 Detailed Floor Premium")
        
        floor_detail = analyzer.get_floor_premium_analysis()
        
        if not floor_detail.empty and len(floor_detail) > 1:
            import plotly.express as px
            fig = px.scatter(
                floor_detail,
                x="floor_number",
                y="avg_price_sqm",
                size="listing_count",
                title="Price per sqm by Floor Number",
                labels={"floor_number": "Floor", "avg_price_sqm": "Avg €/sqm", "listing_count": "Listings"},
                hover_data=["listing_count", "premium_vs_ground_pct"]
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Show premium percentages
            if "premium_vs_ground_pct" in floor_detail.columns:
                st.markdown("**Floor Premiums vs Ground Floor**")
                premiums = floor_detail[floor_detail["floor_number"] > 0].sort_values("floor_number")
                for _, row in premiums.head(10).iterrows():
                    premium = row["premium_vs_ground_pct"]
                    arrow = "📈" if premium > 0 else "📉" if premium < 0 else "➡️"
                    st.write(f"Floor {int(row['floor_number'])}: {arrow} {premium:+.1f}%")
        else:
            st.info("Not enough floor data for detailed analysis.")
        
        st.markdown("---")
        
        # Stale Listings
        st.subheader("⏰ Stale Listings (60+ Days)")
        st.markdown("Properties on market for a long time - potential negotiation opportunities")
        
        stale_df = analyzer.get_stale_listings(min_days=60, limit=20)
        
        if not stale_df.empty:
            display_df = stale_df[["id", "geography", "category", "sq_meters", "price", 
                                  "price_per_sqm", "days_on_market", "agency_name"]].copy()
            display_df["link"] = display_df["id"].apply(lambda x: f"https://www.spitogatos.gr/aggelia/11{x}")
            display_df = display_df[["id", "link", "geography", "category", "sq_meters", "price", 
                                    "price_per_sqm", "days_on_market", "agency_name"]]
            display_df.columns = ["ID", "Link", "Area", "Type", "Size", "Price", "€/sqm", "Days Listed", "Agent"]
            display_df["Price"] = display_df["Price"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
            display_df["€/sqm"] = display_df["€/sqm"].apply(lambda x: f"€{x:,.0f}" if pd.notna(x) else "N/A")
            display_df["Agent"] = display_df["Agent"].apply(lambda x: x[:20] + "..." if x and len(str(x)) > 20 else x)
            st.dataframe(
                display_df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Link": st.column_config.LinkColumn("Link", display_text="View")
                }
            )
        else:
            st.info("No stale listings found (all properties listed < 60 days).")


def main():
    """Main application entry point."""
    try:
        # Initialize database
        init_db()
        
        # Render sidebar and get selected page
        page = render_sidebar()
        
        # Render selected page
        if page == "Investor Dashboard":
            render_investor_dashboard()
        elif page == "Deal Finder":
            render_deal_finder_page()
        elif page == "Market History":
            render_market_history_page()
        elif page == "Market Intelligence":
            render_market_intelligence_page()
        elif page == "Property Insights":
            render_property_insights_page()
        elif page == "Area Analysis":
            render_area_analysis_page()
        elif page == "Agent Insights":
            render_agent_insights_page()
        elif page == "Data Collection":
            render_data_collection_page()
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        import traceback
        st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
