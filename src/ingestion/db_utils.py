"""db_utils.py — Utilidades de conexión a base de datos."""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

load_dotenv()


def get_engine() -> Engine:
    """
    Crea y retorna engine de SQLAlchemy para PostgreSQL.

    Returns:
        Engine de SQLAlchemy listo para usar.
    """
    url = (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:"
        f"{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB')}"
    )
    return create_engine(url, pool_pre_ping=True)


def create_schema_if_not_exists(engine: Engine, schema: str) -> None:
    """
    Crea el schema si no existe.

    Args:
        engine: Engine de SQLAlchemy.
        schema: Nombre del schema (bronze, silver, gold).
    """
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

def drop_table_cascade_if_exists(engine: Engine, schema: str, table: str) -> None:
    """
    Drop table with CASCADE to avoid dependency issues with dbt views.
    """
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {schema}.{table} CASCADE"))

def clear_table_if_exists(engine: Engine, schema: str, table: str) -> None:
    """
    Clears the table without dropping it to avoid dependency issues with dbt views.
    """
    with engine.begin() as conn:
        result = conn.execute(text(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = '{schema}' AND table_name = '{table}')")).scalar()
        if result:
            conn.execute(text(f"TRUNCATE TABLE {schema}.{table}"))
