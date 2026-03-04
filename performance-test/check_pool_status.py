"""
Quick diagnostic DAG to check pool configuration and status
Upload this to S3 and trigger it to see actual pool settings
"""
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Pool
from airflow.settings import Session
from datetime import datetime
import logging

def check_pool_configuration(**context):
    """Check the actual pool configuration in the database"""
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("POOL CONFIGURATION CHECK")
    logger.info("=" * 80)
    
    session = Session()
    try:
        # Get all pools
        pools = session.query(Pool).all()
        
        logger.info(f"\nFound {len(pools)} pools:")
        logger.info("-" * 80)
        
        for pool in pools:
            logger.info(f"\nPool: {pool.pool}")
            logger.info(f"  Slots: {pool.slots}")
            logger.info(f"  Description: {pool.description}")
            logger.info(f"  Running Tasks: {pool.running_slots}")
            logger.info(f"  Queued Tasks: {pool.queued_slots}")
            logger.info(f"  Open Slots: {pool.open_slots}")
            
            # Check if this is default_pool
            if pool.pool == 'default_pool':
                logger.info("\n" + "!" * 80)
                logger.info("DEFAULT POOL STATUS:")
                logger.info(f"  Total Slots: {pool.slots}")
                logger.info(f"  Used Slots: {pool.running_slots}")
                logger.info(f"  Available Slots: {pool.open_slots}")
                logger.info(f"  Queued Tasks: {pool.queued_slots}")
                logger.info("!" * 80)
                
                if pool.slots < 2000:
                    logger.error(f"\n⚠️  WARNING: default_pool only has {pool.slots} slots!")
                    logger.error("⚠️  Expected 2000 slots based on configuration")
                    logger.error("⚠️  This will cause tasks to queue!")
                else:
                    logger.info(f"\n✅ default_pool has {pool.slots} slots - configuration is correct")
        
        logger.info("\n" + "=" * 80)
        
        return {
            'pools': [
                {
                    'name': p.pool,
                    'slots': p.slots,
                    'running': p.running_slots,
                    'queued': p.queued_slots,
                    'open': p.open_slots
                }
                for p in pools
            ]
        }
        
    finally:
        session.close()


def check_airflow_config(**context):
    """Check Airflow configuration values"""
    logger = logging.getLogger(__name__)
    from airflow.configuration import conf
    
    logger.info("=" * 80)
    logger.info("AIRFLOW CONFIGURATION CHECK")
    logger.info("=" * 80)
    
    config_keys = [
        ('core', 'parallelism'),
        ('core', 'max_active_tasks_per_dag'),
        ('core', 'max_active_runs_per_dag'),
        ('core', 'default_pool_task_slot_count'),
        ('scheduler', 'max_tis_per_query'),
    ]
    
    for section, key in config_keys:
        try:
            value = conf.get(section, key)
            logger.info(f"{section}.{key} = {value}")
        except Exception as e:
            logger.warning(f"{section}.{key} = NOT SET ({e})")
    
    logger.info("=" * 80)


with DAG(
    dag_id='diagnostic_pool_check',
    description='Check pool configuration and status',
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['diagnostic', 'pool-check'],
) as dag:
    
    check_config = PythonOperator(
        task_id='check_airflow_config',
        python_callable=check_airflow_config,
    )
    
    check_pools = PythonOperator(
        task_id='check_pool_configuration',
        python_callable=check_pool_configuration,
    )
    
    check_config >> check_pools
