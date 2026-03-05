"""
DR Test DAG - Simple Active Region Check

This DAG demonstrates the simplest DR-aware pattern:
1. Check if current region is ACTIVE (via DynamoDB)
2. If ACTIVE: Execute the work task
3. If STANDBY: Skip the work task

This is the recommended pattern for all production DAGs in a DR setup.
Configuration is read from Airflow config (set in MWAA airflow_configuration_options).
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import BranchPythonOperator
from airflow.providers.standard.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
import os

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def check_active_region(**context):
    """
    Check DynamoDB to determine if current region is active.
    Returns: 'run_work' if active, 'skip_work' if standby
    """
    import boto3
    from airflow.configuration import conf
    
    # Get current region
    try:
        session = boto3.session.Session()
        current_region = session.region_name
    except Exception as e:
        print(f"Error getting region: {e}")
        current_region = os.environ.get('AWS_DEFAULT_REGION', 'unknown')
    
    # Read DR configuration from Airflow config
    # These are set in MWAA airflow_configuration_options
    state_table = conf.get('dr', 'state_table', fallback='mwaa-openlineage-dr-state-dev')
    table_region = conf.get('dr', 'table_region', fallback='us-east-2')
    
    print(f"=" * 60)
    print(f"DR Active Region Check")
    print(f"=" * 60)
    print(f"Current Region: {current_region}")
    print(f"State Table: {state_table} (in {table_region})")
    print(f"Config Source: Airflow configuration")
    
    try:
        # Query DynamoDB for active region
        dynamodb = boto3.client('dynamodb', region_name=table_region)
        response = dynamodb.get_item(
            TableName=state_table,
            Key={'state_id': {'S': 'ACTIVE_REGION'}}
        )
        
        if 'Item' in response:
            active_region = response['Item']['active_region']['S']
            print(f"Active Region: {active_region}")
            print(f"=" * 60)
            
            if current_region == active_region:
                print(f"✓ ACTIVE - Will execute work")
                return 'run_work'
            else:
                print(f"✗ STANDBY - Will skip work")
                return 'skip_work'
        else:
            print(f"⚠ No active region found - Defaulting to skip")
            print(f"=" * 60)
            return 'skip_work'
            
    except Exception as e:
        print(f"✗ ERROR checking DynamoDB: {e}")
        print(f"  Defaulting to skip for safety")
        print(f"=" * 60)
        return 'skip_work'

with DAG(
    'dr_test_dag',
    default_args=default_args,
    description='Simple DR test: check active region, then run or skip work',
    schedule='*/10 * * * *',  # Every 10 minutes
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['dr', 'test', 'simple'],
) as dag:
    
    # Step 1: Check if this region is active
    check_region = BranchPythonOperator(
        task_id='check_region',
        python_callable=check_active_region,
    )
    
    # Step 2a: Run work (ACTIVE region)
    run_work = BashOperator(
        task_id='run_work',
        bash_command='''
        echo "=========================================="
        echo "✓ ACTIVE Region - Executing Work"
        echo "=========================================="
        echo "Region: $AWS_DEFAULT_REGION"
        echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        echo ""
        echo "This is where your actual work happens:"
        echo "  - Data processing"
        echo "  - ETL jobs"
        echo "  - API calls"
        echo "  - etc."
        echo "=========================================="
        ''',
    )
    
    # Step 2b: Skip work (STANDBY region)
    skip_work = EmptyOperator(
        task_id='skip_work',
    )
    
    # Define flow
    check_region >> [run_work, skip_work]
