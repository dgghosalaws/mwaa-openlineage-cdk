"""
MWAA 3.0.6 Sustained Load Test - Extended Duration with Peak Hold

100 DAGs × 70 tasks = 7000 tasks at peak
40 minute total duration with 20 minute peak hold

Wave Pattern (20-minute task duration):
- Wave 1: 20 DAGs × 70 tasks = 1400 tasks (ramp up start)
- Wave 2: 40 DAGs × 70 tasks = 2800 tasks (50% to peak)
- Wave 3: 60 DAGs × 70 tasks = 4200 tasks (75% to peak)
- Wave 4: 80 DAGs × 70 tasks = 5600 tasks (approaching peak)
- Wave 5: 100 DAGs × 70 tasks = 7000 tasks (PEAK - sustained for 20 min)
- Wave 6: 100 DAGs × 70 tasks = 7000 tasks (PEAK continuation)

Timeline:
T+0:00  → Wave 1 starts (1400 tasks)
T+5:00  → Wave 2 starts (2800 tasks)
T+10:00 → Wave 3 starts (4200 tasks)
T+15:00 → Wave 4 starts (5600 tasks)
T+20:00 → Wave 5 starts (7000 tasks - PEAK BEGINS)
T+25:00 → Wave 6 starts (7000 tasks - PEAK SUSTAINED)
T+30:00 → Wave 1 completes (5600 tasks remain)
T+35:00 → Wave 2 completes (4200 tasks remain)
T+40:00 → Wave 3 completes (2800 tasks remain)
T+45:00 → Wave 4 completes (1400 tasks remain)
T+50:00 → Wave 5 completes (700 tasks remain)
T+55:00 → Wave 6 completes (all done)

Peak load (7000 tasks) sustained from T+20:00 to T+40:00 (20 minutes)
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import time
import logging

# ============================================
# CONFIGURATION
# ============================================

NUM_DAGS = 100
TASKS_PER_DAG = 70
TASK_DURATION = 1200  # 20 minutes

# Wave configuration with 5-minute intervals
WAVE_CONFIG = [
    {'wave': 1, 'dag_start': 0,   'dag_end': 20,  'delay': 0,    'description': '1400 tasks - ramp up'},
    {'wave': 2, 'dag_start': 20,  'dag_end': 40,  'delay': 300,  'description': '2800 tasks - 50% to peak'},
    {'wave': 3, 'dag_start': 40,  'dag_end': 60,  'delay': 600,  'description': '4200 tasks - 75% to peak'},
    {'wave': 4, 'dag_start': 60,  'dag_end': 80,  'delay': 900,  'description': '5600 tasks - approaching peak'},
    {'wave': 5, 'dag_start': 80,  'dag_end': 100, 'delay': 1200, 'description': '7000 tasks - PEAK'},
    {'wave': 6, 'dag_start': 80,  'dag_end': 100, 'delay': 1500, 'description': '7000 tasks - PEAK sustained'},
]

# ============================================
# Helper Functions
# ============================================

def get_wave_for_dag(dag_num: int, wave_num: int) -> dict:
    """Determine which wave configuration applies to this DAG."""
    for wave in WAVE_CONFIG:
        if wave['wave'] == wave_num and wave['dag_start'] <= dag_num < wave['dag_end']:
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
    logger.info(f"Waiting {delay} seconds ({delay/60:.1f} minutes) before starting tasks...")
    logger.info("=" * 80)
    
    time.sleep(delay)
    
    logger.info(f"DAG {dag_num} - Wave {wave_num} delay complete. Starting tasks now.")
    
    return {
        'dag_num': dag_num,
        'wave_num': wave_num,
        'delay': delay,
        'start_time': datetime.now().isoformat()
    }


def sustained_load_task(dag_num: int, wave_num: int, task_id: int, duration: int = TASK_DURATION, **context):
    """Simulates a long-running task for sustained load testing."""
    start_time = time.time()
    logger = logging.getLogger(__name__)
    
    logger.info(f"Wave {wave_num} - DAG {dag_num} - Task {task_id} started at {datetime.now()}")
    logger.info(f"Task will run for {duration} seconds ({duration/60:.1f} minutes)")
    
    # Simulate work with periodic logging every 2 minutes
    elapsed = 0
    log_interval = 120  # Log every 2 minutes
    
    while elapsed < duration:
        sleep_time = min(log_interval, duration - elapsed)
        time.sleep(sleep_time)
        elapsed = time.time() - start_time
        
        if elapsed < duration:
            remaining = duration - elapsed
            logger.info(
                f"Wave {wave_num} - DAG {dag_num} - Task {task_id} running... "
                f"{elapsed:.0f}s / {duration}s ({remaining/60:.1f} min remaining)"
            )
    
    end_time = time.time()
    actual_duration = end_time - start_time
    
    logger.info(
        f"Wave {wave_num} - DAG {dag_num} - Task {task_id} completed in "
        f"{actual_duration:.1f}s ({actual_duration/60:.1f} minutes)"
    )
    
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

# Create DAGs for each wave
# Waves 5 and 6 use the same DAGs (80-99) to sustain peak load
for wave_num in range(1, 7):
    wave_info = WAVE_CONFIG[wave_num - 1]
    
    for dag_num in range(wave_info['dag_start'], wave_info['dag_end']):
        dag_id = f'sustained_load_wave{wave_num}_{dag_num:03d}'
        
        with DAG(
            dag_id=dag_id,
            default_args=default_args,
            description=f'Sustained Load - Wave {wave_num} - DAG {dag_num} - {TASKS_PER_DAG} tasks × 20min',
            schedule=None,
            start_date=datetime(2024, 1, 1),
            catchup=False,
            max_active_runs=1,
            is_paused_upon_creation=False,
            tags=['sustained-load', 'long-duration', f'wave-{wave_num}', f'dag-{dag_num}'],
        ) as dag:
            
            # Start delay task
            delay_task = PythonOperator(
                task_id='wave_start_delay',
                python_callable=wave_start_delay,
                op_kwargs={
                    'dag_num': dag_num,
                    'wave_num': wave_num,
                    'delay': wave_info['delay']
                },
            )
            
            # Create load tasks
            load_tasks = []
            for task_id in range(TASKS_PER_DAG):
                task = PythonOperator(
                    task_id=f'task_{task_id:02d}',
                    python_callable=sustained_load_task,
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
SUSTAINED LOAD TEST - 40 MINUTES WITH 20 MINUTE PEAK

CONFIGURATION:
- 100 DAGs × 70 tasks = 7000 tasks at peak
- Task duration: 20 minutes
- Total test duration: ~55 minutes
- Peak load duration: 20 minutes (T+20 to T+40)

DEPLOYMENT:
aws s3 cp test_sustained_load.py s3://YOUR-MWAA-BUCKET/dags/

TRIGGER:
Use master trigger DAG or trigger all manually

TIMELINE:
T+0:00  → Trigger all DAGs
T+0:00  → Wave 1: 1400 tasks (20 DAGs start immediately)
T+5:00  → Wave 2: 2800 tasks (40 DAGs total)
T+10:00 → Wave 3: 4200 tasks (60 DAGs total)
T+15:00 → Wave 4: 5600 tasks (80 DAGs total)
T+20:00 → Wave 5: 7000 tasks (100 DAGs - PEAK BEGINS)
T+25:00 → Wave 6: 7000 tasks (100 DAGs - PEAK SUSTAINED)
T+30:00 → Wave 1 completes (5600 tasks remain)
T+35:00 → Wave 2 completes (4200 tasks remain)
T+40:00 → Wave 3 completes (2800 tasks remain) - PEAK ENDS
T+45:00 → Wave 4 completes (1400 tasks remain)
T+50:00 → Wave 5 completes (700 tasks remain)
T+55:00 → Wave 6 completes (all done)

PEAK LOAD PERIOD:
- From T+20:00 to T+40:00 (20 minutes)
- 7000 tasks running continuously
- Tests sustained high load capacity
- Validates worker stability over time

MONITORING:
- Pool: Should show consistent utilization during peak
- Workers: Should maintain 25 workers during peak
- CPU/Memory: Monitor for degradation over time
- Database: Watch connection pool during sustained load
- Filter by tag: sustained-load

EXPECTED BEHAVIOR:
- Gradual ramp up over 20 minutes
- Sustained peak load for 20 minutes
- Gradual ramp down over 15 minutes
- No performance degradation during peak
- Stable resource utilization

CLEANUP:
aws s3 rm s3://YOUR-MWAA-BUCKET/dags/test_sustained_load.py
"""
