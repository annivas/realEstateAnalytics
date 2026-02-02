"""
Analytics module for real estate market analysis.
"""
from .price_trends import PriceTrendsAnalyzer
from .inventory import InventoryAnalyzer
from .price_reductions import PriceReductionAnalyzer
from .area_analysis import AreaAnalyzer
from .agent_analysis import AgentAnalyzer
from .advanced_insights import AdvancedInsightsAnalyzer
from .investor_tools import InvestorAnalyzer
from .watchlist import WatchlistAnalyzer
from .price_prediction import PricePredictionAnalyzer
from .alerts import AlertManager

__all__ = [
    "PriceTrendsAnalyzer",
    "InventoryAnalyzer",
    "PriceReductionAnalyzer",
    "AreaAnalyzer",
    "AgentAnalyzer",
    "AdvancedInsightsAnalyzer",
    "InvestorAnalyzer",
    "WatchlistAnalyzer",
    "PricePredictionAnalyzer",
    "AlertManager",
]
