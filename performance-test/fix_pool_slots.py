"""
One-time DAG to update default_pool slots to 2000

This is needed because MWAA's core.default_pool_task_slot_count configuration
only applies to NEW pools, not existing ones. We need to manually update the pool.

Upload this, trigger it once, then delete it.
"""
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Pool
from airflow.settings import Session
from datetime import datetime
import logging

def update_default_pool_slots(**context):
    """Update default_pool to have 2000 slots"""
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info("UPDATING DEFAULT POOL SLOTS")
    logger.info("=" * 80)
    
    session = Session()
    try:
        # Get default_pool
        pool = session.query(Pool).filter(Pool.pool == 'default_pool').first()
        
        if pool:
            old_slots = pool.slots
            logger.info(f"\nCurrent default_pool slots: {old_slots}")
            
            # Update to 2000 slots
            pool.slots = 2000
            session.commit()
            
            logger.info(f"✅ Updated default_pool slots: {old_slots} → 2000")
            logger.info("\n" + "=" * 80)
            logger.info("SUCCESS! default_pool now has 2000 slots")
            logger.info("You can now run up to 2000 concurrent tasks")
            logger.info("=" * 80)
            
            return {
                'old_slots': old_slots,
                'new_slots': 2000,
                'status': 'success'
            }
        else:
            logger.error("❌ default_pool not found!")
            return {
                'status': 'error',
                'message': 'default_pool not found'
            }
            
    except Exception as e:
        logger.error(f"❌ Error updating pool: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def verify_pool_update(**context):
    """Verify the pool was updated correctly"""
    logger = logging.getLogger(__name__)
    
    session = Session()
    try:
        pool = session.query(Pool).filter(Pool.pool == 'default_pool').first()
        
        if pool:
            logger.info("=" * 80)
            logger.info("VERIFICATION")
            logger.info("=" * 80)
            logger.info(f"Pool: {pool.pool}")
            logger.info(f"Slots: {pool.slots}")
            logger.info(f"Running: {pool.running_slots}")
            logger.info(f"Queued: {pool.queued_slots}")
            logger.info(f"Open: {pool.open_slots}")
            logger.info("=" * 80)
            
            if pool.slots == 2000:
                logger.info("✅ VERIFIED: Pool has 2000 slots")
            else:
                logger.error(f"❌ FAILED: Pool has {pool.slots} slots, expected 2000")
                
            return {
                'slots': pool.slots,
                'verified': pool.slots == 2000
            }
    finally:
        session.close()


with DAG(
    dag_id='fix_default_pool_slots',
    description='One-time fix: Update default_pool to 2000 slots',
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['fix', 'pool', 'one-time'],
) as dag:
    
    update_pool = PythonOperator(
        task_id='update_default_pool_slots',
        python_callable=update_default_pool_slots,
    )
    
    verify = PythonOperator(
        task_id='verify_pool_update',
        python_callable=verify_pool_update,
    )
    
    update_pool >> verify
