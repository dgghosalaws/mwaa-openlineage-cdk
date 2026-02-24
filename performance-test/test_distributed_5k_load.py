"""
MWAA 3.0.6 Distributed Load Test - 5000 Tasks at Peak

200 DAGs × 25 tasks = 5000 tasks at peak
Target: 4000 running + 1000 queued

Wave Pattern:
- Wave 1: 50 DAGs × 25 tasks = 1250 tasks
- Wave 2: 75 DAGs × 25 tasks = 1875 tasks  
- Wave 3: 100 DAGs × 25 tasks = 2500 tasks
- Wave 4: 150 DAGs × 25 tasks = 3750 tasks
- Wave 5: 200 DAGs × 25 tasks = 5000 tasks (PEAK)

Each wave runs for 2 minutes with 30-second delays.
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import time
import logging

# ============================================
# CONFIGURATION
# ============================================

NUM_DAGS = 200
TASKS_PER_DAG = 25
TASK_DURATION = 120  # 2 minutes

WAVE_CONFIG = [
    {'wave': 1, 'dag_start': 0,   'dag_end': 50,   'delay': 30,  'description': '1250 tasks'},
    {'wave': 2, 'dag_start': 50,  'dag_end': 75,   'delay': 60,  'description': '1875 tasks'},
    {'wave': 3, 'dag_start': 75,  'dag_end': 100,  'delay': 90,  'description': '2500 tasks'},
    {'wave': 4, 'dag_start': 100, 'dag_end': 150,  'delay': 120, 'description': '3750 tasks'},
    {'wave': 5, 'dag_start': 150, 'dag_end': 200,  'delay': 150, 'description': '5000 tasks'},
]

# ============================================
# Helper Functions
# ============================================

def get_wave_for_dag(dag_num: int) -> dict:
    """Determine which wave a DAG belongs to."""
    for wave in WAVE_CONFIG:
        if wave['dag_start'] <= dag_num < wave['dag_end']:
            return wave
    return None


# ============================================
# Task Functions
# ============================================

def wave_start_delay(dag_num: int, wave_num: int, delay: int, **context):
    """Delays the start of tasks based on wave number."""
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info(f"DAG {dag_num} - Wave {wave_num} Starting")
    logger.info("=" * 80)
    logger.info(f"Waiting {delay} seconds before starting tasks...")
    logger.info("=" * 80)
    
    time.sleep(delay)
    
    logger.info(f"DAG {dag_num} - Wave {wave_num} delay complete. Starting tasks now.")
    
    return {
        'dag_num': dag_num,
        'wave_num': wave_num,
        'delay': delay,
        'start_time': datetime.now().isoformat()
    }


def load_task(dag_num: int, wave_num: int, task_id: int, duration: int = TASK_DURATION, **context):
    """Simulates a task in the distributed load test."""
    start_time = time.time()
    logger = logging.getLogger(__name__)
    
    logger.info(f"Wave {wave_num} - DAG {dag_num} - Task {task_id} started at {datetime.now()}")
    
    # Simulate work with periodic logging
    elapsed = 0
    while elapsed < duration:
        sleep_time = min(30, duration - elapsed)
        time.sleep(sleep_time)
        elapsed = time.time() - start_time
        
        if elapsed < duration:
            logger.info(f"Wave {wave_num} - DAG {dag_num} - Task {task_id} running... {elapsed:.0f}s / {duration}s")
    
    end_time = time.time()
    actual_duration = end_time - start_time
    
    logger.info(f"Wave {wave_num} - DAG {dag_num} - Task {task_id} completed in {actual_duration:.1f}s")
    
    return {
        'wave_num': wave_num,
        'dag_num': dag_num,
        'task_id': task_id,
        'duration': actual_duration
    }


# ============================================
# DAG Generation
# ============================================

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}

# Create 200 DAGs dynamically
for dag_num in range(NUM_DAGS):
    wave_info = get_wave_for_dag(dag_num)
    
    if wave_info is None:
        continue
    
    wave_num = wave_info['wave']
    wave_delay = wave_info['delay']
    
    dag_id = f'perf_5k_wave{wave_num}_{dag_num:03d}'
    
    with DAG(
        dag_id=dag_id,
        default_args=default_args,
        description=f'5K Test - Wave {wave_num} - DAG {dag_num}/{NUM_DAGS} - {TASKS_PER_DAG} tasks',
        schedule=None,
        start_date=datetime(2024, 1, 1),
        catchup=False,
        max_active_runs=1,
        is_paused_upon_creation=False,
        tags=['capacity-test-5k', 'distributed-5k', f'wave-{wave_num}', f'dag-{dag_num}'],
    ) as dag:
        
        # Start delay task
        delay_task = PythonOperator(
            task_id='wave_start_delay',
            python_callable=wave_start_delay,
            op_kwargs={
                'dag_num': dag_num,
                'wave_num': wave_num,
                'delay': wave_delay
            },
        )
        
        # Create load tasks
        load_tasks = []
        for task_id in range(TASKS_PER_DAG):
            task = PythonOperator(
                task_id=f'task_{task_id:02d}',
                python_callable=load_task,
                op_kwargs={
                    'dag_num': dag_num,
                    'wave_num': wave_num,
                    'task_id': task_id,
                    'duration': TASK_DURATION
                },
                pool='default_pool',
            )
            load_tasks.append(task)
        
        # Set dependencies
        delay_task >> load_tasks
        
        # Register DAG
        globals()[dag_id] = dag


# ============================================
# Usage Instructions
# ============================================
"""
5000 TASK LOAD TEST

CONFIGURATION:
- 200 DAGs × 25 tasks = 5000 tasks at peak
- Expected: 4000 running + 1000 queued
- Duration: 4.5 minutes

DEPLOYMENT:
aws s3 cp test_distributed_5k_load.py s3://YOUR-BUCKET/dags/

TRIGGER:
Use master trigger DAG or trigger all manually

TIMELINE:
T+0:00  → Trigger all 200 DAGs
T+0:30  → Wave 1: 1250 tasks
T+1:00  → Wave 2: 1875 tasks
T+1:30  → Wave 3: 2500 tasks
T+2:00  → Wave 4: 3750 tasks
T+2:30  → Wave 5: 5000 tasks (PEAK - 4000 running, 1000 queued)
T+4:30  → Complete

MONITORING:
- Pool: Should show 4000/5000 used (if pool = 5000)
- Workers: Should scale to maximum
- Queued: ~1000 tasks at peak
- Filter by tag: capacity-test-5k
"""
