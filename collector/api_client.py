"""
Spitogatos API client for fetching real estate listings.
"""
import time
import logging
from datetime import datetime
from typing import Optional, Generator, List

import httpx

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    API_BASE_URL,
    API_ENDPOINTS,
    DEFAULT_LISTING_TYPE,
    DEFAULT_CATEGORY,
    DEFAULT_SORT_BY,
    DEFAULT_SORT_ORDER,
    DEFAULT_PAGE_SIZE,
    REQUEST_DELAY_SECONDS,
    MAX_RETRIES,
    RETRY_DELAY_SECONDS,
    MONITORED_AREAS,
)
from database.models import (
    get_session,
    Property,
    PropertySnapshot,
    Area,
    Agent,
    CollectionRun,
)

logger = logging.getLogger(__name__)


class SpitogatosClient:
    """Client for interacting with the Spitogatos API."""

    def __init__(self):
        self.base_url = API_BASE_URL
        self.client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9,el;q=0.8",
                "Referer": "https://www.spitogatos.gr/",
                "Origin": "https://www.spitogatos.gr",
            },
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def _build_search_url(
        self,
        area_ids: List[int],
        offset: int = 0,
        listing_type: str = DEFAULT_LISTING_TYPE,
        category: str = DEFAULT_CATEGORY,
    ) -> str:
        """Build the search URL with query parameters."""
        url = f"{self.base_url}{API_ENDPOINTS['search_results_map']}"
        
        params = {
            "listingType": listing_type,
            "category": category,
            "sortBy": DEFAULT_SORT_BY,
            "sortOrder": DEFAULT_SORT_ORDER,
            "offset": offset,
        }
        
        # Build query string manually for array parameters
        query_parts = [f"{k}={v}" for k, v in params.items()]
        for area_id in area_ids:
            query_parts.append(f"areaIDs[]={area_id}")
        
        return f"{url}?{'&'.join(query_parts)}"

    def _fetch_with_retry(self, url: str) -> Optional[dict]:
        """Fetch URL with retry logic."""
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.get(url)
                response.raise_for_status()
                # Handle empty responses
                if not response.content:
                    return None
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code} on attempt {attempt + 1}: {url}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
            except httpx.RequestError as e:
                logger.error(f"Request error on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
        return None

    def fetch_listings(
        self,
        area_ids: List[int],
        listing_type: str = DEFAULT_LISTING_TYPE,
        max_results: Optional[int] = None,
    ) -> Generator[dict, None, None]:
        """
        Fetch all listings for given areas with pagination.
        
        Yields individual property data dictionaries.
        
        API Response structure:
        {
            "data": { ... clusters of properties ... },
            "count": 300,  # results in this page
            "total": 157261  # total available results
        }
        
        Args:
            area_ids: List of area IDs to fetch
            listing_type: 'sale' or 'rent'
            max_results: Optional limit on total results to fetch
        """
        offset = 0
        total_fetched = 0
        total_available = None
        
        while True:
            url = self._build_search_url(area_ids, offset, listing_type)
            logger.info(f"Fetching listings at offset {offset}...")
            
            data = self._fetch_with_retry(url)
            if not data:
                logger.warning(f"No data returned at offset {offset}")
                break
            
            # Get pagination info from response
            count = data.get("count", 0)
            total_available = data.get("total", 0)
            clusters = data.get("data", {})
            
            if total_available and offset == 0:
                logger.info(f"Total available listings: {total_available:,}")
            
            if not clusters or count == 0:
                logger.info("No more listings found.")
                break
            
            # Each cluster contains properties grouped by location
            properties_in_batch = 0
            for cluster_key, cluster_data in clusters.items():
                properties = cluster_data.get("properties", [])
                for prop in properties:
                    # Add cluster metadata to property
                    prop["_cluster_pin"] = cluster_data.get("pin")
                    prop["_geocode_type"] = cluster_data.get("geocodeType")
                    prop["_top_vip"] = cluster_data.get("topVIP", False)
                    yield prop
                    properties_in_batch += 1
                    total_fetched += 1
                    
                    # Check if we've hit the max_results limit
                    if max_results and total_fetched >= max_results:
                        logger.info(f"Reached max_results limit ({max_results})")
                        return
            
            logger.info(f"Fetched {properties_in_batch} properties, {total_fetched:,} / {total_available:,} total")
            
            # Move to next page - increment by the count we received
            offset += count
            
            # Check if we've fetched all available results
            if offset >= total_available:
                logger.info("Fetched all available listings.")
                break
            
            time.sleep(REQUEST_DELAY_SECONDS)
        
        logger.info(f"Completed fetching. Total properties: {total_fetched:,}")

    def collect_and_store(
        self,
        area_ids: Optional[List[int]] = None,
        listing_type: str = DEFAULT_LISTING_TYPE,
        max_results: Optional[int] = None,
    ) -> dict:
        """
        Collect listings from API and store in database.
        
        Args:
            area_ids: List of area IDs to collect. Defaults to MONITORED_AREAS.
            listing_type: 'sale' or 'rent'
            max_results: Optional limit on total results to fetch (useful for testing)
            
        Returns:
            Dictionary with collection statistics
        """
        if area_ids is None:
            area_ids = list(MONITORED_AREAS.keys())
        
        session = get_session()
        
        # Create collection run record
        collection_run = CollectionRun(
            status="running",
            areas_collected=len(area_ids),
        )
        session.add(collection_run)
        session.commit()
        
        try:
            new_properties = 0
            updated_properties = 0
            price_changes = 0
            total_properties = 0
            
            for prop_data in self.fetch_listings(area_ids, listing_type, max_results):
                total_properties += 1
                result = self._process_property(session, prop_data, collection_run.id)
                
                if result == "new":
                    new_properties += 1
                elif result == "updated":
                    updated_properties += 1
                elif result == "price_changed":
                    updated_properties += 1
                    price_changes += 1
                
                # Commit in batches
                if total_properties % 50 == 0:
                    session.commit()
                    logger.info(f"Processed {total_properties} properties...")
            
            # Final commit
            session.commit()
            
            # Update collection run stats
            collection_run.completed_at = datetime.utcnow()
            collection_run.status = "completed"
            collection_run.properties_found = total_properties
            collection_run.new_properties = new_properties
            collection_run.updated_properties = updated_properties
            collection_run.price_changes_detected = price_changes
            session.commit()
            
            logger.info(
                f"Collection completed: {total_properties} found, "
                f"{new_properties} new, {updated_properties} updated, "
                f"{price_changes} price changes"
            )
            
            # Extract stats before closing session
            result = {
                "id": collection_run.id,
                "status": collection_run.status,
                "started_at": collection_run.started_at,
                "completed_at": collection_run.completed_at,
                "properties_found": collection_run.properties_found,
                "new_properties": collection_run.new_properties,
                "updated_properties": collection_run.updated_properties,
                "price_changes_detected": collection_run.price_changes_detected,
            }
            
        except Exception as e:
            logger.error(f"Collection failed: {e}")
            collection_run.status = "failed"
            collection_run.error_message = str(e)
            collection_run.completed_at = datetime.utcnow()
            session.commit()
            
            result = {
                "id": collection_run.id,
                "status": "failed",
                "started_at": collection_run.started_at,
                "completed_at": collection_run.completed_at,
                "properties_found": 0,
                "new_properties": 0,
                "updated_properties": 0,
                "price_changes_detected": 0,
                "error_message": str(e),
            }
            raise
        finally:
            session.close()
        
        return result

    def _process_property(
        self,
        session,
        prop_data: dict,
        collection_run_id: int,
    ) -> str:
        """
        Process a single property from API response.
        
        Returns: 'new', 'updated', 'price_changed', or 'unchanged'
        """
        prop_id = prop_data.get("id")
        if not prop_id:
            return "unchanged"
        
        # Get or create agent
        agent_id = prop_data.get("agent_id")
        if agent_id:
            agent = session.query(Agent).filter_by(id=agent_id).first()
            if not agent:
                re_agent = prop_data.get("reAgent") or {}
                agent = Agent(
                    id=agent_id,
                    agency_name=re_agent.get("agencyName") if re_agent else None,
                )
                session.add(agent)
            else:
                agent.last_seen = datetime.utcnow()
        
        # Get or create area (try to extract from geography if needed)
        # For now, we'll rely on the pre-seeded areas
        
        # Check if property exists
        existing = session.query(Property).filter_by(id=prop_id).first()
        
        current_price = prop_data.get("price", 0)
        sq_meters = prop_data.get("sq_meters", 0)
        price_per_sqm = current_price / sq_meters if sq_meters and sq_meters > 0 else None
        
        if existing:
            # Update existing property
            existing.last_seen = datetime.utcnow()
            existing.is_active = True
            existing.modified = self._parse_datetime(prop_data.get("modified"))
            
            # Get last snapshot to compare prices
            last_snapshot = (
                session.query(PropertySnapshot)
                .filter_by(property_id=prop_id)
                .order_by(PropertySnapshot.collected_at.desc())
                .first()
            )
            
            result = "updated"
            if last_snapshot and last_snapshot.price != current_price:
                result = "price_changed"
            
            # Create new snapshot
            snapshot = PropertySnapshot(
                property_id=prop_id,
                collection_run_id=collection_run_id,
                price=current_price,
                price_reduced=prop_data.get("priceReduced", False),
                price_pre_reduction=prop_data.get("pricePreReduction"),
                price_change_percentage=prop_data.get("priceChangePercentage"),
                price_per_sqm=price_per_sqm,
            )
            session.add(snapshot)
            
            return result
        else:
            # Create new property
            property_obj = Property(
                id=prop_id,
                category=prop_data.get("category", "unknown"),
                subtype=prop_data.get("subtype"),
                buy_or_rent="sale" if prop_data.get("buy_or_rent") == "0" else "rent",
                geography=prop_data.get("geography"),
                latitude=prop_data.get("latitude"),
                longitude=prop_data.get("longitude"),
                geocode_type=prop_data.get("geocodeType"),
                sq_meters=sq_meters,
                floor_number=prop_data.get("floorNumber"),
                rooms=prop_data.get("rooms"),
                total_rooms=prop_data.get("totalRooms"),
                bathrooms=prop_data.get("no_of_bathrooms"),
                kitchens=prop_data.get("kitchens"),
                living_rooms=prop_data.get("livingRooms"),
                within_city_plan=prop_data.get("within_city_plan") == "1",
                agricultural_use=prop_data.get("agriculturalUse") == "1",
                new_development=prop_data.get("newDevelopment") == "1",
                has_virtual_tour=prop_data.get("hasVTour", False),
                has_video=prop_data.get("hasVideo", False),
                ad_type=prop_data.get("adType_code"),
                agent_id=agent_id,
                description=prop_data.get("description"),
                main_image_url=prop_data.get("mainImageURL"),
                image_count=len(prop_data.get("imageIds", [])),
                first_publish_date=self._parse_datetime(prop_data.get("firstPublishDate")),
                uploaded=self._parse_datetime(prop_data.get("uploaded")),
                modified=self._parse_datetime(prop_data.get("modified")),
            )
            session.add(property_obj)
            
            # Create initial snapshot
            snapshot = PropertySnapshot(
                property_id=prop_id,
                collection_run_id=collection_run_id,
                price=current_price,
                price_reduced=prop_data.get("priceReduced", False),
                price_pre_reduction=prop_data.get("pricePreReduction"),
                price_change_percentage=prop_data.get("priceChangePercentage"),
                price_per_sqm=price_per_sqm,
            )
            session.add(snapshot)
            
            return "new"

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string from API."""
        if not dt_str:
            return None
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(dt_str, "%Y-%m-%d")
            except ValueError:
                return None
