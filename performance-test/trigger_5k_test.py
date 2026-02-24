"""
Master DAG to trigger all 200 DAGs for 5K load test

Triggers 200 DAGs at once for 5000 task peak load test.
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
    if dag_num < 50:
        return 1
    elif dag_num < 75:
        return 2
    elif dag_num < 100:
        return 3
    elif dag_num < 150:
        return 4
    else:
        return 5

with DAG(
    dag_id='trigger_5k_performance_test',
    default_args=default_args,
    description='Master DAG to trigger all 200 DAGs for 5K load test',
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=['capacity-test-5k', 'master-trigger-5k'],
) as dag:
    
    # Create trigger tasks for all 200 DAGs
    for i in range(200):
        wave = get_wave_for_dag(i)
        dag_id = f"perf_5k_wave{wave}_{i:03d}"
        
        trigger_task = TriggerDagRunOperator(
            task_id=f'trigger_{dag_id}',
            trigger_dag_id=dag_id,
            wait_for_completion=False,
            reset_dag_run=True,
        )
