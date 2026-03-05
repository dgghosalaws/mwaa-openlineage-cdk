"""
DR Test DAG - Airflow 3.0 Compatible with Branch Logic

This DAG demonstrates DR-aware execution:
- Checks DynamoDB to determine if current region is ACTIVE
- In ACTIVE region: Executes all tasks normally
- In STANDBY region: Skips execution tasks (only logs status)

This approach allows DAGs to run in both regions but only execute
meaningful work in the active region.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.standard.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
import socket
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
    Returns task_id to branch to: 'execute_tasks' or 'skip_execution'
    """
    import boto3
    
    # Get current region
    try:
        session = boto3.session.Session()
        current_region = session.region_name
    except Exception as e:
        print(f"Error getting region: {e}")
        current_region = os.environ.get('AWS_DEFAULT_REGION', 'unknown')
    
    # DynamoDB configuration
    state_table_name = os.environ.get('DR_STATE_TABLE', 'mwaa-openlineage-dr-state-dev')
    primary_region = 'us-east-2'  # Where DynamoDB table is located
    
    print(f"=" * 60)
    print(f"DR Region Check")
    print(f"=" * 60)
    print(f"Current Region: {current_region}")
    print(f"State Table: {state_table_name}")
    print(f"Table Region: {primary_region}")
    
    try:
        # Connect to DynamoDB in primary region
        dynamodb = boto3.client('dynamodb', region_name=primary_region)
        
        # Get active region from DynamoDB
        response = dynamodb.get_item(
            TableName=state_table_name,
            Key={'state_id': {'S': 'ACTIVE_REGION'}}
        )
        
        if 'Item' in response:
            active_region = response['Item']['active_region']['S']
            last_updated = response['Item'].get('last_updated', {}).get('S', 'unknown')
            failover_count = response['Item'].get('failover_count', {}).get('N', '0')
            
            print(f"Active Region: {active_region}")
            print(f"Last Updated: {last_updated}")
            print(f"Failover Count: {failover_count}")
            print(f"=" * 60)
            
            # Determine if we should execute
            if current_region == active_region:
                print(f"✓ ACTIVE: Current region matches active region")
                print(f"  → Branching to: execute_tasks")
                print(f"=" * 60)
                return 'execute_tasks'
            else:
                print(f"✗ STANDBY: Current region is standby")
                print(f"  → Branching to: skip_execution")
                print(f"=" * 60)
                return 'skip_execution'
        else:
            print(f"⚠ WARNING: No active region found in DynamoDB")
            print(f"  → Defaulting to: skip_execution")
            print(f"=" * 60)
            return 'skip_execution'
            
    except Exception as e:
        print(f"✗ ERROR: Failed to check DynamoDB: {e}")
        print(f"  → Defaulting to: skip_execution")
        print(f"=" * 60)
        return 'skip_execution'

def print_region_info(**context):
    """Print information about current region and DR status"""
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
    print(f"DR Test DAG - ACTIVE Region Execution")
    print(f"=" * 60)
    print(f"Region: {region}")
    print(f"Hostname: {hostname}")
    print(f"Execution Date: {context['logical_date']}")
    print(f"DAG Run ID: {context['run_id']}")
    print(f"=" * 60)
    print(f"\n✓ This region is ACTIVE - executing tasks normally")
    print(f"=" * 60)

def print_standby_info(**context):
    """Print information when in standby region"""
    import boto3
    
    # Get region from environment or boto3
    region = os.environ.get('AWS_DEFAULT_REGION', 'unknown')
    if region == 'unknown':
        try:
            session = boto3.session.Session()
            region = session.region_name
        except:
            region = 'unknown'
    
    print(f"=" * 60)
    print(f"DR Test DAG - STANDBY Region")
    print(f"=" * 60)
    print(f"Region: {region}")
    print(f"Execution Date: {context['logical_date']}")
    print(f"=" * 60)
    print(f"\n✗ This region is STANDBY - skipping task execution")
    print(f"  Tasks will not execute until this region becomes active")
    print(f"=" * 60)

# Airflow 3.0: Use 'schedule' instead of 'schedule_interval'
with DAG(
    'dr_test_dag',
    default_args=default_args,
    description='DR-aware test DAG with branch logic based on DynamoDB state',
    schedule='*/10 * * * *',  # Every 10 minutes
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['dr', 'test', 'monitoring', 'branch'],
) as dag:
    
    # Task 1: Check if current region is active
    check_region_branch = BranchPythonOperator(
        task_id='check_region_branch',
        python_callable=check_active_region,
    )
    
    # Branch 1: Execute tasks (ACTIVE region)
    execute_tasks = EmptyOperator(
        task_id='execute_tasks',
    )
    
    # Task 2a: Print active region info
    print_active_info = PythonOperator(
        task_id='print_active_info',
        python_callable=print_region_info,
    )
    
    # Task 3a: Execute work in active region
    execute_work = BashOperator(
        task_id='execute_work',
        bash_command='''
        echo "=========================================="
        echo "DR Test DAG - ACTIVE Region Execution"
        echo "=========================================="
        echo "Region: $AWS_DEFAULT_REGION"
        echo "Hostname: $(hostname)"
        echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        echo ""
        echo "✓ Executing tasks in ACTIVE region"
        echo "  This is where real work would happen"
        echo "=========================================="
        ''',
    )
    
    # Task 4a: Verify active execution
    verify_active = BashOperator(
        task_id='verify_active',
        bash_command='''
        echo "=========================================="
        echo "✓ ACTIVE Region Verification Complete"
        echo "=========================================="
        echo "All tasks executed successfully"
        echo "This region is processing workloads"
        echo "=========================================="
        ''',
    )
    
    # Branch 2: Skip execution (STANDBY region)
    skip_execution = PythonOperator(
        task_id='skip_execution',
        python_callable=print_standby_info,
    )
    
    # Task 2b: Log standby status
    log_standby = BashOperator(
        task_id='log_standby',
        bash_command='''
        echo "=========================================="
        echo "✗ STANDBY Region - No Execution"
        echo "=========================================="
        echo "Region: $AWS_DEFAULT_REGION"
        echo "Status: STANDBY"
        echo "Action: Skipping task execution"
        echo ""
        echo "Tasks will execute when this region becomes active"
        echo "=========================================="
        ''',
    )
    
    # Task 3b: End marker for standby
    end_standby = EmptyOperator(
        task_id='end_standby',
    )
    
    # Task: Join point (runs after either branch completes)
    join = EmptyOperator(
        task_id='join',
        trigger_rule='none_failed_min_one_success',  # Runs if at least one upstream succeeds
    )
    
    # Define task dependencies
    # Branch based on region check
    check_region_branch >> [execute_tasks, skip_execution]
    
    # Active region path
    execute_tasks >> print_active_info >> execute_work >> verify_active >> join
    
    # Standby region path
    skip_execution >> log_standby >> end_standby >> join
