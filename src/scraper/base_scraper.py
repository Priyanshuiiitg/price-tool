from abc import ABC, abstractmethod
from typing import List, Dict, Any
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from src.utils.logger import get_logger
import os

logger = get_logger(__name__)

class BaseScraper(ABC):
    """Base class for all scrapers."""
    
    name = "base_scraper"
    supported_countries = ["ALL"]  # By default, support all countries
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }
    
    def get_scraperapi_url(self, target_url):
        api_key = os.getenv('SCRAPERAPI_KEY')
        return f'https://api.scraperapi.com/?api_key={api_key}&url={target_url}'

    async def fetch_html(self, url: str) -> str:
        """Fetch HTML content from a URL, using ScraperAPI for e-commerce sites, fallback to Selenium, then httpx."""
        ecom_domains = [
            "amazon.", "flipkart.com", "myntra.com", "snapdeal.com", "ajio.com", "jiomart.com"
        ]
        if any(domain in url for domain in ecom_domains):
            # 1. Try ScraperAPI
            try:
                scraperapi_url = self.get_scraperapi_url(url)
                async with aiohttp.ClientSession() as session:
                    async with session.get(scraperapi_url, headers=self.headers, timeout=30) as response:
                        if response.status == 200:
                            html = await response.text()
                            if html and len(html) > 1000:
                                return html
                        else:
                            logger.error(f"ScraperAPI failed for {url}, status code: {response.status}")
            except Exception as e:
                logger.error(f"ScraperAPI fetch failed for {url}: {e}")
            # 2. Fallback to Selenium
            try:
                from src.utils.selenium_fetcher import fetch_html_selenium
                html = fetch_html_selenium(url)
                if html and len(html) > 1000:
                    return html
            except Exception as e:
                logger.error(f"Selenium fetch failed for {url}: {e}")
        # 3. Fallback to httpx
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=15) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.error(f"Failed to fetch {url}, status code: {response.status}")
                        return ""
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return ""
    
    async def fetch_json(self, url: str) -> Dict:
        """Fetch JSON content from a URL."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Failed to fetch JSON from {url}, status code: {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"Error fetching JSON from {url}: {str(e)}")
            return {}
    
    def parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML content into a BeautifulSoup object."""
        return BeautifulSoup(html, "html.parser")
    
    def adapt_country(self, country: str) -> str:
        """Adapt the country code to the format expected by the scraper."""
        return country.upper()
    
    def clean_price(self, price: str) -> str:
        """Clean and standardize price format."""
        if not price:
            return "0"
        
        # Remove non-numeric characters except for decimal points and commas
        clean = ''.join(c for c in price if c.isdigit() or c in ".,")
        
        # Replace commas with empty string if they're thousand separators
        if "," in clean and "." in clean:
            if clean.index(",") < clean.index("."):
                clean = clean.replace(",", "")
        elif "," in clean and "." not in clean:
            clean = clean.replace(",", ".")
            
        try:
            return str(float(clean))
        except ValueError:
            return "0"
    
    def match_product(self, product_name: str, query: str) -> bool:
        """Check if the product matches the query."""
        # A simple matching algorithm - can be improved with more sophisticated approaches
        product_name = product_name.lower()
        query = query.lower()
        
        # Check if all words in the query are in the product name
        query_words = query.split()
        return all(word in product_name for word in query_words)
    
    @abstractmethod
    async def search(self, country: str, query: str) -> List[Dict[str, Any]]:
        """Search for products on the website."""
        pass
    
    @abstractmethod
    def get_search_url(self, country: str, query: str) -> str:
        """Get the URL for searching products."""
        pass 