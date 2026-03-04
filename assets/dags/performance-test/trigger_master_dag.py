"""
Master DAG to trigger all 100 distributed gradual load test DAGs

This DAG triggers all 100 performance test DAGs at once.
Simply trigger this single DAG from the UI, and it will trigger all others.
"""

from airflow import DAG
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from datetime import datetime

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}

def get_wave_for_dag(dag_num):
    """Determine which wave a DAG belongs to"""
    if dag_num < 25:
        return 1
    elif dag_num < 38:
        return 2
    elif dag_num < 50:
        return 3
    elif dag_num < 75:
        return 4
    else:
        return 5

with DAG(
    dag_id='trigger_performance_test',
    default_args=default_args,
    description='Master DAG to trigger all 100 distributed performance test DAGs',
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=['capacity-test', 'master-trigger'],
) as dag:
    
    # Create trigger tasks for all 100 DAGs
    for i in range(100):
        wave = get_wave_for_dag(i)
        dag_id = f"perf_test_wave{wave}_{i:03d}"
        
        trigger_task = TriggerDagRunOperator(
            task_id=f'trigger_{dag_id}',
            trigger_dag_id=dag_id,
            wait_for_completion=False,  # Don't wait - trigger and move on
            reset_dag_run=True,  # Allow re-triggering
        )
