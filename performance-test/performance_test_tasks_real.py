"""
Real task functions for DAG Factory performance tests with actual concurrent tasks

These functions create REAL Airflow task instances (not simulated).
Each task consumes an actual worker slot.
"""

import time
import logging
from datetime import datetime


def wave_delay_task(wave_num: int, delay_seconds: int, **context):
    """
    Delays the start of a wave to create staggered load.
    
    Args:
        wave_num: Wave number (1-5)
        delay_seconds: How long to wait before starting tasks
    """
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info(f"Wave {wave_num} Starting")
    logger.info(f"Waiting {delay_seconds} seconds ({delay_seconds/60:.1f} minutes)")
    logger.info("=" * 80)
    
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    
    logger.info(f"Wave {wave_num} delay complete. Starting tasks now.")
    
    return {
        'wave_num': wave_num,
        'delay': delay_seconds,
        'start_time': datetime.now().isoformat()
    }


def real_load_task(
    task_id: int,
    duration: int,
    wave_num: int,
    dag_num: int,
    total_duration: int = 0,
    **context
):
    """
    Individual load task that creates REAL concurrent execution.
    
    Runs in a loop: sleeps for `duration` seconds, then repeats until
    `total_duration` is reached. This sustains load with short-lived
    sleep cycles while keeping YAML configs small.
    
    Args:
        task_id: Task identifier
        duration: How long each cycle sleeps (seconds)
        wave_num: Wave number for logging
        dag_num: DAG number for logging
        total_duration: Total time this task should run (seconds). If 0, runs once.
    """
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    # If no total_duration, run a single cycle
    if total_duration <= 0:
        total_duration = duration

    cycle = 0
    elapsed = 0
    while elapsed < total_duration:
        remaining = total_duration - elapsed
        sleep_time = min(duration, remaining)
        
        if task_id == 0 or task_id % 10 == 9:
            logger.info(
                f"Wave {wave_num} - DAG {dag_num} - Task {task_id} - "
                f"Cycle {cycle} started (sleep: {sleep_time}s, elapsed: {elapsed:.0f}s/{total_duration}s)"
            )
        
        time.sleep(sleep_time)
        cycle += 1
        elapsed = time.time() - start_time
    
    actual_duration = time.time() - start_time
    
    if task_id == 0 or task_id % 10 == 9:
        logger.info(
            f"Wave {wave_num} - DAG {dag_num} - Task {task_id} completed "
            f"{cycle} cycles in {actual_duration:.1f}s"
        )
    
    return {
        'wave_num': wave_num,
        'dag_num': dag_num,
        'task_id': task_id,
        'duration': actual_duration,
        'cycles': cycle,
        'start_time': start_time,
        'end_time': time.time()
    }
