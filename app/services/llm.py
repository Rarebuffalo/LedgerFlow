import os
import json
import time
import logging
from enum import Enum
from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
import google.generativeai as genai

# Setup Logger
logger = logging.getLogger(__name__)

class AllowedCategory(str, Enum):
    FOOD = "Food"
    SHOPPING = "Shopping"
    TRAVEL = "Travel"
    TRANSPORT = "Transport"
    UTILITIES = "Utilities"
    CASH_WITHDRAWAL = "Cash Withdrawal"
    ENTERTAINMENT = "Entertainment"
    OTHER = "Other"

class CategoryResponse(BaseModel):
    merchant: str
    category: AllowedCategory

class TopMerchantItem(BaseModel):
    merchant: str
    total_spend: float
    transaction_count: int

class SummaryResponse(BaseModel):
    total_spend_inr: float
    total_spend_usd: float
    top_merchants: List[TopMerchantItem]
    anomaly_count: int
    narrative: str = Field(..., min_length=20)
    risk_level: Literal["low", "medium", "high"]

def clean_json_response(text: str) -> str:
    """
    Strips markdown code blocks (e.g. ```json ... ```) from LLM output.
    """
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set. LLM features will fall back or fail.")
        return None
    genai.configure(api_key=api_key)
    # Using 1.5 Flash as the standard light-weight model
    return genai.GenerativeModel("gemini-1.5-flash")

def call_gemini_with_retry(prompt: str, max_retries: int = 3, initial_backoff: float = 1.0) -> str:
    """
    Invokes Gemini API with exponential backoff on failure.
    """
    model = get_gemini_client()
    if not model:
        raise ValueError("Gemini API key is missing.")
        
    backoff = initial_backoff
    last_err = None
    for attempt in range(1, max_retries + 2):
        try:
            logger.info(f"Calling Gemini API (Attempt {attempt}/{max_retries + 1})")
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
            raise ValueError("Empty response text returned from Gemini API")
        except Exception as e:
            last_err = e
            logger.error(f"Gemini call failed on attempt {attempt}: {str(e)}")
            if attempt <= max_retries:
                sleep_time = backoff * (2 ** (attempt - 1))
                logger.info(f"Sleeping for {sleep_time} seconds before retry...")
                time.sleep(sleep_time)
                
    raise last_err

def batch_classify_merchants(merchants: List[str]) -> Dict[str, str]:
    """
    Sends unique merchants in bulk to Gemini to classify them into standard categories.
    Validates the result using Pydantic. Returns a merchant-to-category mapping.
    """
    if not merchants:
        return {}
        
    prompt = f"""
Classify the following merchant names into exactly one of these spending categories:
- Food
- Shopping
- Travel
- Transport
- Utilities
- Cash Withdrawal
- Entertainment
- Other

Input merchants:
{json.dumps(merchants)}

You MUST return a JSON array of objects. Each object must have exactly the "merchant" and "category" keys.
Do not use markdown blocks or formatting. Return only the raw JSON array.
Example response:
[
  {{"merchant": "Swiggy", "category": "Food"}},
  {{"merchant": "Jio Recharge", "category": "Utilities"}}
]
"""
    try:
        raw_response = call_gemini_with_retry(prompt)
        clean_response = clean_json_response(raw_response)
        parsed = json.loads(clean_response)
        
        # Pydantic validation
        validated = TypeAdapter(List[CategoryResponse]).validate_python(parsed)
        return {item.merchant: item.category.value for item in validated}
    except Exception as e:
        logger.error(f"Failed to batch classify merchants via LLM: {str(e)}")
        # Caller will handle marking llm_failed for these records
        raise e

def generate_spending_narrative(
    total_spend_inr: float,
    total_spend_usd: float,
    top_merchants: List[Dict[str, Any]],
    anomaly_count: int
) -> SummaryResponse:
    """
    Sends processed metrics to Gemini to produce a structured summary including narrative and risk level.
    """
    prompt = f"""
You are a senior financial intelligence analyst. Analyze the following aggregated transaction metrics and generate:
1. A concise 2-to-3 sentence spending narrative summarizing key observations (e.g. major spend drivers, suspicious trends).
2. An overall risk level rating (low, medium, high) based on the presence of anomalies and total spend.

Transaction Metrics:
- Total Spend in INR: {total_spend_inr}
- Total Spend in USD: {total_spend_usd}
- Top Merchants: {json.dumps(top_merchants)}
- Anomaly Count: {anomaly_count}

You MUST return a valid JSON object matching the following schema:
{{
  "total_spend_inr": {total_spend_inr},
  "total_spend_usd": {total_spend_usd},
  "top_merchants": {json.dumps(top_merchants)},
  "anomaly_count": {anomaly_count},
  "narrative": "Your 2-3 sentence narrative here.",
  "risk_level": "low" | "medium" | "high"
}}

Return ONLY raw JSON. No markdown syntax or explanations.
"""
    try:
        raw_response = call_gemini_with_retry(prompt)
        clean_response = clean_json_response(raw_response)
        parsed = json.loads(clean_response)
        
        # Pydantic validation
        validated = SummaryResponse.model_validate(parsed)
        return validated
    except Exception as e:
        logger.error(f"Failed to generate narrative summary via LLM: {str(e)}")
        raise e
