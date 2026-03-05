"""
Example: DR-Aware DAG with Minimal Boilerplate

This shows how to make any existing DAG DR-aware with just 3 lines of code:
1. Import the helper function
2. Create a BranchPythonOperator
3. Add it before your tasks

Your existing tasks remain unchanged!
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import BranchPythonOperator, PythonOperator
from airflow.providers.standard.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

# Import DR helper (just 1 line!)
from dr_utils import check_active_region

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def extract_data(**context):
    """Your existing extract task - no changes needed!"""
    print("Extracting data from source...")
    return "extracted_data"

def transform_data(**context):
    """Your existing transform task - no changes needed!"""
    print("Transforming data...")
    return "transformed_data"

def load_data(**context):
    """Your existing load task - no changes needed!"""
    print("Loading data to destination...")
    return "success"

with DAG(
    'example_dr_aware_dag',
    default_args=default_args,
    description='Example ETL DAG with DR awareness',
    schedule='0 */6 * * *',  # Every 6 hours
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['example', 'dr', 'etl'],
) as dag:
    
    # Add DR check (just 2 lines!)
    check_region = BranchPythonOperator(
        task_id='check_region',
        python_callable=check_active_region,
    )
    
    # Marker to start your tasks
    run_tasks = EmptyOperator(task_id='run_tasks')
    
    # Skip marker for standby region
    skip_all = EmptyOperator(task_id='skip_all')
    
    # Your existing tasks (no changes!)
    extract = PythonOperator(
        task_id='extract',
        python_callable=extract_data,
    )
    
    transform = PythonOperator(
        task_id='transform',
        python_callable=transform_data,
    )
    
    load = PythonOperator(
        task_id='load',
        python_callable=load_data,
    )
    
    # Alternative: Use bash operators
    cleanup = BashOperator(
        task_id='cleanup',
        bash_command='echo "Cleaning up temporary files..."',
    )
    
    # Define flow (just 1 line to add DR!)
    check_region >> [run_tasks, skip_all]
    
    # Your existing task flow (unchanged!)
    run_tasks >> extract >> transform >> load >> cleanup
