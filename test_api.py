#!/usr/bin/env python
import asyncio
import httpx
import argparse
import json
from typing import Dict, Any

async def search_products(country: str, query: str) -> Dict[str, Any]:
    """
    Search for products using the API.
    
    Args:
        country: The country code (e.g., US, IN)
        query: The product search query
    
    Returns:
        The API response as a dictionary
    """
    url = "http://localhost:8000/search"
    payload = {
        "country": country,
        "query": query
    }
    
    print(f"Searching for {query} in {country}...")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return None

def format_result(result: Dict[str, Any]) -> str:
    """Format a single result for display."""
    output = []
    output.append(f"Product: {result.get('productName', 'N/A')}")
    output.append(f"Price: {result.get('price', 'N/A')} {result.get('currency', '')}")
    output.append(f"Source: {result.get('source', 'N/A')}")
    output.append(f"Link: {result.get('link', 'N/A')}")
    
    if result.get('additionalInfo'):
        additional = result['additionalInfo']
        if isinstance(additional, dict):
            for key, value in additional.items():
                if value:
                    output.append(f"{key.capitalize()}: {value}")
    
    return "\n".join(output)

async def main():
    parser = argparse.ArgumentParser(description="Test the Product Price Comparison API")
    parser.add_argument("--country", "-c", type=str, required=True, help="Country code (e.g., US, IN)")
    parser.add_argument("--query", "-q", type=str, required=True, help="Product search query")
    parser.add_argument("--json", "-j", action="store_true", help="Output in JSON format")
    
    args = parser.parse_args()
    
    results = await search_products(args.country, args.query)
    
    if not results:
        print("No results found.")
        return
    
    if args.json:
        # Pretty print JSON
        print(json.dumps(results, indent=2))
        return
    
    # Print formatted results
    print(f"\nFound {len(results)} results:\n")
    
    for i, result in enumerate(results, 1):
        print(f"Result #{i}:")
        print(format_result(result))
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main()) 