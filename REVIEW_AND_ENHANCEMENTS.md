# Real Estate Analytics Engine - Code Review & Enhancement Plan

**Review Date:** 2026-02-02
**Reviewer:** Claude Code Review

---

## Executive Summary

This is a well-architected real estate analytics platform for the Greek market with:
- Automated daily data collection via GitHub Actions
- SQLite database with historical price tracking
- 7 specialized analytics modules
- Interactive Streamlit dashboard
- Investment-focused tools (ROI calculator, deal finder, market signals)

The codebase is **production-ready** with some **minor issues** to address and significant **enhancement opportunities**.

---

## Part 1: Implementation Issues Found

### Critical Issues

None found. The core logic is sound and the system appears to be functioning correctly based on the daily data commits.

### Medium Severity Issues

#### Issue 1: Duplicate Rows in Analytics Queries

**Location:** Multiple analytics modules
**Description:** Many SQL queries join `properties` with `property_snapshots` without filtering to the latest snapshot per property.

**Example (advanced_insights.py:387-401):**
```python
query = """
    SELECT p.geography, COUNT(*) as listing_count, ...
    FROM properties p
    JOIN property_snapshots ps ON p.id = ps.property_id
    WHERE p.is_active = 1 ...
    GROUP BY p.geography
"""
```

**Impact:** A property with 10 snapshots gets counted 10 times, inflating listing counts and skewing averages.

**Fix:** Use a subquery to get only the latest snapshot:
```python
latest_snapshot = """
    SELECT property_id, MAX(collected_at) as max_date
    FROM property_snapshots
    GROUP BY property_id
"""
# Then join on both property_id AND max_date
```

**Files affected:**
- `analytics/advanced_insights.py` (multiple methods)
- `analytics/price_reductions.py:get_price_reduction_stats()`
- `analytics/investor_tools.py` (multiple methods)

---

#### Issue 2: Inconsistent Snapshot Handling

**Location:** Analytics modules
**Description:** Some modules correctly use latest-snapshot subqueries (e.g., `area_analysis.py:42-49`), while others don't. This inconsistency causes unpredictable results between different analytics views.

**Recommendation:** Create a shared utility function in `database/models.py`:
```python
def get_latest_snapshot_subquery(session):
    """Returns a subquery for joining to get only the latest snapshot per property."""
    return (
        session.query(
            PropertySnapshot.property_id,
            func.max(PropertySnapshot.collected_at).label("max_date")
        )
        .group_by(PropertySnapshot.property_id)
        .subquery()
    )
```

---

### Low Severity Issues

#### Issue 3: Division by Zero Risk

**Location:** `analytics/price_trends.py:141`
```python
trends["change_pct"] = (
    (trends["current_avg"] - trends["previous_avg"]) / trends["previous_avg"] * 100
)
```

**Fix:** Add null/zero check:
```python
trends["change_pct"] = np.where(
    trends["previous_avg"] > 0,
    (trends["current_avg"] - trends["previous_avg"]) / trends["previous_avg"] * 100,
    np.nan
)
```

---

#### Issue 4: Hardcoded Link Format

**Location:** `dashboard/app.py:201`
```python
display_df["link"] = display_df["id"].apply(lambda x: f"https://www.spitogatos.gr/aggelia/11{x}")
```

**Issue:** Prepending "11" to all property IDs may not be correct for all listings.

**Recommendation:** Store the full URL or URL pattern in the database during collection, or verify the link format with the API documentation.

---

#### Issue 5: Session Initialization in Context Managers

**Location:** `analytics/advanced_insights.py`, `analytics/investor_tools.py`

```python
def __init__(self):
    self.session = None  # Not initialized until __enter__

def some_method(self):
    self.session.query(...)  # AttributeError if not using 'with'
```

**Fix:** Initialize session in `__init__` or add defensive check:
```python
def __init__(self):
    self.session = get_session()  # Or: Check in each method
```

---

#### Issue 6: Mixed Timezone Handling

**Location:** Various files
**Description:** Inconsistent use of `datetime.utcnow()` (naive) and `datetime.now(timezone.utc)` (aware).

**Recommendation:** Standardize on timezone-aware datetimes:
```python
from datetime import datetime, timezone
datetime.now(timezone.utc)  # Everywhere
```

---

## Part 2: Enhancement Recommendations

### Tier 1: High-Impact Enhancements

#### 1. Price Prediction Model

**Description:** Add ML-based price forecasting using historical snapshot data.

**Implementation:**
- Use Facebook Prophet or scikit-learn for time-series prediction
- Train models per area with weekly price averages
- Predict 30/60/90 day price trajectories

**New file:** `analytics/price_prediction.py`
```python
class PricePredictionAnalyzer:
    def predict_area_prices(self, area: str, days_ahead: int = 30):
        """Predict future price per sqm for an area."""
        # Get historical data
        # Train Prophet model
        # Return predictions with confidence intervals
```

**Dashboard integration:** Add "Price Forecast" tab in Investor Dashboard

**Business value:** First-mover advantage on appreciating areas

---

#### 2. Automated Alert System

**Description:** Email/webhook notifications for market events.

**Alert types:**
- New listing matching criteria (area, price, size)
- Price drop on watched property (>X%)
- Market condition change (Buyer's ↔ Seller's market)
- Weekly market summary

**Implementation:**
```python
# New tables
alerts:
  - id, user_email, alert_type, criteria_json, enabled, created_at

alert_history:
  - id, alert_id, triggered_at, property_id, message

# New service
alerts/notification_service.py
```

**Business value:** Investors never miss opportunities

---

#### 3. Rental Data Collection & Yield Calculation

**Description:** Expand to collect rental listings for actual yield calculation.

**Changes:**
- Add `listing_type="rent"` parameter to collector
- New table `rental_snapshots` or extend existing
- Match rental prices to similar sale properties
- Calculate: `Annual Yield = (Monthly Rent × 12) / Sale Price`

**Dashboard:** Add "Rental Yields by Area" comparison chart

**Business value:** Real yield data is extremely valuable for investment decisions

---

#### 4. Comparable Property Auto-Valuation

**Description:** Automated property valuation based on comparables.

**Algorithm:**
1. Find properties in same area
2. Filter to ±20% size, similar room count
3. Calculate weighted average price/sqm (recent sales weighted higher)
4. Return valuation range with confidence score

**New method:**
```python
def auto_valuate(self, area: str, sq_meters: int, rooms: int) -> dict:
    return {
        "estimated_value_low": 245000,
        "estimated_value_mid": 265000,
        "estimated_value_high": 285000,
        "confidence": 0.85,
        "comparables_used": 8,
    }
```

---

### Tier 2: Medium-Impact Enhancements

#### 5. Watchlist Feature

**Description:** Track specific properties over time.

**Tables:**
```sql
watchlist:
  - id, property_id, notes, added_at, last_notified_at
```

**Features:**
- Add/remove from watchlist
- Price history sparkline chart
- Alerts on price changes
- Export watched properties

---

#### 6. Market Report Generator

**Description:** Automated weekly/monthly market reports.

**Contents:**
- Price trends by area (top gainers/losers)
- New listing velocity
- Days on market trends
- Top deals of the period
- Agent activity summary

**Output:** PDF or HTML email

---

#### 7. Geographic Expansion

**Description:** Monitor more Greek markets.

**New areas:**
- Thessaloniki (ID: TBD)
- Crete (ID: TBD)
- Rhodes, Santorini (seasonal markets)

**Implementation:**
- Make MONITORED_AREAS configurable via dashboard
- Add area-selection filters to all analytics

---

#### 8. Historical Trend Visualization

**Description:** Long-term analytics (6-12 months).

**New charts:**
- Price per sqm trend lines (weekly/monthly)
- Seasonal pattern detection
- Year-over-year comparison
- Inventory level trends

---

#### 9. REST API for External Integration

**Description:** Expose analytics via API.

**Endpoints:**
```
GET /api/v1/areas
GET /api/v1/areas/{id}/stats
GET /api/v1/areas/{id}/trends
GET /api/v1/properties?min_price=X&max_price=Y
GET /api/v1/market/signals
GET /api/v1/deals
```

**Implementation:** FastAPI service alongside Streamlit

---

### Tier 3: Quick Wins

| Enhancement | Effort | Impact |
|------------|--------|--------|
| Add CSV export buttons to all tables | Low | High |
| Implement Streamlit caching for expensive queries | Low | Medium |
| Show collection status in dashboard header | Low | Medium |
| Make all property IDs clickable links | Low | Medium |
| Add theme toggle (dark/light) | Low | Low |
| Add loading spinners to slow operations | Low | Medium |

---

### Tier 4: Data Quality Enhancements

#### 10. Duplicate Property Detection

**Description:** Properties may be relisted with new IDs.

**Detection criteria:**
- Same geography + same sq_meters + same price (±5%)
- Same agent + same rooms + same floor

**Action:** Flag as potential duplicate, link to original

---

#### 11. Data Quality Dashboard

**Description:** Monitor data completeness.

**Metrics:**
- % properties with valid coordinates
- % with room/floor/bathroom data
- Areas with sparse coverage
- Collection success rate

---

#### 12. Outlier Detection

**Description:** Flag suspicious data automatically.

**Rules:**
- Price/sqm > 3σ from area mean
- sq_meters < 10 or > 1000
- Price = 0 or negative
- Missing geography

---

## Part 3: Prioritized Implementation Roadmap

### Phase 1: Bug Fixes (1-2 days)
1. Fix duplicate snapshot counting in analytics
2. Add defensive null checks for division operations
3. Standardize session management

### Phase 2: Quick Wins (1 week)
1. CSV export buttons
2. Streamlit caching
3. Collection status widget
4. Clickable property links

### Phase 3: High-Value Features (2-4 weeks)
1. Rental data collection & yield calculation
2. Watchlist feature
3. Auto-valuation with comparables
4. Market report generator

### Phase 4: Advanced Features (1-2 months)
1. Price prediction model
2. Alert system
3. REST API
4. Geographic expansion

---

## Conclusion

The Real Estate Analytics Engine is a solid foundation with excellent architecture and functionality. The identified issues are minor and don't affect the core value proposition. The enhancement roadmap can transform this from a useful tool into a comprehensive real estate investment platform.

**Recommended next step:** Start with Phase 1 bug fixes, then implement CSV export and caching (quick wins with high user satisfaction).
