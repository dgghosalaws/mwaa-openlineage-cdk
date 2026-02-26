"""
DR Test DAG - Airflow 3.0 Compatible

This DAG helps verify that the DR plugin is working correctly:
- In ACTIVE region: DAG runs normally
- In STANDBY region: DAG is paused by dr_state_plugin

Deploy this DAG to both regions to test DR functionality.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.bash import BashOperator
import socket

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def print_region_info(**context):
    """Print information about current region and DR status"""
    import os
    import boto3
    
    # Get region from environment or boto3
    region = os.environ.get('AWS_DEFAULT_REGION', 'unknown')
    if region == 'unknown':
        try:
            session = boto3.session.Session()
            region = session.region_name
        except:
            region = 'unknown'
    
    # Get hostname
    hostname = socket.gethostname()
    
    print(f"=" * 60)
    print(f"DR Test DAG Execution")
    print(f"=" * 60)
    print(f"Region: {region}")
    print(f"Hostname: {hostname}")
    print(f"Execution Date: {context['logical_date']}")
    print(f"DAG Run ID: {context['run_id']}")
    print(f"=" * 60)
    print(f"\nThis DAG is running in: {region}")
    print(f"If you see this in STANDBY region, DR plugin is NOT working!")
    print(f"If you DON'T see this in STANDBY region, DR plugin IS working!")
    print(f"=" * 60)

# Airflow 3.0: Use 'schedule' instead of 'schedule_interval'
with DAG(
    'dr_test_dag',
    default_args=default_args,
    description='Test DAG to verify DR plugin functionality',
    schedule='*/10 * * * *',  # Every 10 minutes
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['dr', 'test', 'monitoring'],
) as dag:
    
    # Task 1: Print region information
    print_info = PythonOperator(
        task_id='print_region_info',
        python_callable=print_region_info,
    )
    
    # Task 2: Simple bash command
    check_region = BashOperator(
        task_id='check_region',
        bash_command='echo "Region: $AWS_DEFAULT_REGION" && echo "Hostname: $(hostname)"',
    )
    
    # Task 3: Verify execution
    verify_execution = BashOperator(
        task_id='verify_execution',
        bash_command='''
        echo "=========================================="
        echo "DR Test DAG - Execution Verified"
        echo "=========================================="
        echo "If you see this message:"
        echo "  - In ACTIVE region: ✓ CORRECT - DAG is running"
        echo "  - In STANDBY region: ✗ ERROR - DAG should be paused"
        echo "=========================================="
        ''',
    )
    
    print_info >> check_region >> verify_execution
