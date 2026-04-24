"""check_db.py — Diagnóstico de conexión y schemas en PostgreSQL."""
import sys
sys.path.insert(0, '/opt/airflow/src')

from ingestion.db_utils import get_engine
from sqlalchemy import text

eng = get_engine()
with eng.connect() as conn:
    # Check all tables
    rows = conn.execute(text(
        "SELECT schemaname, tablename FROM pg_tables "
        "WHERE schemaname NOT IN ('pg_catalog','information_schema') "
        "ORDER BY schemaname, tablename"
    ))
    print("=== ALL TABLES ===")
    for r in rows:
        print(f"  {r[0]}.{r[1]}")

    # Count rows in raw tables
    for schema_table in [('bronze', 'raw_products'), ('bronze', 'raw_competitors'), ('bronze', 'raw_inventory')]:
        schema, table = schema_table
        try:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {schema}.{table}")).scalar()
            print(f"  {schema}.{table}: {cnt} rows")
        except Exception as e:
            print(f"  {schema}.{table}: ERROR - {e}")
