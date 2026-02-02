"""
Analytics module for real estate market analysis.
"""
from .price_trends import PriceTrendsAnalyzer
from .inventory import InventoryAnalyzer
from .price_reductions import PriceReductionAnalyzer
from .area_analysis import AreaAnalyzer
from .agent_analysis import AgentAnalyzer
from .property_insights import (
    PropertyInsightsAnalyzer,
    PropertyInsight,
    get_property_insights,
    print_insights,
)

__all__ = [
    "PriceTrendsAnalyzer",
    "InventoryAnalyzer",
    "PriceReductionAnalyzer",
    "AreaAnalyzer",
    "AgentAnalyzer",
    "PropertyInsightsAnalyzer",
    "PropertyInsight",
    "get_property_insights",
    "print_insights",
]
