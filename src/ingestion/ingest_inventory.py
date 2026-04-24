"""
ingest_inventory.py
===================
Ingesta datos de inventario y demanda a PostgreSQL (capa Bronze).
"""
from pathlib import Path

import pandas as pd
from loguru import logger

from .db_utils import get_engine, create_schema_if_not_exists, clear_table_if_exists


def ingest_inventory(csv_path: str = "data/raw/inventory_demand.csv") -> int:
    """
    Carga datos de inventario/demanda en bronze.raw_inventory.

    Args:
        csv_path: Ruta al archivo CSV de inventario/demanda.

    Returns:
        Número de filas insertadas.

    Raises:
        FileNotFoundError: Si el archivo CSV no existe.
    """
    logger.info(f"Iniciando ingesta de inventario desde: {csv_path}")

    if not Path(csv_path).exists():
        raise FileNotFoundError(f"Archivo no encontrado: {csv_path}")

    df = pd.read_csv(csv_path)
    logger.info(f"  Filas leídas: {len(df)}")

    df["ingested_at"] = pd.Timestamp.now()
    df["source_file"] = csv_path

    engine = get_engine()
    create_schema_if_not_exists(engine, "bronze")

    # Evitar conflictos de dependencia con vistas dbt
    clear_table_if_exists(engine, "bronze", "raw_inventory")

    rows = df.to_sql(
        name="raw_inventory",
        con=engine,
        schema="bronze",
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )
    logger.success(f"  ✅ Insertadas {rows} filas en bronze.raw_inventory")
    return rows or 0


if __name__ == "__main__":
    ingest_inventory()
