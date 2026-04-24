"""check_db2.py — Diagnóstico detallado."""
import sys
sys.path.insert(0, '/opt/airflow/src')

from ingestion.db_utils import get_engine
from sqlalchemy import text
import pandas as pd

eng = get_engine()

# Check search_path and schemas
with eng.connect() as conn:
    sp = conn.execute(text("SHOW search_path")).scalar()
    print("search_path:", sp)
    
    rows = list(conn.execute(text(
        "SELECT schemaname, tablename FROM pg_tables "
        "WHERE schemaname NOT IN ('pg_catalog','information_schema') "
        "ORDER BY schemaname, tablename"
    )))
    print("ALL TABLES:", rows if rows else "NONE")

# Try to write a test record
print("\n--- Test write ---")
try:
    df = pd.DataFrame([{"id": 1, "val": "test"}])
    with eng.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS bronze"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS bronze.test_write (id int, val text)"))
        conn.execute(text("INSERT INTO bronze.test_write VALUES (1, 'hello')"))
    print("Write succeeded - checking...")
    with eng.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM bronze.test_write")).scalar()
        print(f"Rows in bronze.test_write: {cnt}")
        conn.execute(text("DROP TABLE bronze.test_write"))
except Exception as e:
    print(f"Write error: {e}")
