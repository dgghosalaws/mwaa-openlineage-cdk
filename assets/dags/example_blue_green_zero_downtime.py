"""
Zero-Downtime Blue-Green DAG

This DAG uses AWS Systems Manager Parameter Store to determine if it should run.
Switching between Blue and Green is instant - just update the parameter.
"""
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from datetime import datetime, timedelta
import os
import boto3
from botocore.exceptions import ClientError


# Get environment color from MWAA config
ENV_COLOR = os.environ.get('AIRFLOW__CUSTOM__ENVIRONMENT_COLOR', 'unknown')
PARAMETER_NAME = '/mwaa/blue-green/active-environment'


def get_active_environment():
    """Get the active environment from Parameter Store"""
    try:
        ssm = boto3.client('ssm')
        response = ssm.get_parameter(Name=PARAMETER_NAME)
        return response['Parameter']['Value']
    except ClientError as e:
        if e.response['Error']['Code'] == 'ParameterNotFound':
            print(f"Parameter {PARAMETER_NAME} not found, defaulting to 'blue'")
            return 'blue'
        raise


def check_if_active(**context):
    """Check if this environment is active"""
    active_env = get_active_environment()
    
    print(f"{'='*60}")
    print(f"Environment Check")
    print(f"{'='*60}")
    print(f"Current Environment: {ENV_COLOR}")
    print(f"Active Environment: {active_env}")
    print(f"{'='*60}")
    
    if ENV_COLOR == active_env:
        print(f"✓ This environment ({ENV_COLOR}) is ACTIVE - proceeding with execution")
        return 'print_environment_info'
    else:
        print(f"⊘ This environment ({ENV_COLOR}) is STANDBY - skipping execution")
        return 'skip_execution'


def print_environment_info(**context):
    """Print information about the current environment"""
    active_env = get_active_environment()
    
    print(f"{'='*60}")
    print(f"Zero-Downtime Blue-Green Environment")
    print(f"{'='*60}")
    print(f"Environment Color: {ENV_COLOR}")
    print(f"Active Environment: {active_env}")
    print(f"Status: {'ACTIVE ✓' if ENV_COLOR == active_env else 'STANDBY ⊘'}")
    print(f"Execution Date: {context['ds']}")
    print(f"{'='*60}")


def process_data(**context):
    """Simulate data processing"""
    exec_date = context['ds']
    active_env = get_active_environment()
    
    print(f"Processing data for {exec_date} in {ENV_COLOR} environment")
    print(f"Active environment: {active_env}")
    
    # Your actual data processing logic here
    return f"Processed data for {exec_date} in {ENV_COLOR}"


def verify_completion(**context):
    """Verify the processing completed successfully"""
    print(f"✓ Data processing completed successfully in {ENV_COLOR} environment")
    return "success"


# Default DAG arguments
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2025, 1, 1),
}


# Create DAG
with DAG(
    'example_blue_green_zero_downtime',
    default_args=default_args,
    description='Zero-downtime blue-green DAG using Parameter Store',
    schedule='@daily',
    catchup=False,
    tags=['example', 'blue-green', 'zero-downtime'],
) as dag:
    
    # Task 1: Check if this environment is active
    check_active = BranchPythonOperator(
        task_id='check_if_active',
        python_callable=check_if_active,
    )
    
    # Task 2: Skip execution (standby environment)
    skip = EmptyOperator(
        task_id='skip_execution',
    )
    
    # Task 3: Print environment information (active environment)
    print_env = PythonOperator(
        task_id='print_environment_info',
        python_callable=print_environment_info,
    )
    
    # Task 4: Process data
    process = PythonOperator(
        task_id='process_data',
        python_callable=process_data,
    )
    
    # Task 5: Verify completion
    verify = PythonOperator(
        task_id='verify_completion',
        python_callable=verify_completion,
    )
    
    # Set task dependencies
    check_active >> [skip, print_env]
    print_env >> process >> verify


# Add DAG documentation
dag.doc_md = """
# Zero-Downtime Blue-Green DAG

This DAG implements true zero-downtime blue-green switching using AWS Systems Manager Parameter Store.

## How It Works

1. **Parameter Store Flag**: `/mwaa/blue-green/active-environment` contains "blue" or "green"
2. **Runtime Check**: Each DAG run checks the parameter to see if it should execute
3. **Instant Switch**: Update the parameter to switch environments immediately
4. **No Downtime**: Both environments stay AVAILABLE, no MWAA configuration changes

## Switching Environments

To switch from Blue to Green:
```bash
aws ssm put-parameter \
  --name /mwaa/blue-green/active-environment \
  --value green \
  --overwrite
```

To switch from Green to Blue:
```bash
aws ssm put-parameter \
  --name /mwaa/blue-green/active-environment \
  --value blue \
  --overwrite
```

## Benefits

- **Instant switching**: Takes effect on next DAG run (seconds, not minutes)
- **Zero downtime**: No MWAA configuration updates needed
- **Safe**: Running tasks complete normally
- **Reversible**: Switch back instantly if issues occur

## Monitoring

Check which environment is active:
```bash
aws ssm get-parameter --name /mwaa/blue-green/active-environment --query 'Parameter.Value' --output text
```

View DAG logs to see environment checks and execution decisions.
"""
