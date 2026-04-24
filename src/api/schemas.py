"""schemas.py — Modelos Pydantic para request/response de la API."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class PricingSuggestion(BaseModel):
    product_id: str
    name: str
    category: str
    current_price: float
    suggested_price: float
    price_change_pct: float
    action: str  # 'increase', 'decrease', 'maintain'
    reasoning: str
    confidence: str
    min_allowed_price: float
    avg_competitor_price: Optional[float] = None
    min_competitor_price: Optional[float] = None
    stock: int
    stock_status: str
    computed_at: Optional[datetime] = None


class BatchSuggestionItem(BaseModel):
    product_id: str
    name: str
    category: str
    current_price: float
    suggested_price: float
    price_delta: float
    action: str
    confidence: str


class MatchPendingItem(BaseModel):
    own_product_id: str
    own_product_name: str
    competitor_name: str
    competitor_id: str
    similarity_score: float
    category: str


class HealthResponse(BaseModel):
    status: str
    postgres: str
    qdrant: str
    last_pricing_run: Optional[datetime] = None
    total_products: int
    products_with_suggestions: int
