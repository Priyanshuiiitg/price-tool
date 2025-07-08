"""
Google Custom Search JSON API utility for product search.

Required environment variables:
- GOOGLE_CUSTOM_SEARCH_API_KEY
- GOOGLE_CUSTOM_SEARCH_CSE_ID

Usage:
    from src.utils.google_custom_search import search_products_google
    results = await search_products_google(query, country, api_key, cse_id)
"""
import os
import aiohttp
import re
import json
from typing import List, Dict, Any
from src.utils.logger import get_logger
from src.utils.ai_helper import AIHelper

logger = get_logger(__name__)
ai_helper = AIHelper()

# Regular expressions for price extraction
PRICE_PATTERNS = [
    r'[\$\£\€\¥\₹]\s*[\d,]+\.?\d*',  # $123.45, $1,234.56
    r'[\d,]+\.?\d*\s*[\$\£\€\¥\₹]',  # 123.45$, 1,234.56$
    r'[\d,]+\.?\d*\s*USD|EUR|GBP|JPY|INR',  # 123.45 USD
    r'price[^\d]*[\$\£\€\¥\₹]?\s*[\d,]+\.?\d*',  # price: $123.45, price $123
    r'price[^\d]*[\d,]+\.?\d*\s*[\$\£\€\¥\₹]?',  # price: 123.45$, price 123
    r'[\$\£\€\¥\₹]?[^\d]*[\d,]+\.?\d*',  # $123.45, 123.45
    r'cost[^\d]*[\$\£\€\¥\₹]?\s*[\d,]+\.?\d*',  # cost: $123.45
    r'[\d,]+\.?\d*\s*dollars|rupees|euros|pounds',  # 123.45 dollars
    r'starting at\s*[\$\£\€\¥\₹]?\s*[\d,]+\.?\d*',  # starting at $123.45
    r'from\s*[\$\£\€\¥\₹]?\s*[\d,]+\.?\d*',  # from $123.45
]

CURRENCY_MAP = {
    '$': 'USD',
    '£': 'GBP',
    '€': 'EUR',
    '¥': 'JPY',
    '₹': 'INR',
    'USD': 'USD',
    'EUR': 'EUR',
    'GBP': 'GBP',
    'JPY': 'JPY',
    'INR': 'INR',
}

# Country to currency mapping
COUNTRY_CURRENCY = {
    'us': 'USD',
    'uk': 'GBP',
    'gb': 'GBP',
    'de': 'EUR',
    'fr': 'EUR',
    'it': 'EUR',
    'es': 'EUR',
    'jp': 'JPY',
    'in': 'INR',
    'ca': 'CAD',
    'au': 'AUD',
}

def is_likely_year_not_price(price_str: str, text: str) -> bool:
    """Check if a numeric string is likely a year rather than a price."""
    # If empty or not a valid number, it's not a year
    if not price_str or not price_str.isdigit():
        return False
        
    price_num = int(price_str)
    
    # If the price is a 4-digit number between 1800 and 2030, check if it appears in context as a year
    if 1800 <= price_num <= 2030:
        # Check if the number appears in the text with year context
        year_patterns = [
            rf"since\s*{price_str}",
            rf"est\.?\s*{price_str}",
            rf"established\s*{price_str}",
            rf"founded\s*{price_str}",
            rf"{price_str}\s*®",
            rf"watches since {price_str}",
            rf"since\s+{price_str}",
            rf"in\s+{price_str}",
            rf"from\s+{price_str}",
            rf"{price_str}\s+[Ee]dition",
            rf"{price_str}\s+[Cc]ollection",
        ]
        
        # Check if the number appears in product name or title as a year
        for pattern in year_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                logger.debug(f"Detected year {price_str} in text: {text[:50]}...")
                return True
                
        # Special case: if the number is exactly 1755, 1848, 1926 (common watch founding years)
        if price_num in [1755, 1848, 1926, 1884, 1875, 1905]:
            if "watches" in text.lower() or "watch" in text.lower():
                logger.debug(f"Detected known watch brand founding year {price_str}")
                return True
    
    return False

def extract_price_from_text(text: str) -> tuple:
    """Extract price and currency from text using regex patterns."""
    if not text:
        return '', ''
    
    for pattern in PRICE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            price_str = matches[0]
            # Extract currency symbol or code
            currency = ''
            for symbol, code in CURRENCY_MAP.items():
                if symbol in price_str:
                    currency = code
                    break
            
            # Clean up price string to just numbers
            price = re.sub(r'[^\d.,]', '', price_str)
            # Remove trailing dots or commas
            price = price.rstrip('.,')
            # If price is empty after cleaning, skip
            if not price:
                continue
                
            # Check if this is likely a year rather than a price
            if is_likely_year_not_price(price, text):
                continue
                
            return price, currency
    
    return '', ''

async def search_products_google(query: str, country: str, api_key: str = None, cse_id: str = None) -> List[Dict[str, Any]]:
    """Search for products using Google Custom Search API."""
    api_key = api_key or os.getenv('GOOGLE_CUSTOM_SEARCH_API_KEY')
    cse_id = cse_id or os.getenv('GOOGLE_CUSTOM_SEARCH_CSE_ID')
    if not api_key or not cse_id:
        logger.error("Google Custom Search API key or CSE ID not set")
        raise ValueError("Google Custom Search API key and CSE ID must be set.")
    
    country_code = country.lower()
    default_currency = COUNTRY_CURRENCY.get(country_code, 'USD')
    
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': api_key,
        'cx': cse_id,
        'q': f"{query} price buy online",  # Optimize query for product search
        'gl': country_code,  # country code
        'num': 10,
    }
    
    results = []
    logger.info(f"Querying Google Custom Search API for '{query}' in {country}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Google Custom Search API error: {resp.status} {text}")
                    raise Exception(f"Google Custom Search API error: {resp.status} {text}")
                
                data = await resp.json()
                logger.info(f"Google Custom Search returned {len(data.get('items', []))} results")
                
                for item in data.get('items', []):
                    try:
                        # Try to extract product info from snippet, pagemap, etc.
                        pagemap = item.get('pagemap', {})
                        product = pagemap.get('product', [{}])[0] if 'product' in pagemap else {}
                        offer = pagemap.get('offer', [{}])[0] if 'offer' in pagemap else {}
                        metatags = pagemap.get('metatags', [{}])[0] if 'metatags' in pagemap else {}
                        
                        # Extract price from structured data
                        price = offer.get('price') or product.get('price') or ''
                        currency = offer.get('pricecurrency') or product.get('pricecurrency') or ''
                        
                        # If no structured price, try to extract from title, snippet, or description
                        if not price:
                            title = item.get('title', '')
                            snippet = item.get('snippet', '')
                            desc = item.get('pagemap', {}).get('metatags', [{}])[0].get('og:description', '')
                            
                            # Check for years in title and snippet to avoid misidentifying them as prices
                            full_text = f"{title} {snippet} {desc}"
                            
                            # Extract "Since XXXX" pattern and skip if found
                            since_year_match = re.search(r'[Ss]ince\s+(\d{4})', full_text)
                            if since_year_match:
                                logger.debug(f"Skipping 'Since {since_year_match.group(1)}' in {item.get('title')}")
                                # Don't use this number as price
                            else:
                                title_price, title_currency = extract_price_from_text(title)
                                snippet_price, snippet_currency = extract_price_from_text(snippet)
                                desc_price, desc_currency = extract_price_from_text(desc)
                                
                                # Check if any extracted price is actually a year
                                if title_price and is_likely_year_not_price(title_price, full_text):
                                    logger.debug(f"Skipping likely year {title_price} in {title}")
                                    title_price = ''
                                    
                                if snippet_price and is_likely_year_not_price(snippet_price, full_text):
                                    logger.debug(f"Skipping likely year {snippet_price} in snippet")
                                    snippet_price = ''
                                    
                                price = title_price or snippet_price or desc_price
                                currency = title_currency or snippet_currency or desc_currency or default_currency
                        
                        # Always set the default currency if none found
                        if not currency:
                            currency = default_currency
                            
                        # Special case: check if product name contains "Since XXXX" and price matches that year
                        if price and "since" in item.get('title', '').lower() + item.get('snippet', '').lower():
                            year_match = re.search(r'[Ss]ince\s+(\d{4})', item.get('title', '') + item.get('snippet', ''))
                            if year_match and price == year_match.group(1):
                                logger.debug(f"Clearing price {price} that matches 'Since XXXX' year")
                                price = ''
                        
                        # Extract image URL
                        image_url = ''
                        if 'cse_image' in pagemap and pagemap['cse_image']:
                            image_url = pagemap['cse_image'][0].get('src', '')
                        elif 'imageobject' in pagemap and pagemap['imageobject']:
                            image_url = pagemap['imageobject'][0].get('url', '')
                        elif 'og:image' in metatags:
                            image_url = metatags.get('og:image', '')
                        
                        # Extract product name
                        product_name = product.get('name') or metatags.get('og:title') or item.get('title', '')
                        
                        # Create result
                        result = {
                            'link': item.get('link', ''),
                            'price': price,
                            'currency': currency,
                            'productName': product_name,
                            'source': item.get('displayLink', ''),
                            'imageUrl': image_url,
                            'additionalInfo': {
                                'snippet': item.get('snippet', ''),
                                'brand': product.get('brand') or metatags.get('og:brand', ''),
                                'rating': product.get('ratingvalue', ''),
                                'reviews': product.get('reviewcount', ''),
                            }
                        }
                        
                        # Ensure all required fields are strings
                        for k in ['link', 'price', 'currency', 'productName', 'source', 'imageUrl']:
                            if result[k] is None:
                                result[k] = ''
                        
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Error processing search result: {e}")
                
                # If we have few results with price info, try using Gemini to extract more
                price_results = [r for r in results if r.get('price')]
                if len(price_results) < 3 and ai_helper.api_key and data.get('items'):
                    logger.info(f"Few structured price results found ({len(price_results)} of {len(results)}), using Gemini to extract more")
                    try:
                        gemini_results = await extract_with_gemini(data.get('items'), query, country_code)
                        if gemini_results:
                            # Merge with existing results, avoiding duplicates by URL
                            existing_urls = {r['link'] for r in results}
                            for r in gemini_results:
                                if r['link'] not in existing_urls:
                                    results.append(r)
                                    existing_urls.add(r['link'])
                    except Exception as e:
                        logger.error(f"Error using Gemini to extract product info: {e}")
        
        except Exception as e:
            logger.error(f"Error querying Google Custom Search API: {e}")
    
    logger.info(f"Returning {len(results)} products from Google Custom Search")
    return results

async def extract_with_gemini(search_items, query, country_code):
    """Use Gemini to extract product information from search results."""
    if not ai_helper.api_key:
        return []
    
    try:
        # Prepare search results for Gemini
        search_data = []
        for item in search_items[:5]:  # Limit to 5 items to avoid token limits
            search_data.append({
                "title": item.get('title', ''),
                "link": item.get('link', ''),
                "snippet": item.get('snippet', ''),
                "source": item.get('displayLink', '')
            })
        
        default_currency = COUNTRY_CURRENCY.get(country_code, 'USD')
        
        prompt = f"""
        You are a product information extractor specializing in finding prices. I have search results for "{query}" from {country_code}.
        Extract product information from these search results:
        {json.dumps(search_data, indent=2)}
        
        For each result, extract:
        1. Product name
        2. Price (just the number, VERY IMPORTANT - look carefully for any price mentions in the title and snippet)
        3. Currency (use {default_currency} if not specified)
        4. Link (use the exact link from the search result)
        5. Source website
        
        IMPORTANT INSTRUCTIONS:
        - Focus especially on finding prices. Look for patterns like "$199", "199 USD", "price: $199", "from $199", etc.
        - DO NOT use years (like 1926, 1848, 2025) as prices. These are founding years or model years, not prices.
        - For items without explicit prices, provide a reasonable estimate based on market rates for {query}.
        - For luxury watches (Omega, Tudor, etc.), estimate prices starting at $1000 USD or equivalent.
        - For smartwatches and fitness trackers, estimate prices between $100-500 USD or equivalent.
        - For Apple Watch, estimate prices starting at $399 USD or equivalent.
        
        Return a JSON array with objects containing these fields: productName, price, currency, link, source, imageUrl (leave empty).
        """
        
        answer = await ai_helper._call_gemini(prompt)
        logger.debug(f"Gemini raw answer: {answer}")
        
        # Extract JSON from Gemini's response
        import re
        match = re.search(r'\[.*\]', answer, re.DOTALL)
        if match:
            answer = match.group(0)
            
        try:
            parsed_results = json.loads(answer)
            logger.debug(f"Gemini parsed_results: {parsed_results}")
            results = []
            
            if isinstance(parsed_results, list):
                for item in parsed_results:
                    if isinstance(item, dict) and "link" in item:
                        # Ensure required fields exist
                        for field in ["productName", "price", "currency", "link", "source"]:
                            if field not in item:
                                item[field] = ""
                        
                        # Add imageUrl and additionalInfo if missing
                        if "imageUrl" not in item:
                            item["imageUrl"] = ""
                        if "additionalInfo" not in item:
                            item["additionalInfo"] = {}
                            
                        results.append(item)
            
            logger.info(f"Extracted {len(results)} products with Gemini")
            return results
            
        except Exception as e:
            logger.error(f"Failed to parse Gemini JSON: {e}\nRaw: {answer}")
            return []
            
    except Exception as e:
        logger.error(f"Error extracting products with Gemini: {e}")
        return [] 