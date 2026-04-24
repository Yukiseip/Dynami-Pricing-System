"""
dag_dynamic_pricing_pipeline.py
================================
DAG MAESTRO: Orquesta el pipeline completo de dynamic pricing cada hora.

Flujo:
    ingest_data → validate_data_quality → run_dbt_transformations
    → generate_embeddings → run_product_matching → run_pricing_engine

SLA: 10 minutos por ejecución.
"""
import subprocess
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

import sys
sys.path.insert(0, '/opt/airflow/src')


# ============================================================
# TASK FUNCTIONS
# ============================================================

def task_ingest_data():
    """Paso 1: Regenerar datos e ingestar a Bronze."""
    import subprocess
    import sys
    subprocess.run(
        [sys.executable, "/opt/airflow/scripts/generate_datasets.py",
         "--output-dir", "/opt/airflow/data/raw", "--seed", "42"],
        check=True, capture_output=True, text=True
    )
    from ingestion.ingest_catalog import ingest_catalog
    from ingestion.ingest_competitors import ingest_competitors
    from ingestion.ingest_inventory import ingest_inventory

    ingest_catalog("/opt/airflow/data/raw/catalog.csv")
    ingest_competitors("/opt/airflow/data/raw/competitors.csv")
    ingest_inventory("/opt/airflow/data/raw/inventory_demand.csv")
    print("✅ Ingesta completada")


def task_validate_data_quality():
    """Paso 2: Validar calidad de datos en Bronze."""
    import pandas as pd
    from ingestion.db_utils import get_engine

    engine = get_engine()
    validations = []

    # Verificar que las tablas Bronze tienen datos
    for table in ["bronze.raw_products", "bronze.raw_competitors", "bronze.raw_inventory"]:
        count = pd.read_sql(f"SELECT COUNT(*) as n FROM {table}", engine).iloc[0]["n"]
        if count == 0:
            raise ValueError(f"❌ Tabla {table} está vacía!")
        validations.append(f"  ✅ {table}: {count} filas")
        print(f"  ✅ {table}: {count} filas")

    # Verificar que no hay precios negativos en raw_products
    neg = pd.read_sql(
        "SELECT COUNT(*) as n FROM bronze.raw_products WHERE current_price <= 0 OR cost_price <= 0",
        engine
    ).iloc[0]["n"]
    if neg > 0:
        raise ValueError(f"❌ {neg} productos con precio inválido en Bronze")

    print(f"✅ Validación de calidad completada: {len(validations)} checks OK")


def task_run_dbt():
    """Paso 3: Ejecutar transformaciones dbt Bronze → Silver → Gold."""
    for select in ["bronze", "silver", "gold"]:
        result = subprocess.run(
            ["dbt", "run", "--select", select,
             "--project-dir", "/opt/airflow/dbt",
             "--profiles-dir", "/opt/airflow/dbt"],
            capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            raise RuntimeError(f"dbt run {select} falló:\n{result.stderr}")

    # Ejecutar tests de Silver
    test_result = subprocess.run(
        ["dbt", "test", "--select", "silver",
         "--project-dir", "/opt/airflow/dbt",
         "--profiles-dir", "/opt/airflow/dbt"],
        capture_output=True, text=True
    )
    print(test_result.stdout)
    print("✅ dbt transformaciones completadas")


def task_generate_embeddings():
    """Paso 4: Generar e indexar embeddings en Qdrant."""
    import pandas as pd
    from ingestion.db_utils import get_engine
    from matching.embeddings import generate_and_index_embeddings

    engine = get_engine()

    # Embeddings de productos propios
    df_own = pd.read_sql(
        "SELECT product_id, name_original AS name, category FROM silver.stg_products",
        engine
    )
    n_own = generate_and_index_embeddings(
        df_own, source="own", name_col="name",
        product_id_col="product_id", category_col="category"
    )

    # Embeddings de competencia
    df_comp = pd.read_sql(
        """SELECT CONCAT(competitor_id, '_', ROW_NUMBER() OVER()) AS id,
                  product_name_competitor AS name, category,
                  competitor_price, competitor_id
           FROM silver.stg_competitor_prices""",
        engine
    )
    n_comp = generate_and_index_embeddings(
        df_comp, source="competitor", name_col="name",
        product_id_col="id", price_col="competitor_price",
        category_col="category"
    )
    print(f"✅ Embeddings generados: {n_own} propios + {n_comp} competencia")


def task_run_matching():
    """Paso 5: Ejecutar matching de productos."""
    from matching.matcher import run_matching_pipeline
    results = run_matching_pipeline()
    print(f"✅ Matching completado: {len(results)} matches")


def task_run_pricing():
    """Paso 6: Calcular precios sugeridos."""
    from pricing.engine import run_pricing_pipeline
    results = run_pricing_pipeline()
    print(f"✅ Pricing completado: {len(results)} recomendaciones")
    if not results.empty:
        print(f"  Distribución: {results['action'].value_counts().to_dict()}")


# ============================================================
# DAG DEFINITION
# ============================================================

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": days_ago(1),
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
    "email_on_failure": False,
    "sla": timedelta(minutes=10),
}

with DAG(
    dag_id="dynamic_pricing_pipeline",
    default_args=DEFAULT_ARGS,
    description="Pipeline maestro de dynamic pricing (end-to-end)",
    schedule_interval="@hourly",
    catchup=False,
    max_active_runs=1,
    tags=["master", "pricing", "e2e"],
) as dag:

    t1_ingest = PythonOperator(
        task_id="ingest_data",
        python_callable=task_ingest_data,
    )

    t2_validate = PythonOperator(
        task_id="validate_data_quality",
        python_callable=task_validate_data_quality,
    )

    t3_dbt = PythonOperator(
        task_id="run_dbt_transformations",
        python_callable=task_run_dbt,
    )

    t4_embeddings = PythonOperator(
        task_id="generate_embeddings",
        python_callable=task_generate_embeddings,
    )

    t5_matching = PythonOperator(
        task_id="run_product_matching",
        python_callable=task_run_matching,
    )

    t6_pricing = PythonOperator(
        task_id="run_pricing_engine",
        python_callable=task_run_pricing,
    )

    # Flujo secuencial con dependencias
    t1_ingest >> t2_validate >> t3_dbt >> t4_embeddings >> t5_matching >> t6_pricing
