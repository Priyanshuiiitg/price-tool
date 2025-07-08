from typing import List, Dict, Any
import re
import urllib.parse
import httpx
from src.scraper.base_scraper import BaseScraper
from src.utils.logger import get_logger
from src.utils.ai_helper import AIHelper
from bs4 import BeautifulSoup

logger = get_logger(__name__)

class GenericAIScraper(BaseScraper):
    """
    A generic scraper that uses AI to extract product information from any website.
    This is a fallback for websites that don't have specific scrapers.
    """
    
    name = "generic_ai"
    supported_countries = ["ALL"]  # Supports all countries
    
    # List of popular e-commerce sites by country
    ECOMMERCE_SITES = {
        "US": [
            "amazon.com", "walmart.com", "bestbuy.com", "target.com", "ebay.com",
            "newegg.com", "homedepot.com", "macys.com", "kohls.com", "overstock.com"
        ],
        "UK": [
            "amazon.co.uk", 
            "argos.co.uk", 
            "currys.co.uk", 
            "johnlewis.com", 
            "ebay.co.uk"
        ],
        "IN": [
            "amazon.in", "flipkart.com", "myntra.com", "snapdeal.com", "croma.com",
            "reliancedigital.in", "tatacliq.com", "ajio.com", "shopclues.com", "paytmmall.com"
        ],
        "AU": [
            "amazon.com.au", 
            "jbhifi.com.au", 
            "kogan.com", 
            "officeworks.com.au", 
            "ebay.com.au"
        ],
        "CA": [
            "amazon.ca", 
            "walmart.ca", 
            "bestbuy.ca", 
            "thebay.com", 
            "canadiantire.ca"
        ],
        "DE": [
            "amazon.de", 
            "otto.de", 
            "mediamarkt.de", 
            "saturn.de", 
            "ebay.de"
        ],
        "FR": [
            "amazon.fr", 
            "fnac.com", 
            "cdiscount.com", 
            "darty.com", 
            "boulanger.com"
        ],
        # Add more countries as needed
    }
    
    # Default search engines for product searches
    SEARCH_ENGINES = {
        "google": "https://www.google.com/search?q={query}+{product}+{country}+buy+online",
        "bing": "https://www.bing.com/search?q={query}+{product}+{country}+buy+online",
        "duckduckgo": "https://duckduckgo.com/?q={query}+{product}+{country}+buy+online",
    }
    
    PRODUCT_URL_PATTERNS = {
        "amazon.in": r"/dp/|/gp/product/",
        "flipkart.com": r"/p/|/product/|/search\?q=",
        "myntra.com": r"/buy|/\d{6,}/buy",
        "snapdeal.com": r"/product/|/search\?",
    }
    
    def __init__(self):
        super().__init__()
        self.ai_helper = AIHelper()
    
    def get_search_url(self, country: str, query: str) -> str:
        """Get a generic search URL based on the country and query."""
        # This is a placeholder as we'll be using multiple URLs
        engine = "google"
        return self.SEARCH_ENGINES[engine].format(
            query=urllib.parse.quote(query),
            product="product",
            country=country
        )
    
    async def get_websites_for_country(self, country: str) -> List[str]:
        """Get a list of popular e-commerce websites for the given country."""
        country_code = country.upper()
        
        # If we have predefined sites for this country, return those
        if country_code in self.ECOMMERCE_SITES:
            return self.ECOMMERCE_SITES[country_code]
        
        # For countries we don't have predefined sites for, try to get suggestions from AI
        if self.ai_helper.api_key:
            try:
                # Use Gemini
                import asyncio
                answer = await self.ai_helper._call_gemini(f"What are the 5 most popular e-commerce websites in {country}? Please list only the domain names (e.g., amazon.com), one per line without any explanation or numbering.")
                sites = [line.strip() for line in answer.split("\n") if line.strip()]
                
                if sites:
                    # Cache these for future use
                    self.ECOMMERCE_SITES[country_code] = sites
                    return sites
            except Exception as e:
                logger.error(f"Error getting websites for country {country}: {str(e)}")
        
        # Fallback to international sites
        return self.ECOMMERCE_SITES.get("US", ["amazon.com", "ebay.com", "walmart.com"])
    
    async def search(self, country: str, query: str) -> List[Dict[str, Any]]:
        """Search for products across multiple websites based on the country."""
        results = []
        
        try:
            # Get relevant websites for the country
            websites = await self.get_websites_for_country(country)
            
            # Search on each website
            search_tasks = []
            for website in websites[:5]:  # Expand to 5 sites
                search_tasks.append(self._search_website(website, country, query))
            
            # Run all searches concurrently
            import asyncio
            website_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # Process results
            for website_result in website_results:
                if isinstance(website_result, Exception):
                    logger.error(f"Error in website search: {str(website_result)}")
                    continue
                    
                if isinstance(website_result, list):
                    results.extend(website_result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in generic AI search: {str(e)}")
            return []
    
    async def _search_website(self, website: str, country: str, query: str) -> List[Dict[str, Any]]:
        """Search for products on a specific website."""
        try:
            # Create search URL for the website
            search_url = f"https://www.{website}/search?q={urllib.parse.quote(query)}"
            
            # For some common sites, use known search URL patterns
            if "amazon" in website:
                search_url = f"https://www.{website}/s?k={urllib.parse.quote(query)}"
            elif "ebay" in website:
                search_url = f"https://www.{website}/sch/i.html?_nkw={urllib.parse.quote(query)}"
            elif "walmart" in website:
                search_url = f"https://www.{website}/search/?query={urllib.parse.quote(query)}"
            elif "flipkart" in website:
                search_url = f"https://www.{website}/search?q={urllib.parse.quote(query)}"
            
            logger.info(f"Searching {website} for {query} in {country}: {search_url}")
            
            # Fetch the search results page
            html_content = await self.fetch_html(search_url)
            if not html_content:
                logger.error(f"Failed to fetch search results from {website}")
                return []
            
            # Extract product information using AI
            results = await self._extract_with_ai(html_content, search_url, query, website)
            return results
            
        except Exception as e:
            logger.error(f"Error searching {website}: {str(e)}")
            return []
    
    async def _extract_with_ai(self, html_content: str, url: str, query: str, website: str) -> list:
        if not self.ai_helper.api_key or not html_content:
            return []
        try:
            truncated_html = html_content[:15000] + "..." if len(html_content) > 15000 else html_content
            domain = website.lower().replace('www.', '')
            pattern = self.PRODUCT_URL_PATTERNS.get(domain, None)
            pattern_note = f" For {domain}, only extract links matching the pattern: {pattern}" if pattern else ""
            prompt = f"""
            You are a web scraping assistant. Extract up to 5 product listings ONLY from the website {website}. Do NOT include products from any other site.\nWebsite: {website}\nSearch URL: {url}\nSearch Query: {query}\nHTML Content (truncated):\n{truncated_html}\nFor each product, return a JSON list of objects with: productName, price, currency, link, imageUrl, additionalInfo (should be a dictionary or null).\nOnly use product links that are present in the provided HTML. Do not make up or guess links. If you cannot find a link, skip the product. If a field is missing, set it to an empty string. Always include the product link and price if possible. Only include products that match the search query and are actually from {website}.{pattern_note}
            """
            answer = await self.ai_helper._call_gemini(prompt)
            logger.debug(f"Gemini raw answer: {answer}")
            import json, re
            match = re.search(r'\[.*\]', answer, re.DOTALL)
            if match:
                answer = match.group(0)
            try:
                parsed_results = json.loads(answer)
                logger.debug(f"Gemini parsed_results: {parsed_results}")
                processed_results = []
                if isinstance(parsed_results, list):
                    for item in parsed_results:
                        if not isinstance(item, dict):
                            continue
                        if "productName" not in item or not item["productName"]:
                            continue
                        if "link" in item and item["link"] and not item["link"].startswith(("http://", "https://")):
                            if item["link"].startswith("/"):
                                item["link"] = f"https://www.{website}{item['link']}"
                            else:
                                item["link"] = f"https://www.{website}/{item['link']}"
                        if "source" not in item:
                            item["source"] = website
                        if "price" in item and item["price"]:
                            item["price"] = self.clean_price(item["price"])
                        # Fix additionalInfo
                        if "additionalInfo" in item and not isinstance(item["additionalInfo"], dict):
                            if item["additionalInfo"] is None:
                                pass
                            else:
                                item["additionalInfo"] = {"info": str(item["additionalInfo"])}
                        # Ensure required fields are strings
                        for field in ["link", "price", "currency", "productName", "imageUrl"]:
                            if field in item and item[field] is None:
                                item[field] = ""
                            elif field not in item:
                                item[field] = ""
                        # Skip if link or price is empty
                        if not item["link"] or not item["price"]:
                            logger.warning(f"Skipping product with missing link or price: {item}")
                            continue
                        # Only accept products whose link contains the correct domain
                        if domain not in item["link"].lower():
                            logger.warning(f"Skipping product with wrong domain: {item}")
                            continue
                        # If pattern is set, only accept links matching the pattern
                        if pattern and not re.search(pattern, item["link"]):
                            logger.warning(f"Skipping product with link not matching pattern: {item}")
                            continue
                        # Validate link with HEAD request
                        try:
                            async with httpx.AsyncClient(timeout=5) as client:
                                resp = await client.head(item["link"], follow_redirects=True)
                                if resp.status_code != 200:
                                    logger.warning(f"Skipping product with non-200 link: {item['link']} (status {resp.status_code})")
                                    continue
                        except Exception as e:
                            logger.warning(f"Skipping product with unreachable link: {item['link']} ({e})")
                            continue
                        processed_results.append(item)
                        if len(processed_results) >= 5:
                            break
                if not processed_results:
                    logger.warning(f"No valid products extracted for {website} with Gemini, falling back to BeautifulSoup.")
                    # Fallback: Use BeautifulSoup to extract product links and names
                    soup = BeautifulSoup(html_content, "html.parser")
                    links = soup.find_all("a", href=True)
                    seen = set()
                    for a in links:
                        href = a["href"]
                        if domain not in href:
                            continue
                        if href in seen:
                            continue
                        seen.add(href)
                        # Only accept links matching the product pattern
                        if pattern and not re.search(pattern, href):
                            continue
                        # Try to get product name from link text or title
                        name = a.get_text(strip=True) or a.get("title", "")
                        if not name:
                            continue
                        # Validate link
                        link = href if href.startswith("http") else f"https://{domain}{href if href.startswith('/') else '/' + href}"
                        try:
                            async with httpx.AsyncClient(timeout=5) as client:
                                resp = await client.head(link, follow_redirects=True)
                                if resp.status_code != 200:
                                    continue
                        except Exception:
                            continue
                        processed_results.append({
                            "link": link,
                            "price": "",
                            "currency": "",
                            "productName": name,
                            "source": website,
                            "imageUrl": "",
                            "additionalInfo": None
                        })
                        if len(processed_results) >= 5:
                            break
                logger.debug(f"Final results to return: {processed_results}")
                return processed_results
            except Exception as e:
                logger.error(f"Failed to parse Gemini JSON: {e}\nRaw: {answer}")
                return []
        except Exception as e:
            logger.error(f"Error extracting products with AI from {website}: {str(e)}")
            return [] 