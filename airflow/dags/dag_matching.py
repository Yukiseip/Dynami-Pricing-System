"""
dag_matching.py
===============
DAG para generar embeddings e indexar en Qdrant, luego ejecutar matching.
"""
from datetime import timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

import sys
sys.path.insert(0, '/opt/airflow/src')


def task_generate_own_embeddings():
    """Genera e indexa embeddings de productos propios."""
    import pandas as pd
    from ingestion.db_utils import get_engine
    from matching.embeddings import generate_and_index_embeddings

    engine = get_engine()
    df = pd.read_sql(
        "SELECT product_id, name_original AS name, category FROM silver.stg_products",
        engine
    )
    return generate_and_index_embeddings(
        df, source="own", name_col="name",
        product_id_col="product_id", category_col="category"
    )


def task_generate_competitor_embeddings():
    """Genera e indexa embeddings de productos de competencia."""
    import pandas as pd
    from ingestion.db_utils import get_engine
    from matching.embeddings import generate_and_index_embeddings

    engine = get_engine()
    df = pd.read_sql(
        """SELECT CONCAT(competitor_id, '_', ROW_NUMBER() OVER()) AS id,
                  product_name_competitor AS name, category,
                  competitor_price, competitor_id
           FROM silver.stg_competitor_prices""",
        engine
    )
    return generate_and_index_embeddings(
        df, source="competitor", name_col="name",
        product_id_col="id", price_col="competitor_price",
        category_col="category"
    )


def task_run_matching():
    """Ejecuta el algoritmo de matching."""
    from matching.matcher import run_matching_pipeline
    results = run_matching_pipeline()
    print(f"Matches encontrados: {len(results)}")


DEFAULT_ARGS = {
    "owner": "ml-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "start_date": days_ago(1),
}

with DAG(
    dag_id="product_matching",
    default_args=DEFAULT_ARGS,
    description="Embeddings + Matching de productos propios vs competencia",
    schedule_interval=None,  # Triggered por pipeline maestro
    catchup=False,
    tags=["matching", "nlp", "qdrant"],
) as dag:

    t_own_emb = PythonOperator(
        task_id="generate_own_embeddings",
        python_callable=task_generate_own_embeddings,
    )

    t_comp_emb = PythonOperator(
        task_id="generate_competitor_embeddings",
        python_callable=task_generate_competitor_embeddings,
    )

    t_match = PythonOperator(
        task_id="run_matching",
        python_callable=task_run_matching,
    )

    [t_own_emb, t_comp_emb] >> t_match
