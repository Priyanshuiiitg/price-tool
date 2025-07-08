import asyncio
from typing import List, Dict, Any
import importlib
import os
import glob
from src.utils.logger import get_logger
from src.utils.google_custom_search import search_products_google

logger = get_logger(__name__)

class ScraperManager:
    def __init__(self):
        self.scrapers = {}
        self._load_scrapers()
    
    def _load_scrapers(self):
        """Load all available scrapers dynamically."""
        try:
            # Get the directory where the scrapers are located
            current_dir = os.path.dirname(os.path.abspath(__file__))
            scrapers_dir = os.path.join(current_dir, "sites")
            
            # Ensure the directory exists
            if not os.path.exists(scrapers_dir):
                os.makedirs(scrapers_dir)
            
            # Find all Python files in the scrapers directory
            scraper_files = glob.glob(os.path.join(scrapers_dir, "*.py"))
            
            for scraper_file in scraper_files:
                if "__init__" in scraper_file or "__pycache__" in scraper_file:
                    continue
                
                # Get the module name from the file path
                module_name = os.path.basename(scraper_file).replace(".py", "")
                full_module_name = f"src.scraper.sites.{module_name}"
                
                # Import the module dynamically
                try:
                    module = importlib.import_module(full_module_name)
                    
                    # Get the scraper class from the module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        # Check if this is a scraper class
                        if (isinstance(attr, type) and 
                            attr.__name__ != "BaseScraper" and
                            hasattr(attr, "supported_countries") and
                            hasattr(attr, "name")):
                            
                            # Create an instance of the scraper
                            scraper_instance = attr()
                            self.scrapers[scraper_instance.name] = scraper_instance
                            logger.info(f"Loaded scraper: {scraper_instance.name}")
                except Exception as e:
                    logger.error(f"Error loading scraper {module_name}: {str(e)}")
            
            # After loading all dynamic scrapers, add GoogleCustomSearchScraper
            self.scrapers["google_custom_search"] = GoogleCustomSearchScraper()
        except Exception as e:
            logger.error(f"Error loading scrapers: {str(e)}")

    def get_relevant_scrapers(self, country: str) -> List[Any]:
        """Get all scrapers that support the given country."""
        return [
            scraper for scraper in self.scrapers.values() 
            if country.upper() in [c.upper() for c in scraper.supported_countries]
        ]

    async def search_products(self, country: str, query: str) -> List[Dict[str, Any]]:
        """Search for products across all relevant scrapers."""
        relevant_scrapers = self.get_relevant_scrapers(country)
        if not relevant_scrapers:
            # If no specific scraper supports the country, use general scrapers that support all countries
            relevant_scrapers = [
                scraper for scraper in self.scrapers.values() 
                if "ALL" in scraper.supported_countries
            ]
        
        if not relevant_scrapers:
            logger.warning(f"No scrapers found for country: {country}")
            return []
        
        # Run all scrapers concurrently
        tasks = [scraper.search(country, query) for scraper in relevant_scrapers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results, filter out exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error from scraper {relevant_scrapers[i].name}: {str(result)}")
                continue
            
            if isinstance(result, list):
                processed_results.extend(result)
            
        return processed_results 

class GoogleCustomSearchScraper:
    name = "google_custom_search"
    supported_countries = ["ALL"]
    async def search(self, country, query):
        try:
            return await search_products_google(query, country)
        except Exception as e:
            logger.error(f"Google Custom Search failed: {e}")
            return [] 