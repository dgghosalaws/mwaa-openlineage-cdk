"""
Generate DAG Factory YAML Configuration for Sustained Load Testing

This generates a sustained load test with gradual ramp-up, sustained peak, and ramp-down.
Supports multiple sets of 65 DAGs each, with a master trigger DAG per set.

Test Pattern (40 minutes total):
- 0-5 min: Ramp up from 500 → peak tasks
- 5-25 min: Sustain peak load (20 minutes)
- 25-40 min: Ramp down peak → 0 tasks

Usage:
    # Generate 2000 peak tasks (default, 1 set of 65 DAGs)
    python generate_dag_factory_sustained.py
    
    # Generate 2 sets of 65 DAGs (130 DAGs total, 2 master triggers)
    python generate_dag_factory_sustained.py --sets 2
    
    # Generate 4000 peak tasks with 3 sets
    python generate_dag_factory_sustained.py --peak-tasks 4000 --sets 3
    
    # Custom peak and duration
    python generate_dag_factory_sustained.py --peak-tasks 3000 --peak-duration 30 --sets 2
"""

import yaml
import argparse
import os
from typing import Dict, List


def calculate_wave_config(peak_tasks: int, peak_duration: int = 20) -> Dict:
    """
    Calculate wave configuration for sustained load test.
    
    Args:
        peak_tasks: Target peak concurrent tasks
        peak_duration: How long to sustain peak (minutes)
    
    Returns:
        Configuration with wave timings and task counts
    """
    # Use 65 DAGs (scheduler throughput limit)
    num_dags = 65
    
    # Calculate tasks per DAG at peak
    tasks_per_dag_peak = peak_tasks // num_dags
    
    # Wave configuration
    # Wave 1: 500 tasks (baseline)
    # Wave 2: 1000 tasks (50% to peak)
    # Wave 3: 1500 tasks (75% to peak)
    # Wave 4-N: Peak tasks (sustained)
    # Wave N+1: Ramp down
    
    tasks_wave1 = 500
    tasks_wave2 = peak_tasks // 2
    tasks_wave3 = int(peak_tasks * 0.75)
    
    # Calculate how many DAGs needed for each wave
    dags_wave1 = tasks_wave1 // tasks_per_dag_peak or 1
    dags_wave2 = tasks_wave2 // tasks_per_dag_peak or 1
    dags_wave3 = tasks_wave3 // tasks_per_dag_peak or 1
    
    # Remaining DAGs for peak
    dags_peak = num_dags - dags_wave3
    
    # Calculate number of peak waves (one every 5 minutes)
    num_peak_waves = peak_duration // 5
    
    waves = []
    
    # Calculate task durations to achieve proper ramp-down
    # Goal: All tasks overlap during peak (T+5 to T+25), then finish gradually (T+25 to T+40)
    # 
    # Wave 1: starts T+0, finishes T+25 (25 min) - first to finish
    # Wave 2: starts T+2, finishes T+30 (28 min) - ramp-down continues
    # Wave 3: starts T+4, finishes T+35 (31 min) - ramp-down continues
    # Wave 4+: start T+5-20, finish T+40 (35 min) - last to finish
    
    # Ramp up waves with staggered finish times for ramp-down
    waves.append({
        'wave': 1,
        'dag_start': 0,
        'dag_count': dags_wave1,
        'delay_minutes': 0,
        'task_duration': 25,  # Finish at T+25 (start of ramp-down)
        'description': f'Baseline - {tasks_wave1} tasks'
    })
    
    waves.append({
        'wave': 2,
        'dag_start': dags_wave1,
        'dag_count': dags_wave2 - dags_wave1,
        'delay_minutes': 2,
        'task_duration': 28,  # Finish at T+30 (mid ramp-down)
        'description': f'Ramp to 50% - {tasks_wave2} tasks'
    })
    
    waves.append({
        'wave': 3,
        'dag_start': dags_wave2,
        'dag_count': dags_wave3 - dags_wave2,
        'delay_minutes': 4,
        'task_duration': 31,  # Finish at T+35 (late ramp-down)
        'description': f'Ramp to 75% - {tasks_wave3} tasks'
    })
    
    # Peak waves - longest tasks to finish last (creating final ramp-down)
    # Distribute remaining DAGs evenly, with the last wave absorbing any remainder
    current_dag = dags_wave3
    dags_per_peak_wave = dags_peak // num_peak_waves
    for i in range(num_peak_waves):
        wave_num = 4 + i
        if i == num_peak_waves - 1:
            # Last peak wave gets all remaining DAGs
            dags_this_wave = num_dags - current_dag
        else:
            dags_this_wave = min(dags_per_peak_wave, num_dags - current_dag)
        
        waves.append({
            'wave': wave_num,
            'dag_start': current_dag,
            'dag_count': dags_this_wave,
            'delay_minutes': 5 + (i * 5),
            'task_duration': 35,  # Finish at T+40 (end of test)
            'description': f'Peak sustained - {peak_tasks} tasks'
        })
        current_dag += dags_this_wave
    
    return {
        'num_dags': num_dags,
        'tasks_per_dag': tasks_per_dag_peak,
        'peak_tasks': peak_tasks,
        'peak_duration': peak_duration,
        'waves': waves,
        'total_duration': 40
    }



def generate_dag_config(
    dag_num: int,
    wave_config: Dict,
    tasks_per_dag: int,
    set_num: int = 1,
    task_duration_secs: int = 120,
) -> Dict:
    """
    Generate configuration for a single DAG with batched short-lived tasks.

    Instead of long-running tasks, generates sequential batches of parallel tasks.
    Each batch has `tasks_per_dag` parallel tasks, each running for `task_duration_secs`.
    Batches are chained to sustain load for the full wave duration.

    Args:
        dag_num: DAG number (0-based)
        wave_config: Wave configuration for this DAG
        tasks_per_dag: Number of parallel tasks per batch
        set_num: Set number (1-based)
        task_duration_secs: Duration of each individual task in seconds
    """
    import math

    dag_id = f"factory_sustained_set_{set_num:02d}_dag_{dag_num:03d}"
    wave_num = wave_config['wave']
    delay_seconds = wave_config['delay_minutes'] * 60
    wave_duration_secs = wave_config['task_duration'] * 60  # total wave duration in seconds

    # Calculate number of sequential batches needed to sustain load
    num_batches = max(1, math.ceil(wave_duration_secs / task_duration_secs))

    # Build tasks list
    tasks_list = [
        {
            'task_id': 'wave_delay',
            'operator': 'airflow.operators.python.PythonOperator',
            'python_callable_name': 'wave_delay_task',
            'python_callable_file': '/usr/local/airflow/dags/performance_test_tasks_real.py',
            'op_kwargs': {
                'wave_num': wave_num,
                'delay_seconds': delay_seconds,
            }
        }
    ]

    # Create a sync task between each batch to gate the next batch
    for batch in range(num_batches):
        # Dependency: first batch depends on wave_delay, subsequent batches depend on previous sync task
        if batch == 0:
            batch_dependency = 'wave_delay'
        else:
            batch_dependency = f'sync_batch_{batch - 1:02d}'

        # Parallel tasks within this batch
        batch_task_ids = []
        for task_id in range(tasks_per_dag):
            tid = f'b{batch:02d}_task_{task_id:02d}'
            task = {
                'task_id': tid,
                'operator': 'airflow.operators.python.PythonOperator',
                'python_callable_name': 'real_load_task',
                'python_callable_file': '/usr/local/airflow/dags/performance_test_tasks_real.py',
                'op_kwargs': {
                    'task_id': task_id,
                    'duration': task_duration_secs,
                    'wave_num': wave_num,
                    'dag_num': dag_num,
                    'batch_num': batch,
                },
                'dependencies': [batch_dependency]
            }
            tasks_list.append(task)
            batch_task_ids.append(tid)

        # Add sync task that waits for all tasks in this batch before next batch starts
        if batch < num_batches - 1:
            sync_task = {
                'task_id': f'sync_batch_{batch:02d}',
                'operator': 'airflow.operators.python.PythonOperator',
                'python_callable_name': 'wave_delay_task',
                'python_callable_file': '/usr/local/airflow/dags/performance_test_tasks_real.py',
                'op_kwargs': {
                    'wave_num': wave_num,
                    'delay_seconds': 0,
                },
                'dependencies': batch_task_ids
            }
            tasks_list.append(sync_task)

    total_tasks_in_dag = num_batches * tasks_per_dag

    return {
        dag_id: {
            'default_args': {
                'owner': 'airflow',
                'depends_on_past': False,
                'email_on_failure': False,
                'email_on_retry': False,
                'retries': 0,
            },
            'description': f'Sustained Load Test - Set {set_num:02d} - DAG {dag_num:03d} - Wave {wave_num} - {num_batches} batches × {tasks_per_dag} tasks @ {task_duration_secs}s',
            'schedule': None,
            'catchup': False,
            'max_active_runs': 1,
            'max_active_tasks': tasks_per_dag + 5,
            'is_paused_upon_creation': False,
            'tags': ['dag-factory-test', 'sustained-load', 'performance', f'set-{set_num}', f'wave-{wave_num}', f'dag-{dag_num}'],
            'tasks': tasks_list
        }
    }



def generate_full_config(peak_tasks: int = 2000, peak_duration: int = 20, set_num: int = 1, task_duration_secs: int = 120) -> tuple:
    """Generate complete YAML configuration for a single set of sustained load test DAGs"""
    config_dict = {}
    
    # Calculate wave configuration
    wave_params = calculate_wave_config(peak_tasks, peak_duration)
    
    num_dags = wave_params['num_dags']
    tasks_per_dag = wave_params['tasks_per_dag']
    waves = wave_params['waves']
    
    # Generate DAGs according to wave configuration
    for wave in waves:
        wave_num = wave['wave']
        dag_start = wave['dag_start']
        dag_count = wave['dag_count']
        
        for i in range(dag_count):
            dag_num = dag_start + i
            if dag_num >= num_dags:
                break
                
            dag_config = generate_dag_config(
                dag_num=dag_num,
                wave_config=wave,
                tasks_per_dag=tasks_per_dag,
                set_num=set_num,
                task_duration_secs=task_duration_secs,
            )
            config_dict.update(dag_config)
    
    return config_dict, wave_params



def generate_trigger_dag(set_num: int, num_dags: int, tasks_per_dag: int, total_tasks: int,
                         peak_tasks: int, peak_duration: int, total_duration: int, waves: list) -> str:
    """Generate the master trigger DAG Python file content for a given set."""
    wave_log_lines = ""
    for wave in waves:
        wave_log_lines += f'    logger.info("  - Wave {wave["wave"]}: T+{wave["delay_minutes"]}min - {wave["description"]}")\n'

    return f'''"""
Master Trigger DAG for DAG Factory Sustained Load Test - Set {set_num:02d}

This DAG triggers all DAG Factory sustained test DAGs for set {set_num:02d} with wave-based timing.

Configuration:
- Generated by: generate_dag_factory_sustained.py --sets N
- Set: {set_num:02d}
- DAGs: {num_dags}
- Peak tasks per set: {total_tasks}
"""

from airflow import DAG
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import logging
import yaml
import os

default_args = {{
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}}

config_file = os.path.join(os.path.dirname(__file__), "dag_factory_config_sustained_set_{set_num:02d}.yaml")
try:
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    num_dags = len(config)
    first_dag = list(config.values())[0]
    tasks_per_dag = len([t for t in first_dag['tasks'] if t['task_id'] != 'wave_delay'])
    total_tasks = num_dags * tasks_per_dag
except Exception as e:
    num_dags = {num_dags}
    tasks_per_dag = {tasks_per_dag}
    total_tasks = {total_tasks}

dag = DAG(
    'trigger_dag_factory_sustained_test_set_{set_num:02d}',
    default_args=default_args,
    description=f'Master trigger for DAG Factory Sustained Load Test Set {set_num:02d} - {{total_tasks}} peak tasks',
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=['dag-factory-test', 'sustained-load', 'master-trigger', 'performance', 'long-duration', 'set-{set_num:02d}'],
)


def log_test_start(**context):
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info("DAG FACTORY SUSTAINED LOAD TEST - SET {set_num:02d} - STARTING")
    logger.info("=" * 80)
    logger.info(f"  {{num_dags}} DAGs x {{tasks_per_dag}} tasks = {{total_tasks}} peak capacity")
    logger.info("  Peak duration: {peak_duration} minutes")
    logger.info("  Total test duration: ~{total_duration} minutes")
    logger.info("=" * 80)
    return {{'test_start_time': datetime.now().isoformat()}}


def log_test_complete(**context):
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info("DAG FACTORY SUSTAINED LOAD TEST - SET {set_num:02d} - ALL DAGS TRIGGERED")
    logger.info("=" * 80)
    logger.info(f"All {{num_dags}} DAGs have been triggered with wave delays")
    logger.info("=" * 80)
    return {{'test_trigger_complete': datetime.now().isoformat()}}


start_task = PythonOperator(
    task_id='log_test_start',
    python_callable=log_test_start,
    dag=dag,
)

trigger_tasks = []

for dag_num in range(num_dags):
    dag_id = f"factory_sustained_set_{set_num:02d}_dag_{{dag_num:03d}}"

    trigger_task = TriggerDagRunOperator(
        task_id=f'trigger_{{dag_id}}',
        trigger_dag_id=dag_id,
        wait_for_completion=False,
        dag=dag,
    )

    trigger_tasks.append(trigger_task)
    start_task >> trigger_task

end_task = PythonOperator(
    task_id='log_test_complete',
    python_callable=log_test_complete,
    dag=dag,
)

for trigger_task in trigger_tasks:
    trigger_task >> end_task
'''


def main():
    """Generate and save YAML configuration and trigger DAGs for N sets"""
    parser = argparse.ArgumentParser(
        description='Generate DAG Factory sustained load test configuration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 1 set of 65 DAGs (default)
  python generate_dag_factory_sustained.py

  # Generate 2 sets of 65 DAGs (130 DAGs total, 2 master triggers)
  python generate_dag_factory_sustained.py --sets 2

  # Generate 4000 peak tasks with 3 sets
  python generate_dag_factory_sustained.py --peak-tasks 4000 --sets 3
        """
    )
    parser.add_argument(
        '--peak-tasks',
        type=int,
        default=2000,
        help='Peak number of concurrent tasks per set (default: 2000)'
    )
    parser.add_argument(
        '--peak-duration',
        type=int,
        default=20,
        help='Duration to sustain peak load in minutes (default: 20)'
    )
    parser.add_argument(
        '--sets',
        type=int,
        default=1,
        help='Number of sets of 65 DAGs to generate (default: 1)'
    )
    parser.add_argument(
        '--task-duration',
        type=int,
        default=120,
        help='Duration of each individual task in seconds (default: 120)'
    )
    args = parser.parse_args()

    peak_tasks = args.peak_tasks
    peak_duration = args.peak_duration
    num_sets = args.sets
    task_duration_secs = args.task_duration

    print(f"Generating sustained load test configuration...")
    print(f"  Sets: {num_sets}")
    print(f"  Peak tasks per set: {peak_tasks}")
    print(f"  Peak duration: {peak_duration} minutes")
    print(f"  Task duration: {task_duration_secs} seconds")

    for set_num in range(1, num_sets + 1):
        print(f"\n--- Set {set_num:02d} ---")

        # Generate configuration for this set
        config, params = generate_full_config(peak_tasks, peak_duration, set_num=set_num, task_duration_secs=task_duration_secs)

        num_dags = params['num_dags']
        tasks_per_dag = params['tasks_per_dag']
        total_duration = params['total_duration']
        total_tasks = num_dags * tasks_per_dag

        # Save YAML config file
        config_file = f'dag_factory_config_sustained_set_{set_num:02d}.yaml'
        with open(config_file, 'w') as f:
            f.write(f"# DAG Factory Sustained Load Test Configuration - Set {set_num:02d}\n")
            f.write("# Auto-generated configuration file\n")
            f.write("#\n")
            f.write(f"# Sustained Load Test - {peak_tasks} peak tasks\n")
            f.write("#\n")
            f.write(f"# Test Pattern ({total_duration} minutes total):\n")
            f.write(f"# - 0-5 min: Ramp up from 500 → {peak_tasks} tasks\n")
            f.write(f"# - 5-{5+peak_duration} min: Sustain peak load ({peak_duration} minutes)\n")
            f.write(f"# - {5+peak_duration}-{total_duration} min: Ramp down {peak_tasks} → 0 tasks\n")
            f.write("#\n")
            f.write(f"# Configuration:\n")
            f.write(f"# - Set {set_num:02d}: {num_dags} DAGs × {tasks_per_dag} tasks = {total_tasks} peak capacity\n")
            f.write(f"# - Task duration: 20 minutes\n")
            f.write(f"# - Peak sustained: {peak_duration} minutes\n")
            f.write(f"# - Total test duration: ~{total_duration} minutes\n")
            f.write("#\n")
            f.write("# Wave Pattern:\n")
            for wave in params['waves']:
                f.write(f"# - Wave {wave['wave']}: T+{wave['delay_minutes']}min - {wave['description']}\n")
            f.write("#\n\n")
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"  ✅ Config saved to {config_file}")
        print(f"     - {num_dags} DAGs generated")
        print(f"     - {tasks_per_dag} tasks per DAG")

        # Generate master trigger DAG file
        trigger_file = f'trigger_dag_factory_sustained_set_{set_num:02d}.py'
        trigger_content = generate_trigger_dag(
            set_num=set_num,
            num_dags=num_dags,
            tasks_per_dag=tasks_per_dag,
            total_tasks=total_tasks,
            peak_tasks=peak_tasks,
            peak_duration=peak_duration,
            total_duration=total_duration,
            waves=params['waves'],
        )
        with open(trigger_file, 'w') as f:
            f.write(trigger_content)

        print(f"  ✅ Trigger DAG saved to {trigger_file}")

    total_dags = num_sets * 65
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  {num_sets} set(s) × 65 DAGs = {total_dags} DAGs total")
    print(f"  {num_sets} master trigger DAG(s)")
    print(f"  {peak_tasks} peak tasks per set")
    print(f"  ~{total_duration} minute total test duration per set")
    print(f"\n⚠️  WARNING: This is a long-running test ({total_duration} minutes)!")
    print(f"   Make sure your MWAA environment can handle sustained load.")



if __name__ == '__main__':
    main()
