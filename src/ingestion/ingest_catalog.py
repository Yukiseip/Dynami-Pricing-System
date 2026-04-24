"""
ingest_catalog.py
=================
Ingesta el catálogo de productos propios desde CSV a PostgreSQL (capa Bronze).
"""
from pathlib import Path

import pandas as pd
from loguru import logger

from sqlalchemy.types import Numeric
from .db_utils import get_engine, create_schema_if_not_exists, clear_table_if_exists


def ingest_catalog(csv_path: str = "data/raw/catalog.csv") -> int:
    """
    Carga el catálogo completo en la tabla bronze.raw_products.

    Args:
        csv_path: Ruta al archivo CSV del catálogo.

    Returns:
        Número de filas insertadas.

    Raises:
        FileNotFoundError: Si el archivo CSV no existe.
    """
    logger.info(f"Iniciando ingesta de catálogo desde: {csv_path}")

    # Validar que el archivo existe
    if not Path(csv_path).exists():
        raise FileNotFoundError(f"Archivo no encontrado: {csv_path}")

    # Cargar datos
    df = pd.read_csv(csv_path)
    logger.info(f"  Filas leídas: {len(df)}")

    # Agregar metadata de ingesta
    df["ingested_at"] = pd.Timestamp.now()
    df["source_file"] = csv_path

    # Guardar en PostgreSQL
    engine = get_engine()
    create_schema_if_not_exists(engine, "bronze")

    # Evitar conflictos de dependencia con vistas dbt
    clear_table_if_exists(engine, "bronze", "raw_products")

    rows = df.to_sql(
        name="raw_products",
        con=engine,
        schema="bronze",
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
        dtype={
            "base_price": Numeric(10, 2),
            "cost_price": Numeric(10, 2),
            "current_price": Numeric(10, 2),
        }
    )
    logger.success(f"  ✅ Insertadas {rows} filas en bronze.raw_products")
    return rows or 0


if __name__ == "__main__":
    ingest_catalog()
