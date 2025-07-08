import os
import httpx
from typing import List, Dict, Any
from dotenv import load_dotenv
from src.utils.logger import get_logger

# Load environment variables
load_dotenv()

logger = get_logger(__name__)

class AIHelper:
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        if not self.api_key:
            logger.warning("Google API key not found, AI functionality will be limited")

    async def _call_gemini(self, prompt: str) -> str:
        if not self.api_key:
            logger.warning("No Google API key set.")
            return ""
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}
        data = {
            "contents": [
                {"parts": [{"text": prompt}]}
            ]
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.api_url, headers=headers, params=params, json=data, timeout=30)
                resp.raise_for_status()
                result = resp.json()
                # Gemini returns candidates[0].content.parts[0].text
                return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ""

    async def is_product_match(self, product_name: str, product_description: str, search_query: str) -> bool:
        prompt = f"""
        You are a shopping assistant. Product Name: {product_name}\nProduct Description: {product_description}\nUser's Search Query: {search_query}\nIs this product a good match for the user's search query? Answer only yes or no.
        """
        answer = await self._call_gemini(prompt)
        return "yes" in answer.lower()

    async def generate_search_queries(self, query: str, country: str) -> List[str]:
        prompt = f"""
        Original Search Query: {query}\nCountry: {country}\nGenerate 3-5 alternative search queries for this product in the given country. Return only the queries, one per line.
        """
        answer = await self._call_gemini(prompt)
        queries = [line.strip() for line in answer.split("\n") if line.strip()]
        if query not in queries:
            queries.insert(0, query)
        return queries

    async def extract_product_details(self, html_content: str, url: str, query: str) -> Dict[str, Any]:
        if not html_content:
            return None
        truncated_html = html_content[:10000] + "..." if len(html_content) > 10000 else html_content
        prompt = f"""
        You are a web scraping assistant. Extract product information from the HTML below.\nProduct Page URL: {url}\nSearch Query: {query}\nHTML Content (truncated):\n{truncated_html}\nReturn JSON with: productName, price, currency, imageUrl, additionalInfo. Use null for missing fields.
        """
        answer = await self._call_gemini(prompt)
        import json
        try:
            # Try to extract JSON from the answer
            import re
            match = re.search(r'\{.*\}', answer, re.DOTALL)
            if match:
                answer = match.group(0)
            return json.loads(answer)
        except Exception as e:
            logger.error(f"Failed to parse Gemini JSON: {e}\nRaw: {answer}")
            return None 