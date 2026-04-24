"""
embeddings.py
=============
Genera y gestiona embeddings semánticos de productos usando sentence-transformers.
Modelo: all-MiniLM-L6-v2 (384 dimensiones, ~22MB, no requiere GPU)
"""
import os
from typing import Optional

import pandas as pd
from loguru import logger
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue
)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "product_embeddings")
VECTOR_SIZE = 384  # Dimensión fija de all-MiniLM-L6-v2


def get_qdrant_client() -> QdrantClient:
    """Retorna cliente de Qdrant."""
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def get_embedding_model() -> SentenceTransformer:
    """Carga el modelo de embeddings (se cachea en memoria)."""
    logger.info(f"Cargando modelo: {EMBEDDING_MODEL}")
    return SentenceTransformer(EMBEDDING_MODEL)


def create_collection_if_not_exists(client: QdrantClient) -> None:
    """Crea la colección en Qdrant si no existe."""
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        logger.info(f"Colección creada: {COLLECTION_NAME}")
    else:
        logger.info(f"Colección existente: {COLLECTION_NAME}")


def build_product_text(name: str, category: str) -> str:
    """
    Construye el texto de entrada para el modelo.
    Combina nombre y categoría para mejorar la precisión del embedding.
    """
    return f"{category}: {name}".lower().strip()


def generate_and_index_embeddings(
    df: pd.DataFrame,
    source: str,  # 'own' o 'competitor'
    name_col: str,
    product_id_col: str,
    price_col: Optional[str] = None,
    category_col: str = "category",
    batch_size: int = 64,
) -> int:
    """
    Genera embeddings para un DataFrame de productos y los indexa en Qdrant.

    Args:
        df: DataFrame con productos
        source: 'own' o 'competitor'
        name_col: columna con el nombre del producto
        product_id_col: columna con el ID del producto
        price_col: columna con el precio (opcional)
        category_col: columna con la categoría
        batch_size: tamaño de batch para inferencia

    Returns:
        Número de vectores indexados
    """
    logger.info(f"Generando embeddings para {len(df)} productos (source={source})")

    model = get_embedding_model()
    client = get_qdrant_client()
    create_collection_if_not_exists(client)

    texts = [
        build_product_text(row[name_col], row[category_col])
        for _, row in df.iterrows()
    ]

    # Generar embeddings en batches
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = model.encode(batch, show_progress_bar=False)
        all_embeddings.extend(embeddings.tolist())
        logger.debug(f"  Batch {i//batch_size + 1}: {len(batch)} embeddings generados")

    # Preparar puntos para Qdrant
    points = []
    for idx, (_, row) in enumerate(df.iterrows()):
        payload = {
            "product_id": str(row[product_id_col]),
            "source": source,
            "category": str(row.get(category_col, "")),
            "name": str(row[name_col]),
        }
        if price_col and price_col in row:
            payload["price"] = float(row[price_col]) if pd.notna(row[price_col]) else None

        points.append(PointStruct(
            id=abs(hash(f"{source}_{row[product_id_col]}_{idx}")) % (2**63),
            vector=all_embeddings[idx],
            payload=payload,
        ))

    # Indexar en Qdrant en batches
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)

    logger.success(f"  ✅ {len(points)} vectores indexados en Qdrant ({source})")
    return len(points)
