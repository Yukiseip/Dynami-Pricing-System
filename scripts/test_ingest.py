"""test_ingest.py — Test de ingesta con verificación inmediata."""
import sys
sys.path.insert(0, '/opt/airflow/src')

from ingestion.ingest_catalog import ingest_catalog
from ingestion.db_utils import get_engine
from sqlalchemy import text

print("Running ingest_catalog...")
rows = ingest_catalog('/opt/airflow/data/raw/catalog.csv')
print(f"Inserted: {rows}")

# Verify immediately
eng = get_engine()
with eng.connect() as conn:
    tables = list(conn.execute(text(
        "SELECT schemaname, tablename FROM pg_tables "
        "WHERE schemaname = 'bronze'"
    )))
    print("Tables in bronze:", tables)
    if tables:
        cnt = conn.execute(text("SELECT COUNT(*) FROM bronze.raw_products")).scalar()
        print(f"Count in bronze.raw_products: {cnt}")
