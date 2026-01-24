"""
Map components for the dashboard.
"""
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.express as px


def render_property_map(
    df: pd.DataFrame,
    color_by: str = "price_per_sqm",
    center_lat: float = None,
    center_lng: float = None,
    zoom: int = 12,
):
    """
    Render an interactive property map using Folium.
    
    Args:
        df: DataFrame with latitude, longitude, and property data
        color_by: Column to use for marker colors
        center_lat: Map center latitude
        center_lng: Map center longitude
        zoom: Initial zoom level
    """
    if df.empty:
        st.info("No location data available for map.")
        return
    
    # Filter out invalid coordinates
    df = df.dropna(subset=["latitude", "longitude"])
    
    if df.empty:
        st.info("No valid coordinates found.")
        return
    
    # Calculate center if not provided
    if center_lat is None:
        center_lat = df["latitude"].mean()
    if center_lng is None:
        center_lng = df["longitude"].mean()
    
    # Create map
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=zoom,
        tiles="cartodbpositron",
    )
    
    # Color scale based on price per sqm
    if color_by in df.columns and df[color_by].notna().any():
        min_val = df[color_by].min()
        max_val = df[color_by].max()
        
        def get_color(val):
            if pd.isna(val):
                return "#808080"
            normalized = (val - min_val) / (max_val - min_val) if max_val > min_val else 0.5
            # Blue to Red gradient
            r = int(255 * normalized)
            b = int(255 * (1 - normalized))
            return f"#{r:02x}40{b:02x}"
    else:
        def get_color(val):
            return "#1f77b4"
    
    # Add markers
    for _, row in df.iterrows():
        color = get_color(row.get(color_by))
        
        # Build popup content
        popup_html = f"""
        <div style="width: 200px;">
            <b>{row.get('category', 'Property').title()}</b><br>
            <b>Price:</b> EUR {row.get('price', 0):,.0f}<br>
            <b>Size:</b> {row.get('sq_meters', 'N/A')} sqm<br>
            <b>Price/sqm:</b> EUR {row.get('price_per_sqm', 0):,.0f}<br>
            <b>Area:</b> {row.get('geography', 'N/A')}
        </div>
        """
        
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=8,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=250),
        ).add_to(m)
    
    # Add legend
    legend_html = f"""
    <div style="
        position: fixed;
        bottom: 50px;
        left: 50px;
        z-index: 1000;
        background: white;
        padding: 10px;
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        font-size: 12px;
    ">
        <b>Price per sqm</b><br>
        <span style="color: #0040ff;">Low</span> -
        <span style="color: #ff4000;">High</span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Render map
    st_folium(m, width=None, height=500, use_container_width=True)


def render_area_heatmap(df: pd.DataFrame):
    """
    Render an area price heatmap using Plotly.
    
    Args:
        df: DataFrame with area statistics including coordinates
    """
    if df.empty or "center_lat" not in df.columns:
        st.info("No area coordinate data available for heatmap.")
        return
    
    # Filter out invalid coordinates
    df = df.dropna(subset=["center_lat", "center_lng"])
    
    if df.empty:
        st.info("No valid area coordinates found.")
        return
    
    fig = px.scatter_mapbox(
        df,
        lat="center_lat",
        lon="center_lng",
        color="avg_price_per_sqm",
        size="listing_count",
        hover_name="geography",
        hover_data={
            "avg_price_per_sqm": ":,.0f",
            "listing_count": True,
            "avg_price": ":,.0f",
        },
        color_continuous_scale="RdYlBu_r",
        size_max=30,
        zoom=11,
        title="Area Price Heatmap",
    )
    
    fig.update_layout(
        mapbox_style="carto-positron",
        height=600,
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_simple_scatter_map(df: pd.DataFrame, color_col: str = "price"):
    """
    Render a simple scatter map using Plotly (no folium dependency needed).
    
    Args:
        df: DataFrame with latitude, longitude columns
        color_col: Column to use for coloring points
    """
    if df.empty:
        st.info("No location data available.")
        return
    
    df = df.dropna(subset=["latitude", "longitude"])
    
    if df.empty:
        st.info("No valid coordinates found.")
        return
    
    fig = px.scatter_mapbox(
        df,
        lat="latitude",
        lon="longitude",
        color=color_col if color_col in df.columns else None,
        hover_name="geography" if "geography" in df.columns else None,
        hover_data={
            "price": ":,.0f" if "price" in df.columns else False,
            "sq_meters": True if "sq_meters" in df.columns else False,
            "price_per_sqm": ":,.0f" if "price_per_sqm" in df.columns else False,
        },
        color_continuous_scale="Viridis",
        zoom=11,
        height=500,
    )
    
    fig.update_layout(
        mapbox_style="carto-positron",
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
    )
    
    st.plotly_chart(fig, use_container_width=True)
