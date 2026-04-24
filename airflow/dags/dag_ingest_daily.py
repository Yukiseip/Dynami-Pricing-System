"""
dag_ingest_daily.py
===================
DAG de Airflow para ingesta diaria de datos crudos a la capa Bronze.
Tareas:
    1. generate_data      → Ejecuta generate_datasets.py
    2. ingest_catalog     → Carga catalog.csv → bronze.raw_products
    3. ingest_competitors → Carga competitors.csv → bronze.raw_competitors
    4. ingest_inventory   → Carga inventory_demand.csv → bronze.raw_inventory
"""
import subprocess
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

import sys
sys.path.insert(0, '/opt/airflow/src')

from ingestion.ingest_catalog import ingest_catalog
from ingestion.ingest_competitors import ingest_competitors
from ingestion.ingest_inventory import ingest_inventory


def run_generate_datasets():
    """Regenera los datasets sintéticos (simula extracción de sistemas fuente)."""
    import sys
    result = subprocess.run(
        [sys.executable, "/opt/airflow/scripts/generate_datasets.py",
         "--output-dir", "/opt/airflow/data/raw", "--seed", "42"],
        capture_output=True, text=True, check=True
    )
    print(result.stdout)


DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": days_ago(1),
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="ingest_daily",
    default_args=DEFAULT_ARGS,
    description="Ingesta diaria de datos crudos a capa Bronze",
    schedule_interval="@daily",
    catchup=False,
    tags=["ingestion", "bronze", "etl"],
) as dag:

    t_generate = PythonOperator(
        task_id="generate_datasets",
        python_callable=run_generate_datasets,
    )

    t_catalog = PythonOperator(
        task_id="ingest_catalog",
        python_callable=ingest_catalog,
        op_kwargs={"csv_path": "/opt/airflow/data/raw/catalog.csv"},
    )

    t_competitors = PythonOperator(
        task_id="ingest_competitors",
        python_callable=ingest_competitors,
        op_kwargs={"csv_path": "/opt/airflow/data/raw/competitors.csv"},
    )

    t_inventory = PythonOperator(
        task_id="ingest_inventory",
        python_callable=ingest_inventory,
        op_kwargs={"csv_path": "/opt/airflow/data/raw/inventory_demand.csv"},
    )

    # Dependencias: generar datos primero, luego ingestar en paralelo
    t_generate >> [t_catalog, t_competitors, t_inventory]
