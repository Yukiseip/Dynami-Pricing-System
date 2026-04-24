"""
main.py — FastAPI Application para el Sistema de Dynamic Pricing

Endpoints:
    GET /health                          → Estado del sistema
    GET /pricing/suggestion/{product_id} → Sugerencia individual
    GET /pricing/batch                   → Consulta masiva con filtros
    GET /matches/pending                 → Matches pendientes de revisión
"""
import os
from contextlib import asynccontextmanager
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .schemas import (
    PricingSuggestion, BatchSuggestionItem,
    MatchPendingItem, HealthResponse
)
from ..ingestion.db_utils import get_engine
from ..matching.embeddings import get_qdrant_client


# ============================================================
# APP LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización al arrancar la API."""
    logger.info("🚀 Iniciando Dynamic Pricing API...")
    yield
    logger.info("🛑 Cerrando Dynamic Pricing API...")


app = FastAPI(
    title="Dynamic Pricing API",
    description="Motor de pricing dinámico para e-commerce de electrónica.",
    version="1.0.0",
    lifespan=lifespan,
)

# Determinar los orígenes permitidos por seguridad (CORS)
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8501,http://127.0.0.1:8501"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Verifica el estado de todos los componentes del sistema.
    Chequea: PostgreSQL, Qdrant, y conteos de tablas Gold.
    """
    engine = get_engine()
    status = {"postgres": "ok", "qdrant": "ok"}

    # Verificar PostgreSQL
    try:
        total = pd.read_sql(
            "SELECT COUNT(*) as n FROM gold.fct_pricing_signals", engine
        ).iloc[0]["n"]
        suggestions = pd.read_sql(
            "SELECT COUNT(*) as n FROM gold.pricing_recommendations", engine
        ).iloc[0]["n"]
        last_run_df = pd.read_sql(
            "SELECT MAX(computed_at) as last FROM gold.pricing_recommendations", engine
        )
        last_run = last_run_df.iloc[0]["last"] if not last_run_df.empty else None
    except Exception as e:
        status["postgres"] = f"error: {e}"
        total = 0
        suggestions = 0
        last_run = None

    # Verificar Qdrant
    try:
        client = get_qdrant_client()
        client.get_collections()
    except Exception as e:
        status["qdrant"] = f"error: {e}"

    overall = "healthy" if all(v == "ok" for v in status.values()) else "degraded"

    return HealthResponse(
        status=overall,
        postgres=status["postgres"],
        qdrant=status["qdrant"],
        last_pricing_run=last_run,
        total_products=int(total),
        products_with_suggestions=int(suggestions),
    )


@app.get("/pricing/suggestion/{product_id}", response_model=PricingSuggestion, tags=["Pricing"])
async def get_pricing_suggestion(product_id: str):
    """
    Retorna la sugerencia de precio para un producto específico.
    Combina datos de gold.pricing_recommendations y gold.fct_pricing_signals.
    """
    engine = get_engine()

    query = """
        SELECT
            r.product_id,
            s.name_original AS name,
            s.category,
            r.current_price,
            r.suggested_price,
            r.price_delta,
            r.action,
            r.reasoning,
            r.confidence,
            r.min_allowed_price,
            s.avg_comp_price,
            s.min_comp_price,
            s.stock,
            s.stock_status,
            r.computed_at
        FROM gold.pricing_recommendations r
        JOIN gold.fct_pricing_signals s ON r.product_id = s.product_id
        WHERE r.product_id = %(product_id)s
        LIMIT 1
    """

    try:
        df = pd.read_sql(query, engine, params={"product_id": product_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {e}")

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Producto {product_id} no encontrado o sin recomendación calculada"
        )

    row = df.iloc[0]
    price_change_pct = (
        (row["suggested_price"] - row["current_price"]) / row["current_price"] * 100
        if row["current_price"] > 0 else 0.0
    )

    return PricingSuggestion(
        product_id=row["product_id"],
        name=row["name"],
        category=row["category"],
        current_price=float(row["current_price"]),
        suggested_price=float(row["suggested_price"]),
        price_change_pct=round(float(price_change_pct), 2),
        action=row["action"],
        reasoning=row["reasoning"],
        confidence=row["confidence"],
        min_allowed_price=float(row["min_allowed_price"]),
        avg_competitor_price=float(row["avg_comp_price"]) if pd.notna(row.get("avg_comp_price")) else None,
        min_competitor_price=float(row["min_comp_price"]) if pd.notna(row.get("min_comp_price")) else None,
        stock=int(row["stock"]),
        stock_status=row["stock_status"],
        computed_at=row.get("computed_at"),
    )


@app.get("/pricing/batch", response_model=list[BatchSuggestionItem], tags=["Pricing"])
async def get_pricing_batch(
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    action: Optional[str] = Query(None, description="Filtrar por acción: increase|decrease|maintain"),
    confidence: Optional[str] = Query(None, description="Filtrar por confianza: high|medium|low"),
    limit: int = Query(100, ge=1, le=1000, description="Límite de resultados"),
):
    """
    Retorna múltiples sugerencias de precio con filtros opcionales.
    Ordenado por magnitud de cambio de precio descendente.
    """
    engine = get_engine()

    conditions = ["1=1"]
    params = {}

    if category:
        conditions.append("s.category ILIKE %(category)s")
        params["category"] = f"%{category}%"
    if action:
        conditions.append("r.action = %(action)s")
        params["action"] = action
    if confidence:
        conditions.append("r.confidence = %(confidence)s")
        params["confidence"] = confidence

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            r.product_id,
            s.name_original AS name,
            s.category,
            r.current_price,
            r.suggested_price,
            r.price_delta,
            r.action,
            r.confidence
        FROM gold.pricing_recommendations r
        JOIN gold.fct_pricing_signals s ON r.product_id = s.product_id
        WHERE {where_clause}
        ORDER BY ABS(r.price_delta) DESC
        LIMIT %(limit)s
    """
    params["limit"] = limit

    try:
        df = pd.read_sql(query, engine, params=params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {e}")

    return [
        BatchSuggestionItem(
            product_id=row["product_id"],
            name=row["name"],
            category=row["category"],
            current_price=float(row["current_price"]),
            suggested_price=float(row["suggested_price"]),
            price_delta=float(row["price_delta"]),
            action=row["action"],
            confidence=row["confidence"],
        )
        for _, row in df.iterrows()
    ]


@app.get("/matches/pending", response_model=list[MatchPendingItem], tags=["Matching"])
async def get_pending_matches(
    limit: int = Query(50, ge=1, le=500),
):
    """
    Retorna matches de productos pendientes de revisión manual.
    Estos son matches con similarity_score entre 0.70 y 0.85.
    """
    engine = get_engine()

    query = """
        SELECT
            m.own_product_id,
            p.name_original AS own_product_name,
            m.competitor_name,
            m.competitor_id,
            m.similarity_score,
            m.category
        FROM silver.product_matches m
        LEFT JOIN silver.stg_products p ON m.own_product_id = p.product_id
        WHERE m.status = 'review'
        ORDER BY m.similarity_score DESC
        LIMIT %(limit)s
    """

    try:
        df = pd.read_sql(query, engine, params={"limit": limit})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {e}")

    return [
        MatchPendingItem(
            own_product_id=row["own_product_id"],
            own_product_name=row.get("own_product_name", row["own_product_id"]),
            competitor_name=row["competitor_name"],
            competitor_id=row["competitor_id"],
            similarity_score=float(row["similarity_score"]),
            category=row["category"],
        )
        for _, row in df.iterrows()
    ]
