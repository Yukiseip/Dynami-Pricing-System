"""
dag_run_dbt.py
==============
DAG de Airflow para ejecutar modelos dbt en secuencia Bronze → Silver → Gold.
"""
import subprocess
from datetime import timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago


def run_dbt_command(command: list) -> None:
    """Ejecuta un comando dbt y captura la salida."""
    full_command = ["dbt"] + command + [
        "--project-dir", "/opt/airflow/dbt",
        "--profiles-dir", "/opt/airflow/dbt"
    ]
    result = subprocess.run(
        full_command, capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(f"dbt falló:\n{result.stderr}")


def run_dbt_bronze():
    run_dbt_command(["run", "--select", "bronze"])


def run_dbt_silver():
    run_dbt_command(["run", "--select", "silver"])


def run_dbt_gold():
    run_dbt_command(["run", "--select", "gold"])


def run_dbt_tests():
    run_dbt_command(["test", "--select", "silver"])


DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
    "start_date": days_ago(1),
}

with DAG(
    dag_id="run_dbt_models",
    default_args=DEFAULT_ARGS,
    description="Ejecutar modelos dbt: Bronze → Silver → Gold",
    schedule_interval=None,  # Triggered por pipeline maestro
    catchup=False,
    tags=["dbt", "transformation"],
) as dag:

    t_bronze = PythonOperator(task_id="dbt_bronze", python_callable=run_dbt_bronze)
    t_silver = PythonOperator(task_id="dbt_silver", python_callable=run_dbt_silver)
    t_test = PythonOperator(task_id="dbt_tests", python_callable=run_dbt_tests)
    t_gold = PythonOperator(task_id="dbt_gold", python_callable=run_dbt_gold)

    t_bronze >> t_silver >> t_test >> t_gold
