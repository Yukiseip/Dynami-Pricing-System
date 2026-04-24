"""
ingest_competitors.py
=====================
Ingesta datos de competencia desde CSV a PostgreSQL (capa Bronze).
"""
from pathlib import Path

import pandas as pd
from loguru import logger

from sqlalchemy.types import Numeric
from .db_utils import get_engine, create_schema_if_not_exists, clear_table_if_exists


def ingest_competitors(csv_path: str = "data/raw/competitors.csv") -> int:
    """
    Carga datos de competencia en bronze.raw_competitors.

    Args:
        csv_path: Ruta al archivo CSV de competidores.

    Returns:
        Número de filas insertadas.

    Raises:
        FileNotFoundError: Si el archivo CSV no existe.
    """
    logger.info(f"Iniciando ingesta de competencia desde: {csv_path}")

    if not Path(csv_path).exists():
        raise FileNotFoundError(f"Archivo no encontrado: {csv_path}")

    df = pd.read_csv(csv_path)
    logger.info(f"  Filas leídas: {len(df)}")

    df["ingested_at"] = pd.Timestamp.now()
    df["source_file"] = csv_path

    engine = get_engine()
    create_schema_if_not_exists(engine, "bronze")

    # Evitar conflictos de dependencia con vistas dbt
    clear_table_if_exists(engine, "bronze", "raw_competitors")

    rows = df.to_sql(
        name="raw_competitors",
        con=engine,
        schema="bronze",
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
        dtype={
            "competitor_price": Numeric(10, 2),
        }
    )
    logger.success(f"  ✅ Insertadas {rows} filas en bronze.raw_competitors")
    return rows or 0


if __name__ == "__main__":
    ingest_competitors()
