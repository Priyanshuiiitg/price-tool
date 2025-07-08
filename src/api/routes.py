from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from src.utils.google_custom_search import search_products_google
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["products"])

class ProductSearchQuery(BaseModel):
    country: str
    query: str

class ProductPriceResponse(BaseModel):
    link: str
    price: str
    currency: str
    productName: str
    source: str
    imageUrl: str = None
    additionalInfo: Optional[Dict[str, Any]] = None

def estimate_price(product, query):
    """Add estimated price based on product type and name."""
    product_name = product.get('productName', '').lower()
    
    # Skip if already has a price
    if product.get('price'):
        return product
        
    # Simple price estimation based on product type and brand
    if 'apple watch' in product_name or 'apple' in product.get('source', '').lower():
        product['price'] = '399'
        if not product.get('additionalInfo'):
            product['additionalInfo'] = {}
        product['additionalInfo']['priceEstimated'] = True
    elif 'garmin' in product_name or 'garmin' in product.get('source', '').lower():
        product['price'] = '299'
        if not product.get('additionalInfo'):
            product['additionalInfo'] = {}
        product['additionalInfo']['priceEstimated'] = True
    elif 'amazfit' in product_name or 'amazfit' in product.get('source', '').lower():
        product['price'] = '149'
        if not product.get('additionalInfo'):
            product['additionalInfo'] = {}
        product['additionalInfo']['priceEstimated'] = True
    elif 'fitbit' in product_name or 'fitbit' in product.get('source', '').lower():
        product['price'] = '199'
        if not product.get('additionalInfo'):
            product['additionalInfo'] = {}
        product['additionalInfo']['priceEstimated'] = True
    elif any(luxury in product_name for luxury in ['omega', 'tudor', 'vacheron', 'constantin', 'luxury']):
        product['price'] = '2999'
        if not product.get('additionalInfo'):
            product['additionalInfo'] = {}
        product['additionalInfo']['priceEstimated'] = True
    elif 'smartwatch' in product_name or 'smart watch' in product_name or 'smartwatch' in query.lower():
        product['price'] = '149'
        if not product.get('additionalInfo'):
            product['additionalInfo'] = {}
        product['additionalInfo']['priceEstimated'] = True
        
    return product

@router.post("/search", response_model=List[ProductPriceResponse])
async def search_products(query: ProductSearchQuery):
    """
    Search for products using Google Custom Search API based on the country and query.
    """
    try:
        logger.info(f"Searching for {query.query} in {query.country} using Google Custom Search API")
        results = await search_products_google(query.query, query.country)
        
        if not results:
            logger.warning(f"No results found for {query.query} in {query.country}")
            return []
        
        # Add estimated prices for items without prices
        results = [estimate_price(item, query.query) for item in results]
            
        # Sort results by price (ascending)
        # Convert price to float for sorting, handle potential issues with conversion
        def get_price_for_sorting(item):
            try:
                return float(item.get("price", "0").replace(",", ""))
            except (ValueError, AttributeError):
                return float(0)
                
        sorted_results = sorted(results, key=get_price_for_sorting)
        logger.info(f"Found {len(sorted_results)} results for {query.query}")
        
        return sorted_results
    except Exception as e:
        logger.error(f"Error searching products with Google API: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching products: {str(e)}") 