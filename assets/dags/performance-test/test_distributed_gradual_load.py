"""
MWAA 3.0.6 Distributed Gradual Load Test - Multiple DAGs with Waves

This test distributes the gradual load across multiple DAGs to avoid per-DAG limits.
Each wave triggers a subset of DAGs, gradually ramping from 650 to 2600 concurrent tasks.

Test Pattern:
- Wave 1: 25 DAGs × 26 tasks = 650 tasks (baseline)
- Wave 2: 38 DAGs × 26 tasks = 988 tasks (52% increase)
- Wave 3: 50 DAGs × 26 tasks = 1300 tasks (100% increase)
- Wave 4: 75 DAGs × 26 tasks = 1950 tasks (200% increase)
- Wave 5: 100 DAGs × 26 tasks = 2600 tasks (300% increase - target)

Each wave runs for 2 minutes with 30-second delays between waves.
Waves overlap so all 2600 tasks run simultaneously at peak (T+2:30).

CloudWatch Metrics to Monitor:
- Worker auto-scaling behavior across waves
- Queue depth (QueuedTasks metric)
- CPU/Memory utilization trends
- Database connections
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import time
import logging

# ============================================
# CONFIGURATION
# ============================================

# Total number of DAGs
NUM_DAGS = 100

# Tasks per DAG
TASKS_PER_DAG = 26

# Task duration (seconds)
TASK_DURATION = 120  # 2 minutes

# Wave configuration - which DAGs belong to which wave
# Delays are set so all waves overlap and run simultaneously at peak
# Each wave runs for 120s, so delays must be < 120s apart for overlap
WAVE_CONFIG = [
    {'wave': 1, 'dag_start': 0,   'dag_end': 25,  'delay': 30,  'description': 'Baseline - 650 tasks'},
    {'wave': 2, 'dag_start': 25,  'dag_end': 38,  'delay': 60,  'description': '52% increase - 988 tasks'},
    {'wave': 3, 'dag_start': 38,  'dag_end': 50,  'delay': 90,  'description': '100% increase - 1300 tasks'},
    {'wave': 4, 'dag_start': 50,  'dag_end': 75,  'delay': 120, 'description': '200% increase - 1950 tasks'},
    {'wave': 5, 'dag_start': 75,  'dag_end': 100, 'delay': 150, 'description': '300% increase - 2600 tasks'},
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
    """
    Delays the start of tasks based on wave number.
    This ensures waves start at staggered intervals.
    """
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info(f"DAG {dag_num} - Wave {wave_num} Starting")
    logger.info("=" * 80)
    logger.info(f"Waiting {delay} seconds before starting tasks...")
    logger.info(f"This allows previous waves to establish baseline load")
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
    """
    Simulates a task in the distributed gradual load test.
    
    Args:
        dag_num: DAG number (0-99)
        wave_num: Wave number (1-5)
        task_id: Task identifier within the DAG (0-19)
        duration: How long the task should run
    """
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

# Create 100 DAGs dynamically, each assigned to a wave
for dag_num in range(NUM_DAGS):
    wave_info = get_wave_for_dag(dag_num)
    
    if wave_info is None:
        continue
    
    wave_num = wave_info['wave']
    wave_delay = wave_info['delay']
    
    dag_id = f'perf_test_wave{wave_num}_{dag_num:03d}'
    
    with DAG(
        dag_id=dag_id,
        default_args=default_args,
        description=f'Wave {wave_num} - DAG {dag_num}/{NUM_DAGS} - {TASKS_PER_DAG} tasks',
        schedule=None,
        start_date=datetime(2024, 1, 1),
        catchup=False,
        max_active_runs=1,
        is_paused_upon_creation=False,  # Auto-enable all 100 DAGs
        tags=['capacity-test', 'distributed-gradual', f'wave-{wave_num}', f'dag-{dag_num}'],
    ) as dag:
        
        # Start delay task - ensures this wave starts at the right time
        delay_task = PythonOperator(
            task_id='wave_start_delay',
            python_callable=wave_start_delay,
            op_kwargs={
                'dag_num': dag_num,
                'wave_num': wave_num,
                'delay': wave_delay
            },
        )
        
        # Create load tasks for this DAG
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
        
        # Set dependencies: delay first, then all tasks run in parallel
        delay_task >> load_tasks
        
        # Register DAG in globals so Airflow can find it
        globals()[dag_id] = dag


# ============================================
# Usage Instructions
# ============================================
"""
HOW TO USE THIS DISTRIBUTED GRADUAL LOAD TEST:

1. DEPLOY THE DAG:
   aws s3 cp test_distributed_gradual_load.py s3://YOUR-MWAA-BUCKET/dags/ --region YOUR-REGION

2. WAIT FOR DAGS TO APPEAR:
   - This creates 100 DAGs with wave assignments (24 tasks each):
     * Wave 1: perf_test_wave1_000 through perf_test_wave1_024 (25 DAGs = 600 tasks)
     * Wave 2: perf_test_wave2_025 through perf_test_wave2_037 (13 DAGs = 312 tasks)
     * Wave 3: perf_test_wave3_038 through perf_test_wave3_049 (12 DAGs = 288 tasks)
     * Wave 4: perf_test_wave4_050 through perf_test_wave4_074 (25 DAGs = 600 tasks)
     * Wave 5: perf_test_wave5_075 through perf_test_wave5_099 (25 DAGs = 600 tasks)
   - Wait 1-2 minutes for all DAGs to be parsed

3. TRIGGER ALL DAGS SIMULTANEOUSLY:
   
   Using AWS CLI (recommended):
   ```bash
   # Trigger all 100 DAGs at once
   for i in {0..99}; do
     WAVE=$(( (i < 25) ? 1 : (i < 38) ? 2 : (i < 50) ? 3 : (i < 75) ? 4 : 5 ))
     aws mwaa create-web-login-token --name mwaa-openlineage-dev --region us-east-2 > /dev/null 2>&1 &
     # Use Airflow API to trigger
     dag_id="perf_test_wave${WAVE}_$(printf '%03d' $i)"
     echo "Triggering $dag_id"
   done
   ```
   
   Or use Airflow UI:
   - Filter by tag: "distributed-gradual"
   - Select all 100 DAGs
   - Click "Trigger DAG" button

4. WHAT HAPPENS AUTOMATICALLY:
   
   Time 0s (All DAGs triggered):
   - All 100 DAGs start
   - Wave 1 DAGs (0-24): Start immediately after 30s delay
   - Wave 2 DAGs (25-37): Wait 60s (1 min) before starting
   - Wave 3 DAGs (38-49): Wait 90s (1.5 min) before starting
   - Wave 4 DAGs (50-74): Wait 120s (2 min) before starting
   - Wave 5 DAGs (75-99): Wait 150s (2.5 min) before starting
   
   Time 30s - Wave 1 Starts:
   - 25 DAGs × 24 tasks = 600 tasks running
   - Workers: ~8 (600 ÷ 80 tasks per worker)
   - Baseline load established
   
   Time 60s - Wave 2 Starts:
   - Wave 1 still running (90s remaining)
   - 13 more DAGs start: 13 × 24 = 312 additional tasks
   - Total: 912 tasks running
   - Workers: ~12
   
   Time 90s - Wave 3 Starts:
   - Wave 1 still running (60s remaining)
   - Wave 2 still running (90s remaining)
   - 12 more DAGs start: 12 × 24 = 288 additional tasks
   - Total: 1200 tasks running
   - Workers: ~15
   
   Time 120s - Wave 4 Starts:
   - Wave 1 still running (30s remaining)
   - Wave 2 still running (60s remaining)
   - Wave 3 still running (90s remaining)
   - 25 more DAGs start: 25 × 24 = 600 additional tasks
   - Total: 1800 tasks running
   - Workers: ~23
   
   Time 150s - Wave 5 Starts (PEAK LOAD):
   - Wave 1 still running (0s remaining - about to finish)
   - Wave 2 still running (30s remaining)
   - Wave 3 still running (60s remaining)
   - Wave 4 still running (90s remaining)
   - 25 more DAGs start: 25 × 24 = 600 additional tasks
   - Total: 2400 tasks running (PEAK LOAD)
   - Workers: 25 (maximum)
   
   Time 150s - Wave 1 Completes:
   - 1800 tasks remain running
   
   Time 180s - Wave 2 Completes:
   - 1488 tasks remain running
   
   Time 210s - Wave 3 Completes:
   - 1200 tasks remain running
   
   Time 240s - Wave 4 Completes:
   - 600 tasks remain running
   
   Time 270s - Wave 5 Completes:
   - All done!

5. MONITOR DURING TEST:
   
   CloudWatch Dashboard:
   - Watch worker count increase: 7 → 10 → 13 → 19 → 25
   - QueuedTasks should remain low (good scheduling)
   - RunningTasks increases with each wave
   - CPU/Memory trends across waves
   
   Airflow UI:
   - Filter by wave tags to see each wave's status
   - Grid view shows staggered start times
   - Total running tasks across all DAGs

6. EXPECTED TIMELINE:
   
   0:00 - Trigger all 100 DAGs
   0:30 - Wave 1 starts (600 tasks)
   1:00 - Wave 2 starts (912 tasks total)
   1:30 - Wave 3 starts (1200 tasks total)
   2:00 - Wave 4 starts (1800 tasks total)
   2:30 - Wave 5 starts (2400 tasks total - PEAK)
   2:30 - Wave 1 completes (1800 tasks remain)
   3:00 - Wave 2 completes (1488 tasks remain)
   3:30 - Wave 3 completes (1200 tasks remain)
   4:00 - Wave 4 completes (600 tasks remain)
   4:30 - Wave 5 completes (all done)
   
   Total test duration: ~4.5 minutes

7. ANALYZE RESULTS:
   
   Success Indicators:
   - All 100 DAGs completed successfully
   - Workers scaled smoothly: 7 → 10 → 13 → 19 → 25
   - No tasks stuck in queued state
   - CPU/Memory stayed below 90%
   - Database connections stable
   
   Warning Signs:
   - Some DAGs failed
   - Workers didn't scale to 25
   - Tasks stuck in queued state
   - CPU/Memory > 95%

8. CLEANUP:
   
   aws s3 rm s3://YOUR-MWAA-BUCKET/dags/test_distributed_gradual_load.py --region YOUR-REGION

ADVANTAGES:
- Bypasses per-DAG limits (each DAG only has 24 tasks)
- Gradual load ramp (600 → 2400 tasks)
- Automatic wave timing (no manual triggering between waves)
- Realistic multi-DAG workload
- Easy to monitor by wave (use wave tags)

COMPARISON TO SINGLE DAG APPROACH:
- Single DAG: Hits per-DAG max_active_tasks limit at 500 tasks
- Distributed: No per-DAG limits, smooth scaling to 2400 tasks
- Both test same capacity, but distributed approach actually works!
"""
