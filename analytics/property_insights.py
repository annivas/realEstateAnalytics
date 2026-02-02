"""
Property insights and analytics based on scraped listing data.

This module provides actionable insights using the detailed property data
scraped from individual listing pages.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

from sqlalchemy import func, and_, or_, case
from sqlalchemy.orm import Session

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
from database.models import Property, PropertySnapshot, get_session


@dataclass
class PropertyInsight:
    """Container for a single insight."""
    title: str
    value: Any
    description: str
    category: str  # 'energy', 'amenities', 'age', 'price', 'market'


class PropertyInsightsAnalyzer:
    """Analyzes property data to generate actionable insights."""

    def __init__(self, session: Optional[Session] = None):
        """Initialize the analyzer with a database session."""
        self.session = session or get_session()

    def get_all_insights(self) -> List[PropertyInsight]:
        """Get all available insights."""
        insights = []
        insights.extend(self.get_energy_insights())
        insights.extend(self.get_age_insights())
        insights.extend(self.get_amenity_insights())
        insights.extend(self.get_price_insights())
        insights.extend(self.get_market_insights())
        return insights

    def get_energy_insights(self) -> List[PropertyInsight]:
        """Get insights related to energy efficiency."""
        insights = []

        # Energy class distribution
        energy_dist = self._get_energy_distribution()
        if energy_dist:
            total = sum(energy_dist.values())
            efficient = sum(energy_dist.get(c, 0) for c in ['A+', 'A', 'B+', 'B'])
            inefficient = sum(energy_dist.get(c, 0) for c in ['E', 'F', 'G'])

            if total > 0:
                efficient_pct = (efficient / total) * 100
                inefficient_pct = (inefficient / total) * 100

                insights.append(PropertyInsight(
                    title="Energy Efficient Properties",
                    value=f"{efficient_pct:.1f}%",
                    description=f"{efficient} properties rated A+ to B ({efficient_pct:.1f}% of rated)",
                    category="energy"
                ))

                insights.append(PropertyInsight(
                    title="Poor Energy Efficiency",
                    value=f"{inefficient_pct:.1f}%",
                    description=f"{inefficient} properties rated E-G may need renovation ({inefficient_pct:.1f}%)",
                    category="energy"
                ))

        # Average price by energy class
        price_by_energy = self._get_avg_price_by_energy_class()
        if price_by_energy:
            best_value = min(price_by_energy.items(), key=lambda x: x[1])
            worst_value = max(price_by_energy.items(), key=lambda x: x[1])

            insights.append(PropertyInsight(
                title="Best Value Energy Class",
                value=best_value[0],
                description=f"Class {best_value[0]} has lowest avg price/sqm: €{best_value[1]:,.0f}",
                category="energy"
            ))

        return insights

    def get_age_insights(self) -> List[PropertyInsight]:
        """Get insights related to property age and construction."""
        insights = []

        # Age distribution
        age_stats = self._get_construction_year_stats()
        if age_stats:
            avg_year = age_stats.get('avg_year')
            oldest = age_stats.get('oldest')
            newest = age_stats.get('newest')

            if avg_year:
                avg_age = datetime.now().year - int(avg_year)
                insights.append(PropertyInsight(
                    title="Average Property Age",
                    value=f"{avg_age} years",
                    description=f"Average construction year: {int(avg_year)}",
                    category="age"
                ))

            # New construction opportunities
            new_builds = self._count_properties_by_year_range(2020, 2030)
            if new_builds > 0:
                insights.append(PropertyInsight(
                    title="New Developments (2020+)",
                    value=new_builds,
                    description=f"{new_builds} properties built since 2020",
                    category="age"
                ))

            # Renovation candidates
            old_buildings = self._count_properties_by_year_range(1900, 1980)
            if old_buildings > 0:
                insights.append(PropertyInsight(
                    title="Potential Renovation Targets",
                    value=old_buildings,
                    description=f"{old_buildings} properties built before 1980 may need updates",
                    category="age"
                ))

        return insights

    def get_amenity_insights(self) -> List[PropertyInsight]:
        """Get insights about property amenities."""
        insights = []

        amenity_counts = self._get_amenity_counts()

        # Most common amenities
        if amenity_counts:
            total_scraped = self._count_scraped_properties()

            for amenity, count in sorted(amenity_counts.items(), key=lambda x: -x[1])[:5]:
                if count > 0 and total_scraped > 0:
                    pct = (count / total_scraped) * 100
                    amenity_name = amenity.replace('has_', '').replace('_', ' ').title()
                    insights.append(PropertyInsight(
                        title=f"{amenity_name} Availability",
                        value=f"{pct:.1f}%",
                        description=f"{count} properties have {amenity_name.lower()}",
                        category="amenities"
                    ))

        # Premium amenity combos
        premium_count = self._count_premium_properties()
        if premium_count > 0:
            insights.append(PropertyInsight(
                title="Premium Properties",
                value=premium_count,
                description=f"Properties with pool + parking + A/C",
                category="amenities"
            ))

        return insights

    def get_price_insights(self) -> List[PropertyInsight]:
        """Get price-related insights using scraped data."""
        insights = []

        # Price premium for amenities
        premiums = self._calculate_amenity_premiums()
        for amenity, premium in sorted(premiums.items(), key=lambda x: -x[1])[:3]:
            if premium > 5:  # Only show significant premiums
                amenity_name = amenity.replace('has_', '').replace('_', ' ').title()
                insights.append(PropertyInsight(
                    title=f"{amenity_name} Premium",
                    value=f"+{premium:.1f}%",
                    description=f"Properties with {amenity_name.lower()} command {premium:.1f}% higher price/sqm",
                    category="price"
                ))

        # Undervalued opportunities
        undervalued = self._find_undervalued_properties()
        if undervalued:
            insights.append(PropertyInsight(
                title="Potential Undervalued Properties",
                value=len(undervalued),
                description=f"Properties with good features but below-average price/sqm",
                category="price"
            ))

        return insights

    def get_market_insights(self) -> List[PropertyInsight]:
        """Get market trend insights."""
        insights = []

        # Heating type distribution (market preference)
        heating_dist = self._get_heating_distribution()
        if heating_dist:
            most_common = max(heating_dist.items(), key=lambda x: x[1])
            if most_common[1] > 0:
                insights.append(PropertyInsight(
                    title="Most Common Heating",
                    value=most_common[0][:30],
                    description=f"{most_common[1]} properties use this heating type",
                    category="market"
                ))

        # Scraping coverage
        total = self._count_active_properties()
        scraped = self._count_scraped_properties()
        if total > 0:
            coverage = (scraped / total) * 100
            insights.append(PropertyInsight(
                title="Data Coverage",
                value=f"{coverage:.1f}%",
                description=f"{scraped} of {total} active properties have detailed data",
                category="market"
            ))

        return insights

    # Helper methods

    def _get_energy_distribution(self) -> Dict[str, int]:
        """Get count of properties by energy class."""
        result = (
            self.session.query(Property.energy_class, func.count(Property.id))
            .filter(Property.energy_class.isnot(None))
            .filter(Property.is_active == True)
            .group_by(Property.energy_class)
            .all()
        )
        return {row[0]: row[1] for row in result}

    def _get_avg_price_by_energy_class(self) -> Dict[str, float]:
        """Get average price per sqm by energy class."""
        result = (
            self.session.query(
                Property.energy_class,
                func.avg(PropertySnapshot.price_per_sqm)
            )
            .join(PropertySnapshot)
            .filter(Property.energy_class.isnot(None))
            .filter(PropertySnapshot.price_per_sqm.isnot(None))
            .filter(Property.is_active == True)
            .group_by(Property.energy_class)
            .all()
        )
        return {row[0]: row[1] for row in result if row[1]}

    def _get_construction_year_stats(self) -> Dict[str, Any]:
        """Get statistics about construction years."""
        result = self.session.query(
            func.avg(Property.construction_year),
            func.min(Property.construction_year),
            func.max(Property.construction_year)
        ).filter(Property.construction_year.isnot(None)).first()

        if result:
            return {
                'avg_year': result[0],
                'oldest': result[1],
                'newest': result[2]
            }
        return {}

    def _count_properties_by_year_range(self, start: int, end: int) -> int:
        """Count properties within a construction year range."""
        return (
            self.session.query(func.count(Property.id))
            .filter(Property.construction_year >= start)
            .filter(Property.construction_year <= end)
            .filter(Property.is_active == True)
            .scalar() or 0
        )

    def _get_amenity_counts(self) -> Dict[str, int]:
        """Get count of properties with each amenity."""
        amenities = [
            'has_parking', 'has_elevator', 'has_storage', 'has_garden',
            'has_pool', 'has_air_conditioning', 'has_fireplace', 'has_alarm'
        ]

        counts = {}
        for amenity in amenities:
            count = (
                self.session.query(func.count(Property.id))
                .filter(getattr(Property, amenity) == True)
                .filter(Property.is_active == True)
                .scalar() or 0
            )
            counts[amenity] = count

        return counts

    def _count_premium_properties(self) -> int:
        """Count properties with pool + parking + A/C."""
        return (
            self.session.query(func.count(Property.id))
            .filter(Property.has_pool == True)
            .filter(Property.has_parking == True)
            .filter(Property.has_air_conditioning == True)
            .filter(Property.is_active == True)
            .scalar() or 0
        )

    def _calculate_amenity_premiums(self) -> Dict[str, float]:
        """Calculate price premium for each amenity."""
        # Get base average price
        base_avg = (
            self.session.query(func.avg(PropertySnapshot.price_per_sqm))
            .join(Property)
            .filter(Property.is_active == True)
            .filter(PropertySnapshot.price_per_sqm.isnot(None))
            .scalar()
        )

        if not base_avg:
            return {}

        premiums = {}
        amenities = ['has_parking', 'has_elevator', 'has_pool', 'has_air_conditioning', 'has_garden']

        for amenity in amenities:
            avg_with = (
                self.session.query(func.avg(PropertySnapshot.price_per_sqm))
                .join(Property)
                .filter(getattr(Property, amenity) == True)
                .filter(Property.is_active == True)
                .filter(PropertySnapshot.price_per_sqm.isnot(None))
                .scalar()
            )

            if avg_with:
                premium_pct = ((avg_with - base_avg) / base_avg) * 100
                premiums[amenity] = premium_pct

        return premiums

    def _find_undervalued_properties(self, limit: int = 20) -> List[int]:
        """Find potentially undervalued properties."""
        # Properties with good energy class + amenities but below-average price
        avg_price = (
            self.session.query(func.avg(PropertySnapshot.price_per_sqm))
            .join(Property)
            .filter(Property.is_active == True)
            .scalar()
        )

        if not avg_price:
            return []

        # Get latest snapshot for each property
        subq = (
            self.session.query(
                PropertySnapshot.property_id,
                func.max(PropertySnapshot.collected_at).label('latest')
            )
            .group_by(PropertySnapshot.property_id)
            .subquery()
        )

        result = (
            self.session.query(Property.id)
            .join(PropertySnapshot)
            .join(subq, and_(
                Property.id == subq.c.property_id,
                PropertySnapshot.collected_at == subq.c.latest
            ))
            .filter(Property.is_active == True)
            .filter(Property.energy_class.in_(['A+', 'A', 'B+', 'B']))
            .filter(or_(
                Property.has_parking == True,
                Property.has_elevator == True,
                Property.has_air_conditioning == True
            ))
            .filter(PropertySnapshot.price_per_sqm < avg_price * 0.85)
            .limit(limit)
            .all()
        )

        return [r[0] for r in result]

    def _get_heating_distribution(self) -> Dict[str, int]:
        """Get distribution of heating types."""
        result = (
            self.session.query(Property.heating_type, func.count(Property.id))
            .filter(Property.heating_type.isnot(None))
            .filter(Property.is_active == True)
            .group_by(Property.heating_type)
            .all()
        )
        return {row[0]: row[1] for row in result}

    def _count_active_properties(self) -> int:
        """Count total active properties."""
        return (
            self.session.query(func.count(Property.id))
            .filter(Property.is_active == True)
            .scalar() or 0
        )

    def _count_scraped_properties(self) -> int:
        """Count properties with scraped details."""
        return (
            self.session.query(func.count(Property.id))
            .filter(Property.details_scraped_at.isnot(None))
            .filter(Property.is_active == True)
            .scalar() or 0
        )

    def close(self):
        """Close the database session."""
        self.session.close()


def get_property_insights() -> List[PropertyInsight]:
    """Convenience function to get all insights."""
    analyzer = PropertyInsightsAnalyzer()
    try:
        return analyzer.get_all_insights()
    finally:
        analyzer.close()


def print_insights():
    """Print all insights to console."""
    insights = get_property_insights()

    if not insights:
        print("No insights available. Run the scraper to collect detailed property data.")
        return

    current_category = None
    for insight in insights:
        if insight.category != current_category:
            current_category = insight.category
            print(f"\n{'=' * 50}")
            print(f" {current_category.upper()} INSIGHTS")
            print('=' * 50)

        print(f"\n{insight.title}: {insight.value}")
        print(f"  {insight.description}")


if __name__ == "__main__":
    print_insights()
