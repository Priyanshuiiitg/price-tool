from typing import List, Dict, Any
import urllib.parse
import re
from src.scraper.base_scraper import BaseScraper
from src.utils.logger import get_logger
from src.utils.ai_helper import AIHelper

logger = get_logger(__name__)

class FlipkartScraper(BaseScraper):
    """Scraper for Flipkart website."""
    
    name = "flipkart"
    supported_countries = ["IN"]  # Flipkart primarily serves India
    
    def __init__(self):
        super().__init__()
        self.ai_helper = AIHelper()
        # Update headers for Flipkart
        self.headers.update({
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })
    
    def get_search_url(self, country: str, query: str) -> str:
        """Get the Flipkart search URL for the given query."""
        encoded_query = urllib.parse.quote(query)
        return f"https://www.flipkart.com/search?q={encoded_query}"
    
    async def search(self, country: str, query: str) -> List[Dict[str, Any]]:
        """Search for products on Flipkart."""
        results = []
        
        if country.upper() != "IN":
            logger.info(f"Flipkart primarily serves India, not {country}. Skipping.")
            return []
            
        try:
            search_url = self.get_search_url(country, query)
            logger.info(f"Searching Flipkart: {search_url}")
            
            # Fetch search results page
            html_content = await self.fetch_html(search_url)
            if not html_content:
                logger.error(f"Failed to fetch Flipkart search results for {query}")
                return []
            
            # Parse HTML
            soup = self.parse_html(html_content)
            
            # Find all product items
            products = soup.select("div._1AtVbE")
            
            # Process each product
            for product in products[:10]:  # Limit to 10 products
                try:
                    # Extract product link
                    link_elem = product.select_one("a._1fQZEK, a._2rpwqI, a.s1Q9rs")
                    if not link_elem:
                        continue
                    
                    link = link_elem.get("href")
                    if link and link.startswith("/"):
                        link = f"https://www.flipkart.com{link}"
                    
                    # Extract product name
                    name_elem = product.select_one("div._4rR01T, a.s1Q9rs, div._2WkVRV")
                    product_name = name_elem.text.strip() if name_elem else ""
                    
                    # Skip if product name doesn't match query
                    if not product_name or not self.match_product(product_name, query):
                        continue
                    
                    # Extract price
                    price_elem = product.select_one("div._30jeq3._1_WHN1, div._30jeq3")
                    price_text = price_elem.text.strip() if price_elem else ""
                    price = self.clean_price(price_text)
                    
                    # Extract image URL
                    img_elem = product.select_one("img._396cs4, img._2r_T1I")
                    img_url = img_elem.get("src") if img_elem else None
                    
                    # Extract additional info
                    rating_elem = product.select_one("div._3LWZlK")
                    rating = rating_elem.text.strip() if rating_elem else None
                    
                    reviews_elem = product.select_one("span._2_R_DZ")
                    reviews = reviews_elem.text.strip() if reviews_elem else None
                    
                    # Create result
                    result = {
                        "link": link,
                        "price": price,
                        "currency": "INR",  # Flipkart uses INR
                        "productName": product_name,
                        "source": "Flipkart",
                        "imageUrl": img_url,
                        "additionalInfo": {
                            "rating": rating,
                            "reviews": reviews
                        }
                    }
                    
                    results.append(result)
                    
                except Exception as e:
                    logger.error(f"Error processing Flipkart product: {str(e)}")
                    continue
            
            # If results are empty or few, try using AI to parse the page
            if len(results) < 3 and self.ai_helper.api_key:
                try:
                    ai_result = await self._extract_with_ai(html_content, search_url, query)
                    if ai_result:
                        results.extend(ai_result)
                except Exception as e:
                    logger.error(f"Error using AI to extract Flipkart products: {str(e)}")
            
            return results
                
        except Exception as e:
            logger.error(f"Error searching Flipkart: {str(e)}")
            return results
            
    async def _extract_with_ai(self, html_content: str, url: str, query: str) -> list:
        if not self.ai_helper.api_key:
            return []
        try:
            truncated_html = html_content[:15000] + "..." if len(html_content) > 15000 else html_content
            prompt = f"""
            You are a web scraping assistant. Extract up to 5 product listings from this Flipkart search results page.\nSearch URL: {url}\nSearch Query: {query}\nHTML Content (truncated):\n{truncated_html}\nFor each product found, return a JSON list of objects with: productName, price, currency, link, imageUrl, additionalInfo (should be a dictionary or null). Only include products that match the search query.
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
                            item["source"] = "Flipkart"
                            if "currency" not in item:
                                item["currency"] = "INR"
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
            logger.error(f"Error extracting Flipkart products with AI: {str(e)}")
            return [] 