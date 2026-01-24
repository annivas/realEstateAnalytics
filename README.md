# Real Estate Analytics Engine

A Python-based analytics platform for tracking real estate market trends from spitogatos.gr. Features automated data collection, comprehensive market analysis, and an interactive Streamlit dashboard.

## Features

- **Automated Data Collection**: Scheduled fetching from spitogatos.gr API with rate limiting
- **Historical Price Tracking**: Track price changes over time for every property
- **Market Analytics**:
  - Price trends (avg/median price per sqm over time)
  - Inventory analysis (listing counts, days on market)
  - Price reduction tracking (find deals and opportunities)
  - Area comparisons (neighborhood heatmaps and rankings)
  - Agent analysis (agency performance and market share)
- **Interactive Dashboard**: Streamlit-based web interface with charts and maps

## Quick Start

### 1. Install Dependencies

```bash
cd realEstateAnalytics
pip install -r requirements.txt
```

### 2. Initialize Database

```bash
python scripts/init_db.py
```

### 3. Collect Initial Data

```bash
python scripts/run_collection.py
```

### 4. Launch Dashboard

```bash
streamlit run dashboard/app.py
```

The dashboard will open at `http://localhost:8501`

## Project Structure

```
realEstateAnalytics/
├── config.py                 # Configuration settings
├── requirements.txt          # Python dependencies
├── README.md                 # This file
│
├── database/
│   ├── models.py            # SQLAlchemy database models
│   └── schema.sql           # SQL schema reference
│
├── collector/
│   ├── api_client.py        # Spitogatos API client
│   └── scheduler.py         # Automated collection scheduler
│
├── analytics/
│   ├── price_trends.py      # Price trend analysis
│   ├── inventory.py         # Inventory/listing analysis
│   ├── price_reductions.py  # Deal finder & price drops
│   ├── area_analysis.py     # Geographic comparisons
│   └── agent_analysis.py    # Agent/agency metrics
│
├── dashboard/
│   ├── app.py               # Main Streamlit application
│   └── components/          # Reusable UI components
│
├── scripts/
│   ├── init_db.py           # Database initialization
│   └── run_collection.py    # Manual data collection
│
└── data/
    └── real_estate.db       # SQLite database (auto-created)
```

## Configuration

Edit `config.py` to customize:

### Monitored Areas

```python
MONITORED_AREAS = {
    2121: "Filothei",
    2124: "Psychiko",
    # Add more area IDs...
}
```

To find area IDs, search on spitogatos.gr and check the URL parameters.

### Collection Schedule

```python
COLLECTION_SCHEDULE = {
    "hour": 6,           # Run at 6 AM
    "minute": 0,
    "day_of_week": "*",  # Every day
}
```

### Rate Limiting

```python
REQUEST_DELAY_SECONDS = 1.0  # Delay between API requests
MAX_RETRIES = 3
```

## Usage

### Manual Data Collection

```bash
python scripts/run_collection.py
```

### Scheduled Collection

Run the scheduler as a background process:

```bash
python collector/scheduler.py
```

Options:
- `--hour 8` - Run at 8 AM
- `--minute 30` - Run at XX:30
- `--days mon-fri` - Weekdays only
- `--run-now` - Collect immediately on start

Example with cron (Linux/Mac):

```bash
# Run daily at 6 AM
0 6 * * * cd /path/to/realEstateAnalytics && python scripts/run_collection.py
```

### Dashboard

```bash
streamlit run dashboard/app.py
```

Dashboard pages:
- **Overview**: Key metrics and market summary
- **Price Trends**: Historical price analysis with charts
- **Deal Finder**: Properties with price reductions
- **Area Analysis**: Neighborhood comparisons and heatmaps
- **Agent Insights**: Agency performance metrics
- **Data Collection**: Collection history and status

## Analytics API

You can also use the analytics modules programmatically:

```python
from analytics import PriceTrendsAnalyzer, AreaAnalyzer

# Price trends
with PriceTrendsAnalyzer() as analyzer:
    trends = analyzer.get_price_per_sqm_trends(days=90)
    print(trends)

# Area comparison
with AreaAnalyzer() as analyzer:
    areas = analyzer.get_area_summary()
    print(areas)
```

## Database Schema

- **properties**: Core property data (location, size, features)
- **property_snapshots**: Historical price records
- **agents**: Real estate agent/agency info
- **areas**: Geographic areas being monitored
- **collection_runs**: Data collection job history

## Notes

- Data is stored in SQLite for simplicity (no separate database server needed)
- The API client respects rate limits to avoid overloading the source
- Historical data accumulates over time for better trend analysis
- Collect data regularly (daily/weekly) for meaningful insights

## License

For personal/educational use only. Please respect the terms of service of any data sources.
