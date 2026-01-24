"""
Configuration settings for the Real Estate Analytics Engine.
"""
import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "real_estate.db"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# API Configuration
API_BASE_URL = "https://www.spitogatos.gr/n_api/v1"
API_ENDPOINTS = {
    "search_results_map": "/properties/search-results-map",
}

# Default search parameters
DEFAULT_LISTING_TYPE = "sale"
DEFAULT_CATEGORY = "residential"
DEFAULT_SORT_BY = "rankingscore"
DEFAULT_SORT_ORDER = "desc"
DEFAULT_PAGE_SIZE = 100  # Number of results per page

# Areas to monitor (area IDs from spitogatos.gr)
# 105103 is a larger area covering more of Athens
MONITORED_AREAS = {
    105103: "Athens Region",
    # Smaller area examples:
    # 2121: "Filothei",
    # 2124: "Psychiko",
}

# Rate limiting
REQUEST_DELAY_SECONDS = 1.0  # Delay between API requests
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5.0

# Scheduler settings
COLLECTION_SCHEDULE = {
    "hour": 6,      # Run at 6 AM
    "minute": 0,
    "day_of_week": "*",  # Every day (* = all days, "mon-fri" for weekdays only)
}

# Database settings
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Property categories mapping
PROPERTY_CATEGORIES = {
    "house": "House",
    "apartment": "Apartment",
    "maisonette": "Maisonette",
    "studio": "Studio",
    "loft": "Loft",
    "penthouse": "Penthouse",
}

# Property subtypes mapping
PROPERTY_SUBTYPES = {
    1: "Detached",
    2: "Semi-detached",
    3: "Terraced",
    4: "Villa",
    5: "Bungalow",
}

# Ad types for quality scoring
AD_TYPES = {
    "vip": 3,      # Premium listing
    "featured": 2,  # Featured listing
    "standard": 1,  # Standard listing
}
