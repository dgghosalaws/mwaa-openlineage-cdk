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
    **context
):
    """
    Individual load task that creates REAL concurrent execution.
    
    This is a real Airflow task that consumes a worker slot.
    When many of these run simultaneously, they create actual load.
    
    Args:
        task_id: Task identifier
        duration: How long the task should run (seconds)
        wave_num: Wave number for logging
        dag_num: DAG number for logging
    """
    logger = logging.getLogger(__name__)
    start_time = time.time()
    
    # Log start (only for first and last task to reduce noise)
    if task_id == 0 or task_id % 10 == 9:  # Log every 10th task
        logger.info(
            f"Wave {wave_num} - DAG {dag_num} - Task {task_id} started "
            f"(duration: {duration}s)"
        )
    
    # Simulate work
    time.sleep(duration)
    
    end_time = time.time()
    actual_duration = end_time - start_time
    
    # Log completion (only for first and last task)
    if task_id == 0 or task_id % 10 == 9:
        logger.info(
            f"Wave {wave_num} - DAG {dag_num} - Task {task_id} completed in "
            f"{actual_duration:.1f}s"
        )
    
    return {
        'wave_num': wave_num,
        'dag_num': dag_num,
        'task_id': task_id,
        'duration': actual_duration,
        'start_time': start_time,
        'end_time': end_time
    }
