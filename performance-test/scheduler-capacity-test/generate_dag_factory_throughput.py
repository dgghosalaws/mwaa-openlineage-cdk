"""
Generate DAG Factory YAML Configuration for DAG Throughput Testing

Creates N DAGs with 2 dummy tasks each to test MWAA scheduler parsing
and scheduling throughput at scale.

Usage:
    # Generate 4000 DAGs (default)
    python generate_dag_factory_throughput.py

    # Custom count
    python generate_dag_factory_throughput.py --dags 2000

    # Custom task duration
    python generate_dag_factory_throughput.py --dags 4000 --task-duration 30
"""

import yaml
import argparse
import os
import math


DAGS_PER_LOADER = 400  # Max DAGs per loader file to stay under parse timeout


def generate_dag_config(dag_num: int, task_duration_secs: int = 30) -> dict:
    """Generate config for a single DAG with 2 dummy tasks."""
    dag_id = f"throughput_dag_{dag_num:04d}"
    return {
        dag_id: {
            'default_args': {
                'owner': 'airflow',
                'depends_on_past': False,
                'email_on_failure': False,
                'email_on_retry': False,
                'retries': 0,
            },
            'description': f'Throughput test DAG {dag_num:04d}',
            'schedule': None,
            'catchup': False,
            'max_active_runs': 1,
            'is_paused_upon_creation': False,
            'tags': ['throughput-test', 'dag-factory-test', 'performance'],
            'tasks': [
                {
                    'task_id': 'task_a',
                    'operator': 'airflow.operators.python.PythonOperator',
                    'python_callable_name': 'dummy_task',
                    'python_callable_file': '/usr/local/airflow/dags/throughput_tasks.py',
                    'op_kwargs': {
                        'dag_num': dag_num,
                        'task_name': 'task_a',
                        'duration': task_duration_secs,
                    },
                },
                {
                    'task_id': 'task_b',
                    'operator': 'airflow.operators.python.PythonOperator',
                    'python_callable_name': 'dummy_task',
                    'python_callable_file': '/usr/local/airflow/dags/throughput_tasks.py',
                    'op_kwargs': {
                        'dag_num': dag_num,
                        'task_name': 'task_b',
                        'duration': task_duration_secs,
                    },
                    'dependencies': ['task_a'],
                },
            ],
        }
    }


def generate_loader(loader_num: int, dag_start: int, dag_end: int) -> str:
    """Generate a per-loader Python file."""
    return f'''"""
DAG Factory loader for throughput test - loader {loader_num:02d} (DAGs {dag_start}-{dag_end - 1})
"""

from airflow import DAG  # noqa: F401
from dagfactory import load_yaml_dags
import os

config_dir = os.path.join(os.path.dirname(__file__), "throughput_configs", "loader_{loader_num:02d}")
load_yaml_dags(dags_folder=config_dir, globals_dict=globals())
'''


def generate_trigger_dag(total_dags: int) -> str:
    """Generate master trigger DAG."""
    return f'''"""
Master Trigger DAG for Throughput Test - {total_dags} DAGs
"""

from airflow import DAG
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.operators.python import PythonOperator
from datetime import datetime
import logging

default_args = {{
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}}

num_dags = {total_dags}

dag = DAG(
    'trigger_throughput_test',
    default_args=default_args,
    description=f'Master trigger for {{num_dags}} throughput test DAGs',
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=['throughput-test', 'master-trigger', 'performance'],
)


def log_start(**context):
    logger = logging.getLogger(__name__)
    logger.info(f"Triggering {{num_dags}} throughput test DAGs")
    return {{'start_time': datetime.now().isoformat()}}


def log_complete(**context):
    logger = logging.getLogger(__name__)
    logger.info(f"All {{num_dags}} DAGs triggered")
    return {{'complete_time': datetime.now().isoformat()}}


start = PythonOperator(task_id='log_start', python_callable=log_start, dag=dag)
end = PythonOperator(task_id='log_complete', python_callable=log_complete, dag=dag)

for i in range(num_dags):
    dag_id = f"throughput_dag_{{i:04d}}"
    t = TriggerDagRunOperator(
        task_id=f'trigger_{{dag_id}}',
        trigger_dag_id=dag_id,
        wait_for_completion=False,
        dag=dag,
    )
    start >> t >> end
'''


def main():
    parser = argparse.ArgumentParser(
        description='Generate DAG Factory throughput test configuration',
    )
    parser.add_argument('--dags', type=int, default=4000, help='Total number of DAGs (default: 4000)')
    parser.add_argument('--task-duration', type=int, default=30, help='Duration of each dummy task in seconds (default: 30)')
    args = parser.parse_args()

    total_dags = args.dags
    task_duration = args.task_duration
    num_loaders = math.ceil(total_dags / DAGS_PER_LOADER)

    configs_dir = 'throughput_configs'

    print(f"Generating throughput test configuration...")
    print(f"  Total DAGs: {total_dags}")
    print(f"  Tasks per DAG: 2")
    print(f"  Task duration: {task_duration}s")
    print(f"  Loaders: {num_loaders} ({DAGS_PER_LOADER} DAGs each)")

    dag_num = 0
    for loader_num in range(num_loaders):
        loader_dir = os.path.join(configs_dir, f'loader_{loader_num:02d}')
        os.makedirs(loader_dir, exist_ok=True)

        dag_start = dag_num
        dags_this_loader = min(DAGS_PER_LOADER, total_dags - dag_num)

        for i in range(dags_this_loader):
            config = generate_dag_config(dag_num, task_duration)
            dag_file = os.path.join(loader_dir, f'throughput_dag_{dag_num:04d}.yaml')
            with open(dag_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            dag_num += 1

        dag_end = dag_num

        # Generate loader file
        loader_file = f'throughput_loader_{loader_num:02d}.py'
        with open(loader_file, 'w') as f:
            f.write(generate_loader(loader_num, dag_start, dag_end))

        print(f"  Loader {loader_num:02d}: {dags_this_loader} DAGs ({dag_start}-{dag_end - 1})")

    # Generate trigger DAG
    trigger_file = 'trigger_throughput_test.py'
    with open(trigger_file, 'w') as f:
        f.write(generate_trigger_dag(total_dags))

    # Generate task functions
    tasks_file = 'throughput_tasks.py'
    with open(tasks_file, 'w') as f:
        f.write('''"""Dummy task functions for throughput test."""

import time
import logging


def dummy_task(dag_num: int, task_name: str, duration: int = 30, **context):
    """Simple task that sleeps for the given duration."""
    logger = logging.getLogger(__name__)
    if dag_num % 100 == 0:
        logger.info(f"DAG {dag_num} - {task_name} started (duration: {duration}s)")
    time.sleep(duration)
    if dag_num % 100 == 0:
        logger.info(f"DAG {dag_num} - {task_name} completed")
    return {'dag_num': dag_num, 'task_name': task_name, 'duration': duration}
''')

    print(f"\n✅ Generated:")
    print(f"   - {total_dags} per-DAG YAML configs in {configs_dir}/")
    print(f"   - {num_loaders} loader files (throughput_loader_*.py)")
    print(f"   - 1 trigger DAG (trigger_throughput_test.py)")
    print(f"   - 1 task functions file (throughput_tasks.py)")


if __name__ == '__main__':
    main()
