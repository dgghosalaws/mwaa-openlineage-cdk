"""
OpenLineage Demo DAG

This DAG demonstrates OpenLineage lineage capture with:
1. Configuration verification
2. Connectivity testing
3. Simple SQL operations to generate lineage
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
import logging

logger = logging.getLogger(__name__)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}


def verify_openlineage_config(**context):
    """Verify OpenLineage native provider is configured"""
    from airflow.configuration import conf
    
    logger.info("=" * 60)
    logger.info("OpenLineage Native Provider Configuration")
    logger.info("=" * 60)
    
    # Check Airflow configuration for OpenLineage settings
    try:
        transport = conf.get('openlineage', 'transport', fallback='NOT_SET')
        namespace = conf.get('openlineage', 'namespace', fallback='NOT_SET')
        disabled = conf.get('openlineage', 'disabled', fallback='False')
        
        logger.info(f"Transport: {transport[:100]}..." if len(transport) > 100 else f"Transport: {transport}")
        logger.info(f"Namespace: {namespace}")
        logger.info(f"Disabled: {disabled}")
    except Exception as e:
        logger.warning(f"Could not read OpenLineage config: {str(e)}")
        transport = 'NOT_SET'
        namespace = 'NOT_SET'
    
    logger.info("=" * 60)
    
    # Check if listener is registered
    try:
        from airflow.listeners.listener import get_listener_manager
        listener_manager = get_listener_manager()
        listeners = listener_manager.listeners if hasattr(listener_manager, 'listeners') else []
        listener_names = [type(l).__name__ for l in listeners]
        
        logger.info(f"Registered listeners: {listener_names}")
        has_openlineage = any('OpenLineage' in name for name in listener_names)
        logger.info(f"OpenLineage listener registered: {has_openlineage}")
        
        if has_openlineage:
            logger.info("✅ Native OpenLineage provider is active!")
        else:
            logger.warning("⚠️  OpenLineage listener not found (may still work)")
    except Exception as e:
        logger.warning(f"Could not check listener registration: {str(e)}")
    
    logger.info("✅ OpenLineage native provider check complete!")
    return {
        'transport': transport,
        'namespace': namespace,
        'disabled': disabled
    }


def test_marquez_connectivity(**context):
    """Test connectivity to Marquez server"""
    from airflow.configuration import conf
    import requests
    import json as json_lib
    
    # Extract Marquez URL from transport config
    try:
        transport_str = conf.get('openlineage', 'transport', fallback='{}')
        transport = json_lib.loads(transport_str)
        marquez_url = transport.get('url', '')
    except Exception as e:
        logger.error(f"Could not parse transport config: {str(e)}")
        marquez_url = ''
    
    if not marquez_url:
        logger.warning("⚠️  Marquez URL not found in config, skipping connectivity test")
        return {"status": "skipped", "reason": "no_url"}
    
    logger.info(f"Testing connection to: {marquez_url}")
    
    try:
        # Test API endpoint
        response = requests.get(f"{marquez_url}/api/v1/namespaces", timeout=10)
        response.raise_for_status()
        
        namespaces = response.json().get('namespaces', [])
        logger.info(f"✅ Successfully connected to Marquez!")
        logger.info(f"Found {len(namespaces)} namespace(s)")
        
        for ns in namespaces:
            logger.info(f"  - {ns['name']}")
        
        return {
            "status": "success",
            "namespaces_count": len(namespaces),
            "marquez_url": marquez_url
        }
        
    except requests.exceptions.Timeout:
        logger.error(f"❌ Timeout connecting to {marquez_url}")
        raise
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ Connection error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}")
        raise


def generate_sample_data(**context):
    """Generate sample data to demonstrate lineage"""
    import random
    
    # Simulate data processing
    data = {
        'records_processed': random.randint(100, 1000),
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'success'
    }
    
    logger.info(f"Generated sample data: {data}")
    
    # Push to XCom for downstream tasks
    context['task_instance'].xcom_push(key='sample_data', value=data)
    
    return data


def process_data(**context):
    """Process data from upstream task"""
    ti = context['task_instance']
    sample_data = ti.xcom_pull(task_ids='generate_sample_data', key='sample_data')
    
    if not sample_data:
        raise ValueError("No data received from upstream task")
    
    logger.info(f"Processing data: {sample_data}")
    
    # Simulate processing
    processed = {
        'input_records': sample_data['records_processed'],
        'output_records': sample_data['records_processed'] * 2,
        'processing_time': '1.5s',
        'status': 'completed'
    }
    
    logger.info(f"Processing complete: {processed}")
    
    return processed


with DAG(
    dag_id='openlineage_demo',
    default_args=default_args,
    description='Demonstrates OpenLineage integration with MWAA',
    schedule=None,  # Manual trigger only
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['demo', 'openlineage', 'lineage'],
) as dag:

    # Task 1: Verify OpenLineage configuration
    verify_config = PythonOperator(
        task_id='verify_openlineage_config',
        python_callable=verify_openlineage_config,
        doc_md="""
        ### Verify OpenLineage Configuration
        
        Checks that OpenLineage native provider is configured:
        - Reads openlineage.transport from Airflow config
        - Reads openlineage.namespace from Airflow config
        - Verifies OpenLineage listener is registered
        
        Uses native provider (no environment variables needed).
        """
    )

    # Task 2: Test Marquez connectivity
    test_connectivity = PythonOperator(
        task_id='test_marquez_connectivity',
        python_callable=test_marquez_connectivity,
        doc_md="""
        ### Test Marquez Connectivity
        
        Tests connection to the Marquez server:
        - Fetches list of namespaces
        - Tests lineage endpoint
        - Validates API responses
        """
    )

    # Task 3: Print environment info
    print_env = BashOperator(
        task_id='print_environment_info',
        bash_command="""
        echo "==================================="
        echo "Environment Information"
        echo "==================================="
        echo "Hostname: $(hostname)"
        echo "Date: $(date)"
        echo "Python: $(python --version)"
        echo "==================================="
        """,
        doc_md="Prints basic environment information"
    )

    # Task 4: Generate sample data
    generate_data = PythonOperator(
        task_id='generate_sample_data',
        python_callable=generate_sample_data,
        doc_md="""
        ### Generate Sample Data
        
        Creates sample data to demonstrate lineage tracking.
        This simulates a data source.
        """
    )

    # Task 5: Process data
    process = PythonOperator(
        task_id='process_data',
        python_callable=process_data,
        doc_md="""
        ### Process Data
        
        Processes data from the upstream task.
        This simulates a data transformation.
        """
    )

    # Task 6: Success notification
    success = BashOperator(
        task_id='success_notification',
        bash_command="""
        echo "=========================================="
        echo "✅ OpenLineage Demo DAG Completed!"
        echo "=========================================="
        echo ""
        echo "Check Marquez UI to see the lineage graph:"
        echo "  - Navigate to your namespace"
        echo "  - Find job: openlineage_demo"
        echo "  - View the lineage visualization"
        echo ""
        echo "=========================================="
        """,
        doc_md="Prints success message with instructions"
    )

    # Define task dependencies
    verify_config >> test_connectivity >> print_env
    print_env >> generate_data >> process >> success
