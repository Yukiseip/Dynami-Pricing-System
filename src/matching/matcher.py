"""
matcher.py
==========
Algoritmo de matching automático entre productos propios y de competencia.
Usa búsqueda por similitud coseno en Qdrant con filtrado por categoría.

Umbrales:
    >= 0.85  → match aceptado automáticamente
    >= 0.70  → match pendiente de revisión manual
    < 0.70   → descartado
"""
import os
from dataclasses import dataclass

import pandas as pd
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

from .embeddings import (
    get_qdrant_client, get_embedding_model,
    build_product_text, COLLECTION_NAME,
)
from ingestion.db_utils import get_engine

SIMILARITY_THRESHOLD_ACCEPT = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))
SIMILARITY_THRESHOLD_REVIEW = float(os.getenv("SIMILARITY_REVIEW_THRESHOLD", "0.70"))
TOP_K = 3


@dataclass
class MatchResult:
    own_product_id: str
    own_product_name: str
    competitor_product_id: str
    competitor_name: str
    competitor_id: str
    similarity_score: float
    status: str  # 'accepted', 'review', 'rejected'
    category: str


def find_matches_for_product(
    product_id: str,
    product_name: str,
    category: str,
    model: SentenceTransformer,
    client: QdrantClient,
) -> list[MatchResult]:
    """Encuentra los mejores matches en competencia para un producto propio."""

    text = build_product_text(product_name, category)
    embedding = model.encode([text])[0].tolist()

    # Buscar en Qdrant filtrando por source=competitor y misma categoría
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=embedding,
        query_filter=Filter(
            must=[
                FieldCondition(key="source", match=MatchValue(value="competitor")),
                FieldCondition(key="category", match=MatchValue(value=category.title())),
            ]
        ),
        limit=TOP_K,
        with_payload=True,
    )

    matches = []
    for hit in results:
        score = hit.score
        if score < SIMILARITY_THRESHOLD_REVIEW:
            continue

        status = "accepted" if score >= SIMILARITY_THRESHOLD_ACCEPT else "review"

        matches.append(MatchResult(
            own_product_id=product_id,
            own_product_name=product_name,
            competitor_product_id=hit.payload.get("product_id", ""),
            competitor_name=hit.payload.get("name", ""),
            competitor_id=hit.payload.get("competitor_id", "unknown"),
            similarity_score=round(score, 4),
            status=status,
            category=category,
        ))

    return matches


def run_matching_pipeline() -> pd.DataFrame:
    """
    Ejecuta el pipeline completo de matching para todos los productos propios.

    Returns:
        DataFrame con todos los matches (aceptados + en revisión)
    """
    logger.info("Iniciando pipeline de matching de productos...")

    engine = get_engine()
    model = get_embedding_model()
    client = get_qdrant_client()

    # Cargar productos propios desde Silver
    products_df = pd.read_sql(
        "SELECT product_id, name_original AS name, category FROM silver.stg_products",
        engine
    )
    logger.info(f"  Productos a procesar: {len(products_df)}")

    all_matches = []
    accepted_count = 0
    review_count = 0

    for _, product in products_df.iterrows():
        matches = find_matches_for_product(
            product_id=product["product_id"],
            product_name=product["name"],
            category=product["category"],
            model=model,
            client=client,
        )
        all_matches.extend(matches)
        accepted_count += sum(1 for m in matches if m.status == "accepted")
        review_count += sum(1 for m in matches if m.status == "review")

    # Convertir a DataFrame
    if not all_matches:
        logger.warning("No se encontraron matches")
        return pd.DataFrame()

    results_df = pd.DataFrame([
        {
            "own_product_id": m.own_product_id,
            "own_product_name": m.own_product_name,
            "competitor_product_id": m.competitor_product_id,
            "competitor_name": m.competitor_name,
            "competitor_id": m.competitor_id,
            "similarity_score": m.similarity_score,
            "status": m.status,
            "category": m.category,
        }
        for m in all_matches
    ])

    # Guardar en PostgreSQL (silver layer)
    results_df.to_sql(
        "product_matches",
        engine,
        schema="silver",
        if_exists="replace",
        index=False,
    )

    logger.success(
        f"  ✅ Matching completado: {accepted_count} aceptados, "
        f"{review_count} en revisión"
    )
    return results_df
