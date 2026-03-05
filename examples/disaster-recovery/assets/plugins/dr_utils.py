"""
DR Utilities for Airflow DAGs

This module provides helper functions to make any DAG DR-aware with minimal code.
Simply import and use the check_active_region function in your DAG.

Example usage:
    from dr_utils import check_active_region
    from airflow.providers.standard.operators.python import BranchPythonOperator
    
    check_region = BranchPythonOperator(
        task_id='check_region',
        python_callable=check_active_region,
    )
    
    # Your existing tasks
    task1 = ...
    task2 = ...
    
    # Add DR check before your tasks
    check_region >> [task1, skip_all]
"""
import os
import boto3
from airflow.configuration import conf


def check_active_region(**context):
    """
    Check if current region is the active DR region.
    
    Returns:
        str: 'run_tasks' if active region, 'skip_all' if standby
        
    This function reads configuration from Airflow config:
    - dr.state_table: DynamoDB table name
    - dr.table_region: Region where DynamoDB table is located
    
    Usage in DAG:
        check_region = BranchPythonOperator(
            task_id='check_region',
            python_callable=check_active_region,
        )
    """
    # Get current region
    try:
        session = boto3.session.Session()
        current_region = session.region_name
    except Exception as e:
        print(f"Error getting region: {e}")
        current_region = os.environ.get('AWS_DEFAULT_REGION', 'unknown')
    
    # Read DR configuration from Airflow config
    state_table = conf.get('dr', 'state_table', fallback='mwaa-openlineage-dr-state-dev')
    table_region = conf.get('dr', 'table_region', fallback='us-east-2')
    
    print(f"=" * 60)
    print(f"DR Active Region Check")
    print(f"=" * 60)
    print(f"Current Region: {current_region}")
    print(f"State Table: {state_table} (in {table_region})")
    
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
                print(f"✓ ACTIVE - Will execute tasks")
                return 'run_tasks'
            else:
                print(f"✗ STANDBY - Will skip tasks")
                return 'skip_all'
        else:
            print(f"⚠ No active region found - Defaulting to skip")
            print(f"=" * 60)
            return 'skip_all'
            
    except Exception as e:
        print(f"✗ ERROR checking DynamoDB: {e}")
        print(f"  Defaulting to skip for safety")
        print(f"=" * 60)
        return 'skip_all'


def is_active_region():
    """
    Simple boolean check if current region is active.
    
    Returns:
        bool: True if active region, False if standby
        
    Usage in task:
        def my_task(**context):
            if not is_active_region():
                print("Skipping - standby region")
                return
            # Do actual work
    """
    try:
        session = boto3.session.Session()
        current_region = session.region_name
    except:
        current_region = os.environ.get('AWS_DEFAULT_REGION', 'unknown')
    
    state_table = conf.get('dr', 'state_table', fallback='mwaa-openlineage-dr-state-dev')
    table_region = conf.get('dr', 'table_region', fallback='us-east-2')
    
    try:
        dynamodb = boto3.client('dynamodb', region_name=table_region)
        response = dynamodb.get_item(
            TableName=state_table,
            Key={'state_id': {'S': 'ACTIVE_REGION'}}
        )
        
        if 'Item' in response:
            active_region = response['Item']['active_region']['S']
            return current_region == active_region
        return False
    except:
        return False
