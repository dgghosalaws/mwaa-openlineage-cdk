"""
Master DAG to trigger sustained load test

Triggers all DAGs for 40-minute sustained load test with 20-minute peak.
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
    """Determine which waves a DAG belongs to"""
    waves = []
    if dag_num < 20:
        waves.append(1)
    if 20 <= dag_num < 40:
        waves.append(2)
    if 40 <= dag_num < 60:
        waves.append(3)
    if 60 <= dag_num < 80:
        waves.append(4)
    if 80 <= dag_num < 100:
        waves.extend([5, 6])  # These DAGs run in both wave 5 and 6
    return waves

with DAG(
    dag_id='trigger_sustained_load_test',
    default_args=default_args,
    description='Master DAG to trigger 40-minute sustained load test with 20-minute peak',
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=['sustained-load', 'master-trigger'],
) as dag:
    
    # Create trigger tasks for all wave/DAG combinations
    for wave_num in range(1, 7):
        if wave_num <= 4:
            # Waves 1-4: Each has unique DAG ranges
            start = (wave_num - 1) * 20
            end = wave_num * 20
        else:
            # Waves 5-6: Both use DAGs 80-99
            start = 80
            end = 100
        
        for dag_num in range(start, end):
            dag_id = f"sustained_load_wave{wave_num}_{dag_num:03d}"
            
            trigger_task = TriggerDagRunOperator(
                task_id=f'trigger_{dag_id}',
                trigger_dag_id=dag_id,
                wait_for_completion=False,
                reset_dag_run=True,
            )
