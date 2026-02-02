"""
Listing page scraper using Playwright.

Scrapes additional property details from individual listing pages that
aren't available through the API.
"""
import json
import random
import re
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PlaywrightTimeout

import sys
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
from config import REQUEST_DELAY_SECONDS


# Scraping configuration
LISTING_URL_TEMPLATE = "https://www.spitogatos.gr/aggelia/11{property_id}"
MIN_DELAY = 2.0  # Minimum delay between requests (be respectful)
MAX_DELAY = 5.0  # Maximum delay (adds randomness)
PAGE_TIMEOUT = 30000  # 30 seconds timeout for page load


class ListingScraper:
    """Scrapes detailed property information from listing pages."""

    def __init__(self, headless: bool = True):
        """
        Initialize the scraper.

        Args:
            headless: Run browser in headless mode (default True)
        """
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    def __enter__(self):
        """Context manager entry - start browser."""
        self.playwright = sync_playwright().start()

        # Try to find a working chromium executable
        import os
        chromium_path = None
        playwright_cache = os.path.expanduser("~/.cache/ms-playwright")
        if os.path.exists(playwright_cache):
            for entry in os.listdir(playwright_cache):
                if entry.startswith("chromium-"):
                    potential_path = os.path.join(
                        playwright_cache, entry, "chrome-linux", "chrome"
                    )
                    if os.path.exists(potential_path):
                        chromium_path = potential_path
                        break

        launch_args = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        }

        if chromium_path:
            launch_args["executable_path"] = chromium_path

        self.browser = self.playwright.chromium.launch(**launch_args)
        # Create a context with realistic settings
        context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="el-GR",
        )
        self.page = context.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close browser."""
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _wait_random_delay(self):
        """Wait a random amount of time to avoid detection."""
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        time.sleep(delay)

    def scrape_listing(self, property_id: int) -> Optional[Dict[str, Any]]:
        """
        Scrape detailed information from a single listing page.

        Args:
            property_id: The Spitogatos property ID

        Returns:
            Dictionary of scraped data, or None if scraping failed
        """
        url = LISTING_URL_TEMPLATE.format(property_id=property_id)

        try:
            self.page.goto(url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")

            # Wait for main content to load
            self.page.wait_for_selector("body", timeout=PAGE_TIMEOUT)

            # Give JavaScript time to render
            time.sleep(1)

            # Check if listing exists (might be removed)
            if self._is_listing_removed():
                return {"listing_removed": True}

            # Extract all available data
            data = self._extract_listing_data()
            data["scraped_at"] = datetime.utcnow()
            data["property_id"] = property_id

            return data

        except PlaywrightTimeout:
            print(f"Timeout loading listing {property_id}")
            return None
        except Exception as e:
            print(f"Error scraping listing {property_id}: {e}")
            return None

    def _is_listing_removed(self) -> bool:
        """Check if the listing has been removed."""
        try:
            # Look for common "listing removed" indicators
            page_text = self.page.content().lower()
            removed_indicators = [
                "η αγγελία δεν βρέθηκε",  # "listing not found" in Greek
                "listing not found",
                "page not found",
                "404",
                "αυτή η αγγελία έχει αφαιρεθεί",  # "this listing has been removed"
            ]
            return any(indicator in page_text for indicator in removed_indicators)
        except Exception:
            return False

    def _extract_listing_data(self) -> Dict[str, Any]:
        """Extract all available data from the listing page."""
        data = {}

        # Try to extract JSON-LD structured data first (most reliable)
        data.update(self._extract_json_ld())

        # Extract using various strategies (fills in gaps)
        data.update(self._extract_property_details())
        data.update(self._extract_features())
        data.update(self._extract_energy_info())
        data.update(self._extract_additional_details())

        return data

    def _extract_json_ld(self) -> Dict[str, Any]:
        """Extract structured data from JSON-LD script tags."""
        data = {}

        try:
            # Find all JSON-LD script tags
            scripts = self.page.query_selector_all('script[type="application/ld+json"]')

            for script in scripts:
                try:
                    json_text = script.inner_text()
                    json_data = json.loads(json_text)

                    # Handle both single objects and arrays
                    items = json_data if isinstance(json_data, list) else [json_data]

                    for item in items:
                        item_type = item.get("@type", "")

                        # RealEstateListing or Product type
                        if item_type in ["RealEstateListing", "Product", "Residence", "House", "Apartment"]:
                            # Extract year built
                            if "yearBuilt" in item:
                                data["construction_year"] = int(item["yearBuilt"])

                            # Extract floor area
                            if "floorSize" in item:
                                floor_size = item["floorSize"]
                                if isinstance(floor_size, dict):
                                    data["floor_size_value"] = floor_size.get("value")

                            # Extract number of rooms
                            if "numberOfRooms" in item:
                                data["num_rooms"] = int(item["numberOfRooms"])

                            # Extract address details
                            if "address" in item:
                                addr = item["address"]
                                if isinstance(addr, dict):
                                    if "postalCode" in addr:
                                        data["postal_code"] = addr["postalCode"]
                                    if "streetAddress" in addr:
                                        data["street_address"] = addr["streetAddress"]

                            # Extract geo coordinates
                            if "geo" in item:
                                geo = item["geo"]
                                if isinstance(geo, dict):
                                    if "latitude" in geo:
                                        data["latitude"] = float(geo["latitude"])
                                    if "longitude" in geo:
                                        data["longitude"] = float(geo["longitude"])

                            # Extract amenities
                            if "amenityFeature" in item:
                                amenities = item["amenityFeature"]
                                if isinstance(amenities, list):
                                    for amenity in amenities:
                                        name = amenity.get("name", "").lower()
                                        value = amenity.get("value", True)
                                        if "parking" in name or "garage" in name:
                                            data["has_parking"] = bool(value)
                                        elif "pool" in name or "πισίνα" in name:
                                            data["has_pool"] = bool(value)
                                        elif "garden" in name or "κήπος" in name:
                                            data["has_garden"] = bool(value)
                                        elif "elevator" in name or "ασανσέρ" in name:
                                            data["has_elevator"] = bool(value)
                                        elif "air" in name or "κλιματισμ" in name:
                                            data["has_air_conditioning"] = bool(value)

                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

        except Exception as e:
            print(f"Error extracting JSON-LD: {e}")

        return data

    def _extract_property_details(self) -> Dict[str, Any]:
        """Extract basic property details from the page."""
        details = {}

        try:
            # Get the full page content for text extraction
            content = self.page.content()

            # Construction year - look for patterns like "Έτος κατασκευής: 1985"
            year_match = re.search(r'(?:Έτος κατασκευής|Year of construction)[:\s]*(\d{4})', content, re.IGNORECASE)
            if year_match:
                details["construction_year"] = int(year_match.group(1))

            # Plot size - "Οικόπεδο: 500 τ.μ."
            plot_match = re.search(r'(?:Οικόπεδο|Plot)[:\s]*(\d+)\s*(?:τ\.?μ\.?|sqm|m²)', content, re.IGNORECASE)
            if plot_match:
                details["plot_sqm"] = int(plot_match.group(1))

            # Balcony size
            balcony_match = re.search(r'(?:Μπαλκόνι|Balcony)[:\s]*(\d+)\s*(?:τ\.?μ\.?|sqm|m²)', content, re.IGNORECASE)
            if balcony_match:
                details["balcony_sqm"] = int(balcony_match.group(1))

            # Garden size
            garden_match = re.search(r'(?:Κήπος|Garden)[:\s]*(\d+)\s*(?:τ\.?μ\.?|sqm|m²)', content, re.IGNORECASE)
            if garden_match:
                details["garden_sqm"] = int(garden_match.group(1))
                details["has_garden"] = True

            # Parking spots
            parking_match = re.search(r'(?:Θέσεις στάθμευσης|Parking spots?)[:\s]*(\d+)', content, re.IGNORECASE)
            if parking_match:
                details["parking_spots"] = int(parking_match.group(1))
                details["has_parking"] = True

            # Heating type - "Θέρμανση: Αυτόνομη με Φυσικό Αέριο"
            heating_patterns = [
                r'(?:Θέρμανση|Heating)[:\s]*([^<\n]+)',
                r'heating["\s:]+([^"<\n]+)',
            ]
            for pattern in heating_patterns:
                heating_match = re.search(pattern, content, re.IGNORECASE)
                if heating_match:
                    heating_text = heating_match.group(1).strip()
                    if len(heating_text) < 100:  # Sanity check
                        details["heating_type"] = heating_text
                    break

            # Condition/State
            condition_patterns = [
                r'(?:Κατάσταση|Condition)[:\s]*([^<\n,]+)',
            ]
            for pattern in condition_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    condition = match.group(1).strip()
                    if len(condition) < 50:
                        details["condition"] = condition
                    break

            # Orientation
            orientation_match = re.search(r'(?:Προσανατολισμός|Orientation)[:\s]*([^<\n,]+)', content, re.IGNORECASE)
            if orientation_match:
                orientation = orientation_match.group(1).strip()
                if len(orientation) < 50:
                    details["orientation"] = orientation

            # View type
            view_patterns = [
                r'(?:Θέα|View)[:\s]*([^<\n,]+)',
            ]
            for pattern in view_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    view = match.group(1).strip()
                    if len(view) < 100:
                        details["view_type"] = view
                    break

        except Exception as e:
            print(f"Error extracting property details: {e}")

        return details

    def _extract_features(self) -> Dict[str, Any]:
        """Extract boolean features (amenities)."""
        features = {}

        try:
            content = self.page.content().lower()

            # Define feature patterns (Greek and English)
            feature_mappings = {
                "has_elevator": ["ασανσέρ", "elevator", "lift"],
                "has_parking": ["parking", "πάρκινγκ", "γκαράζ", "garage", "θέση στάθμευσης"],
                "has_storage": ["αποθήκη", "storage", "warehouse"],
                "has_garden": ["κήπος", "garden"],
                "has_pool": ["πισίνα", "pool", "swimming"],
                "has_air_conditioning": ["κλιματισμός", "air conditioning", "a/c", "air-condition"],
                "has_fireplace": ["τζάκι", "fireplace"],
                "has_alarm": ["συναγερμός", "alarm", "security system"],
                "has_solar_water_heater": ["ηλιακός", "solar", "θερμοσίφωνας"],
            }

            for feature_key, patterns in feature_mappings.items():
                for pattern in patterns:
                    if pattern in content:
                        features[feature_key] = True
                        break

        except Exception as e:
            print(f"Error extracting features: {e}")

        return features

    def _extract_energy_info(self) -> Dict[str, Any]:
        """Extract energy class information."""
        info = {}

        try:
            content = self.page.content()

            # Energy class - look for patterns like "Ενεργειακή κλάση: B+"
            energy_patterns = [
                r'(?:Ενεργειακή κλάση|Energy class|Energy efficiency)[:\s]*([A-G][+]?)',
                r'energy[_-]?class["\s:]+([A-G][+]?)',
                r'class["\s]*[:\s]*["\s]*([A-G][+]?)["\s]*(?:energy)?',
            ]

            for pattern in energy_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    energy_class = match.group(1).upper()
                    if energy_class in ["A+", "A", "B+", "B", "C", "D", "E", "F", "G"]:
                        info["energy_class"] = energy_class
                        break

        except Exception as e:
            print(f"Error extracting energy info: {e}")

        return info

    def _extract_additional_details(self) -> Dict[str, Any]:
        """Extract additional property details using CSS selectors and data attributes."""
        details = {}

        try:
            content = self.page.content()

            # Try to extract from data attributes or specific HTML patterns
            # Floor level
            floor_patterns = [
                r'(?:Όροφος|Floor)[:\s]*(\d+)',
                r'floor[:\s]*(\d+)',
            ]
            for pattern in floor_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    floor = int(match.group(1))
                    if 0 <= floor <= 50:  # Sanity check
                        details["floor_level"] = floor
                    break

            # Total floors in building
            total_floors_patterns = [
                r'(?:Συνολικοί όροφοι|Total floors)[:\s]*(\d+)',
                r'(?:από|of)\s*(\d+)\s*(?:ορόφους|floors)',
            ]
            for pattern in total_floors_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    total = int(match.group(1))
                    if 1 <= total <= 50:
                        details["total_floors"] = total
                    break

            # Renovation year
            renovation_patterns = [
                r'(?:Ανακαίνιση|Renovated|Renovation)[:\s]*(\d{4})',
                r'(?:ανακαινίστηκε το|renovated in)\s*(\d{4})',
            ]
            for pattern in renovation_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    year = int(match.group(1))
                    if 1900 <= year <= 2030:
                        details["renovation_year"] = year
                    break

            # Distance to sea/beach
            sea_distance_patterns = [
                r'(?:Απόσταση από θάλασσα|Distance to sea)[:\s]*(\d+)\s*(?:μ\.|m|μέτρα|meters)',
                r'(\d+)\s*(?:μ\.|m)\s*(?:από|from)\s*(?:θάλασσα|sea|beach)',
            ]
            for pattern in sea_distance_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    distance = int(match.group(1))
                    if 0 <= distance <= 50000:
                        details["distance_to_sea_m"] = distance
                    break

            # Furnished status
            if re.search(r'(?:επιπλωμένο|furnished)', content, re.IGNORECASE):
                details["is_furnished"] = True
            elif re.search(r'(?:μη επιπλωμένο|unfurnished)', content, re.IGNORECASE):
                details["is_furnished"] = False

            # Pet friendly
            if re.search(r'(?:κατοικίδια δεκτά|pets allowed|pet friendly)', content, re.IGNORECASE):
                details["pets_allowed"] = True

            # Corner property
            if re.search(r'(?:γωνιακό|corner)', content, re.IGNORECASE):
                details["is_corner"] = True

            # Bright/luminous
            if re.search(r'(?:φωτεινό|bright|luminous)', content, re.IGNORECASE):
                details["is_bright"] = True

            # Double glazing
            if re.search(r'(?:διπλά τζάμια|double glaz)', content, re.IGNORECASE):
                details["has_double_glazing"] = True

            # Night power
            if re.search(r'(?:νυχτερινό ρεύμα|night power)', content, re.IGNORECASE):
                details["has_night_power"] = True

            # Suitable for professional use
            if re.search(r'(?:κατάλληλο για επαγγελματική χρήση|suitable for professional use)', content, re.IGNORECASE):
                details["suitable_for_professional_use"] = True

            # Try to extract agent/agency name
            agency_patterns = [
                r'(?:Μεσιτικό γραφείο|Agency|Real Estate)[:\s]*([^<\n]{3,50})',
            ]
            for pattern in agency_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    agency = match.group(1).strip()
                    if len(agency) >= 3 and len(agency) <= 100:
                        details["agency_name"] = agency
                    break

        except Exception as e:
            print(f"Error extracting additional details: {e}")

        return details

    def scrape_multiple(self, property_ids: List[int],
                       progress_callback=None) -> Dict[int, Dict[str, Any]]:
        """
        Scrape multiple listings with delays between requests.

        Args:
            property_ids: List of property IDs to scrape
            progress_callback: Optional callback(current, total, property_id) for progress updates

        Returns:
            Dictionary mapping property_id to scraped data
        """
        results = {}
        total = len(property_ids)

        for i, property_id in enumerate(property_ids):
            if progress_callback:
                progress_callback(i + 1, total, property_id)

            data = self.scrape_listing(property_id)
            if data:
                results[property_id] = data

            # Wait between requests (except for the last one)
            if i < total - 1:
                self._wait_random_delay()

        return results


def scrape_property_details(property_id: int, headless: bool = True) -> Optional[Dict[str, Any]]:
    """
    Convenience function to scrape a single property.

    Args:
        property_id: The Spitogatos property ID
        headless: Run browser in headless mode

    Returns:
        Dictionary of scraped data, or None if failed
    """
    with ListingScraper(headless=headless) as scraper:
        return scraper.scrape_listing(property_id)
