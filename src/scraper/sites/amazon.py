from typing import List, Dict, Any
import re
import urllib.parse
from src.scraper.base_scraper import BaseScraper
from src.utils.logger import get_logger
from src.utils.ai_helper import AIHelper
import os
import requests

logger = get_logger(__name__)

class AmazonScraper(BaseScraper):
    """Scraper for Amazon websites."""
    
    name = "amazon"
    supported_countries = ["US", "UK", "DE", "FR", "ES", "IT", "JP", "IN", "CA", "AU", "ALL"]
    
    def __init__(self):
        super().__init__()
        self.ai_helper = AIHelper()
        # Update headers for Amazon
        self.headers.update({
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })
    
    def get_domain(self, country: str) -> str:
        """Get the Amazon domain for the given country."""
        country = country.upper()
        domains = {
            "US": "amazon.com",
            "UK": "amazon.co.uk",
            "DE": "amazon.de",
            "FR": "amazon.fr",
            "ES": "amazon.es",
            "IT": "amazon.it",
            "JP": "amazon.co.jp",
            "IN": "amazon.in",
            "CA": "amazon.ca",
            "AU": "amazon.com.au",
        }
        return domains.get(country, "amazon.com")
    
    def get_search_url(self, country: str, query: str) -> str:
        """Get the Amazon search URL for the given query."""
        domain = self.get_domain(country)
        encoded_query = urllib.parse.quote(query)
        return f"https://www.{domain}/s?k={encoded_query}"
    
    async def search(self, country: str, query: str) -> List[Dict[str, Any]]:
        """Search for products on Amazon using ScraperAPI's structured endpoint if possible."""
        results = []
        api_key = os.getenv('SCRAPERAPI_KEY')
        domain = self.get_domain(country)
        # Check if query is an ASIN (10 chars, alphanumeric)
        is_asin = isinstance(query, str) and len(query) == 10 and query.isalnum()
        try:
            if api_key:
                if is_asin:
                    # Use product endpoint
                    url = f'https://api.scraperapi.com/structured/amazon/product'
                    params = {'api_key': api_key, 'asin': query}
                else:
                    # Use search endpoint
                    url = f'https://api.scraperapi.com/structured/amazon/search'
                    params = {'api_key': api_key, 'search_term': query, 'domain': domain}
                try:
                    resp = requests.get(url, params=params, timeout=20)
                    if resp.status_code == 200:
                        data = resp.json()
                        # If product endpoint, wrap in a list
                        if is_asin and isinstance(data, dict) and 'asin' in data:
                            products = [data]
                        elif 'products' in data and isinstance(data['products'], list):
                            products = data['products'][:10]
                        else:
                            products = []
                        for prod in products:
                            # Defensive: handle missing fields
                            result = {
                                'link': prod.get('url', prod.get('product_url', '')),
                                'price': prod.get('pricing', prod.get('price', '')),
                                'currency': prod.get('currency', ''),
                                'productName': prod.get('name', prod.get('title', '')),
                                'source': f"Amazon {country}",
                                'imageUrl': (prod.get('images') or prod.get('image', ['']))[0] if isinstance(prod.get('images'), list) and prod.get('images') else prod.get('image', ''),
                                'additionalInfo': prod.get('product_information', None)
                            }
                            # Ensure all required fields are strings
                            for k in ['link', 'price', 'currency', 'productName', 'imageUrl']:
                                if result[k] is None:
                                    result[k] = ''
                            results.append(result)
                        if results:
                            return results
                except Exception as e:
                    logger.error(f"ScraperAPI structured endpoint failed: {e}")
            # Fallback to original HTML scraping logic
            search_url = self.get_search_url(country, query)
            logger.info(f"[Fallback] Searching Amazon {country}: {search_url}")
            html_content = await self.fetch_html(search_url)
            if not html_content:
                logger.error(f"Failed to fetch Amazon search results for {query} in {country}")
                return []
            
            # Parse HTML
            soup = self.parse_html(html_content)
            
            # Find all product items
            # Note: Amazon's HTML structure frequently changes, so we need to adapt
            products = soup.select("div.s-result-item[data-component-type='s-search-result']")
            if not products:
                products = soup.select("div.sg-col-inner")
            
            # Get currency symbol
            currency = self._extract_currency(html_content, country)
            
            # Process each product
            for product in products[:10]:  # Limit to 10 products to avoid overloading
                try:
                    # Extract product link
                    link_elem = product.select_one("a.a-link-normal.s-no-outline")
                    if not link_elem:
                        link_elem = product.select_one("a.a-link-normal")
                    
                    if not link_elem:
                        continue
                    
                    link = link_elem.get("href")
                    if link and link.startswith("/"):
                        domain = self.get_domain(country)
                        link = f"https://www.{domain}{link}"
                    
                    # Extract product name
                    name_elem = product.select_one("span.a-size-medium.a-color-base.a-text-normal")
                    if not name_elem:
                        name_elem = product.select_one("span.a-size-base-plus.a-color-base.a-text-normal")
                    
                    product_name = name_elem.text.strip() if name_elem else ""
                    
                    # Skip if product name doesn't match query
                    if not product_name or not self.match_product(product_name, query):
                        continue
                    
                    # Extract price
                    price_elem = product.select_one("span.a-price > span.a-offscreen")
                    if not price_elem:
                        price_elem = product.select_one("span.a-price-whole")
                    
                    price_text = price_elem.text.strip() if price_elem else ""
                    price = self.clean_price(price_text)
                    
                    # Extract image URL
                    img_elem = product.select_one("img.s-image")
                    img_url = img_elem.get("src") if img_elem else None
                    
                    # Extract additional info
                    rating_elem = product.select_one("span.a-icon-alt")
                    rating = rating_elem.text.strip() if rating_elem else None
                    
                    reviews_elem = product.select_one("span.a-size-base.s-underline-text")
                    reviews = reviews_elem.text.strip() if reviews_elem else None
                    
                    # Create result
                    result = {
                        "link": link,
                        "price": price,
                        "currency": currency,
                        "productName": product_name,
                        "source": f"Amazon {country}",
                        "imageUrl": img_url,
                        "additionalInfo": {
                            "rating": rating,
                            "reviews": reviews
                        }
                    }
                    
                    results.append(result)
                    
                except Exception as e:
                    logger.error(f"Error processing Amazon product: {str(e)}")
                    continue
            
            # If results are empty or few, try using AI to parse the page
            if len(results) < 3 and self.ai_helper.api_key:
                try:
                    ai_result = await self._extract_with_ai(html_content, search_url, query)
                    if ai_result:
                        results.extend(ai_result)
                except Exception as e:
                    logger.error(f"Error using AI to extract Amazon products: {str(e)}")
            
            return results
                
        except Exception as e:
            logger.error(f"Error searching Amazon: {str(e)}")
            return results
    
    def _extract_currency(self, html_content: str, country: str) -> str:
        """Extract currency from HTML content."""
        # Default currency mapping based on country
        country_currency = {
            "US": "USD",
            "UK": "GBP",
            "DE": "EUR",
            "FR": "EUR",
            "ES": "EUR",
            "IT": "EUR",
            "JP": "JPY",
            "IN": "INR",
            "CA": "CAD",
            "AU": "AUD",
        }
        
        # Try to extract from HTML
        currency_match = re.search(r'ppu-currency">(\w+)<', html_content)
        if currency_match:
            return currency_match.group(1)
        
        # Use price symbol pattern
        symbol_match = re.search(r'a-price-symbol">([^<]+)<', html_content)
        if symbol_match:
            symbol = symbol_match.group(1).strip()
            symbol_to_currency = {
                "$": "USD",
                "£": "GBP",
                "€": "EUR",
                "¥": "JPY",
                "₹": "INR",
            }
            return symbol_to_currency.get(symbol, country_currency.get(country.upper(), "USD"))
        
        # Fall back to country-based currency
        return country_currency.get(country.upper(), "USD")
    
    async def _extract_with_ai(self, html_content: str, url: str, query: str) -> list:
        if not self.ai_helper.api_key:
            return []
        try:
            truncated_html = html_content[:15000] + "..." if len(html_content) > 15000 else html_content
            prompt = f"""
            You are a web scraping assistant. Extract up to 5 product listings from this Amazon search results page.\nSearch URL: {url}\nSearch Query: {query}\nHTML Content (truncated):\n{truncated_html}\nFor each product found, return a JSON list of objects with: productName, price, currency, link, imageUrl, additionalInfo (should be a dictionary or null). Only include products that match the search query.
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
                results = []
                if isinstance(parsed_results, list):
                    for item in parsed_results:
                        if isinstance(item, dict) and "productName" in item and "price" in item:
                            item["source"] = url.split("//")[1].split("/")[0]
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
                            results.append(item)
                logger.debug(f"Final results to return: {results}")
                return results
            except Exception as e:
                logger.error(f"Failed to parse Gemini JSON: {e}\nRaw: {answer}")
                return []
        except Exception as e:
            logger.error(f"Error extracting Amazon products with AI: {str(e)}")
            return [] 