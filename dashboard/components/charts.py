"""
Chart components for the dashboard.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


def render_price_trend_chart(df: pd.DataFrame, title: str = "Price Trends Over Time"):
    """
    Render a price trend line chart.
    
    Args:
        df: DataFrame with 'date', 'avg_price_per_sqm', and optionally 'median_price_per_sqm'
        title: Chart title
    """
    if df.empty:
        st.info("No price trend data available yet. Collect more data to see trends.")
        return
    
    fig = go.Figure()
    
    # Average line
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["avg_price_per_sqm"],
        mode="lines+markers",
        name="Average",
        line=dict(color="#1f77b4", width=2),
        marker=dict(size=6),
    ))
    
    # Median line if available
    if "median_price_per_sqm" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["median_price_per_sqm"],
            mode="lines+markers",
            name="Median",
            line=dict(color="#2ca02c", width=2, dash="dash"),
            marker=dict(size=6),
        ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Price per sqm (EUR)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_white",
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_inventory_chart(df: pd.DataFrame, title: str = "New Listings Over Time"):
    """
    Render an inventory/new listings bar chart.
    
    Args:
        df: DataFrame with 'date' and 'new_listings' columns
        title: Chart title
    """
    if df.empty:
        st.info("No inventory data available yet.")
        return
    
    fig = px.bar(
        df,
        x="date",
        y="new_listings",
        title=title,
        color_discrete_sequence=["#1f77b4"],
    )
    
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Number of Listings",
        template="plotly_white",
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_price_distribution(df: pd.DataFrame, column: str = "price", title: str = "Price Distribution"):
    """
    Render a price distribution histogram.
    
    Args:
        df: DataFrame with price data
        column: Column to plot
        title: Chart title
    """
    if df.empty or column not in df.columns:
        st.info("No data available for distribution chart.")
        return
    
    fig = px.histogram(
        df,
        x=column,
        nbins=30,
        title=title,
        color_discrete_sequence=["#1f77b4"],
    )
    
    # Add mean and median lines
    mean_val = df[column].mean()
    median_val = df[column].median()
    
    fig.add_vline(x=mean_val, line_dash="dash", line_color="red",
                  annotation_text=f"Mean: {mean_val:,.0f}")
    fig.add_vline(x=median_val, line_dash="dash", line_color="green",
                  annotation_text=f"Median: {median_val:,.0f}")
    
    fig.update_layout(
        xaxis_title=column.replace("_", " ").title(),
        yaxis_title="Count",
        template="plotly_white",
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_area_comparison(df: pd.DataFrame, metric: str = "avg_price_per_sqm"):
    """
    Render an area comparison bar chart.
    
    Args:
        df: DataFrame with area statistics
        metric: Metric to compare
    """
    if df.empty:
        st.info("No area comparison data available.")
        return
    
    # Sort by metric and take top 15
    df_sorted = df.nlargest(15, metric)
    
    fig = px.bar(
        df_sorted,
        y="geography",
        x=metric,
        orientation="h",
        title=f"Areas by {metric.replace('_', ' ').title()}",
        color=metric,
        color_continuous_scale="Blues",
    )
    
    fig.update_layout(
        xaxis_title=metric.replace("_", " ").title(),
        yaxis_title="Area",
        template="plotly_white",
        height=max(400, len(df_sorted) * 30),
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_category_pie_chart(df: pd.DataFrame):
    """
    Render a property category pie chart.
    
    Args:
        df: DataFrame with 'category' and 'count' columns
    """
    if df.empty:
        st.info("No category data available.")
        return
    
    fig = px.pie(
        df,
        values="count",
        names="category",
        title="Property Categories",
        color_discrete_sequence=px.colors.qualitative.Set3,
    )
    
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(template="plotly_white")
    
    st.plotly_chart(fig, use_container_width=True)


def render_days_on_market_chart(df: pd.DataFrame):
    """
    Render a days on market distribution chart.
    
    Args:
        df: DataFrame with 'dom_bucket' and 'count' columns
    """
    if df.empty:
        st.info("No days on market data available.")
        return
    
    fig = px.bar(
        df,
        x="dom_bucket",
        y="count",
        title="Days on Market Distribution",
        color="count",
        color_continuous_scale="Oranges",
    )
    
    fig.update_layout(
        xaxis_title="Days on Market",
        yaxis_title="Number of Listings",
        template="plotly_white",
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_agent_comparison_chart(df: pd.DataFrame, metric: str = "listing_count"):
    """
    Render an agent comparison bar chart.
    
    Args:
        df: DataFrame with agent statistics
        metric: Metric to compare
    """
    if df.empty:
        st.info("No agent data available.")
        return
    
    # Use agency name, fall back to agent_id
    df = df.copy()
    df["display_name"] = df["agency_name"].fillna(df["agent_id"].astype(str))
    
    fig = px.bar(
        df.head(15),
        y="display_name",
        x=metric,
        orientation="h",
        title=f"Top Agents by {metric.replace('_', ' ').title()}",
        color=metric,
        color_continuous_scale="Greens",
    )
    
    fig.update_layout(
        xaxis_title=metric.replace("_", " ").title(),
        yaxis_title="Agent/Agency",
        template="plotly_white",
        height=max(400, min(len(df), 15) * 30),
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_price_change_scatter(df: pd.DataFrame):
    """
    Render a scatter plot of price changes.
    
    Args:
        df: DataFrame with price change data
    """
    if df.empty:
        st.info("No price change data available.")
        return
    
    fig = px.scatter(
        df,
        x="prev_price",
        y="price",
        color="change_type",
        size=abs(df["price_change"]),
        hover_data=["geography", "change_pct"],
        title="Price Changes",
        color_discrete_map={"increase": "#d62728", "decrease": "#2ca02c"},
    )
    
    # Add diagonal reference line
    max_price = max(df["prev_price"].max(), df["price"].max())
    fig.add_trace(go.Scatter(
        x=[0, max_price],
        y=[0, max_price],
        mode="lines",
        name="No Change",
        line=dict(color="gray", dash="dash"),
    ))
    
    fig.update_layout(
        xaxis_title="Previous Price (EUR)",
        yaxis_title="Current Price (EUR)",
        template="plotly_white",
    )
    
    st.plotly_chart(fig, use_container_width=True)
