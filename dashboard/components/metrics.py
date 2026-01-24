"""
Metric card components for the dashboard.
"""
import streamlit as st
from typing import Optional, Union


def render_metric_cards(metrics: dict, columns: int = 4):
    """
    Render a row of metric cards.
    
    Args:
        metrics: Dictionary with metric name -> value pairs
                 Can also include delta values as tuples: (value, delta)
        columns: Number of columns in the row
    """
    cols = st.columns(columns)
    
    for i, (label, value) in enumerate(metrics.items()):
        col_idx = i % columns
        
        with cols[col_idx]:
            if isinstance(value, tuple):
                # Value with delta
                main_value, delta = value
                st.metric(label=label, value=format_metric_value(main_value), delta=delta)
            else:
                st.metric(label=label, value=format_metric_value(value))


def format_metric_value(value: Union[int, float, str]) -> str:
    """Format a metric value for display."""
    if isinstance(value, str):
        return value
    
    if isinstance(value, float):
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        elif abs(value) >= 1_000:
            return f"{value / 1_000:.1f}K"
        elif abs(value) < 1:
            return f"{value:.2f}"
        else:
            return f"{value:,.0f}"
    
    if isinstance(value, int):
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        elif abs(value) >= 1_000:
            return f"{value / 1_000:.1f}K"
        else:
            return f"{value:,}"
    
    return str(value)


def render_stat_box(title: str, value: str, subtitle: Optional[str] = None, color: str = "blue"):
    """
    Render a styled stat box.
    
    Args:
        title: Box title
        value: Main value to display
        subtitle: Optional subtitle
        color: Color theme (blue, green, red, orange)
    """
    color_map = {
        "blue": "#1f77b4",
        "green": "#2ca02c",
        "red": "#d62728",
        "orange": "#ff7f0e",
    }
    
    bg_color = color_map.get(color, color_map["blue"])
    
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, {bg_color}22 0%, {bg_color}11 100%);
        border-left: 4px solid {bg_color};
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    ">
        <div style="color: #666; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em;">
            {title}
        </div>
        <div style="font-size: 1.8rem; font-weight: 600; color: #333;">
            {value}
        </div>
        {f'<div style="color: #888; font-size: 0.85rem;">{subtitle}</div>' if subtitle else ''}
    </div>
    """, unsafe_allow_html=True)
