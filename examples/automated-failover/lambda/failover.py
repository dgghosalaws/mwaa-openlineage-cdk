"""
MWAA Automated Failover Lambda

Executes failover to secondary region:
1. Updates DynamoDB active region
2. Pauses DAGs in old active region
3. Unpauses DAGs in new active region
4. Sends notification
"""
import json
import boto3
import os
from datetime import datetime
import base64

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')


def get_airflow_access(env_name, region):
    """Get Airflow CLI token and webserver URL"""
    try:
        mwaa = boto3.client('mwaa', region_name=region)
        
        token_response = mwaa.create_cli_token(Name=env_name)
        token = token_response['CliToken']
        
        env_response = mwaa.get_environment(Name=env_name)
        webserver = env_response['Environment']['WebserverUrl']
        
        return token, webserver
    except Exception as e:
        print(f"Error getting Airflow access for {env_name} in {region}: {e}")
        return None, None


def get_dag_list(token, webserver):
    """Get list of all DAGs"""
    import urllib3
    http = urllib3.PoolManager()
    
    try:
        response = http.request(
            'POST',
            f'https://{webserver}/aws_mwaa/cli/',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'text/plain'
            },
            body='dags list'
        )
        
        result = json.loads(response.data.decode('utf-8'))
        stdout = base64.b64decode(result['stdout']).decode('utf-8')
        
        # Parse DAG IDs (skip header, exclude DR DAGs)
        lines = stdout.strip().split('\n')
        dag_ids = []
        for line in lines[2:]:  # Skip header
            if line and not line.startswith('='):
                dag_id = line.split()[0]
                if not dag_id.startswith('dr_'):
                    dag_ids.append(dag_id)
        
        return dag_ids
    except Exception as e:
        print(f"Error getting DAG list: {e}")
        return []


def control_dag(token, webserver, dag_id, pause):
    """Pause or unpause a DAG"""
    import urllib3
    http = urllib3.PoolManager()
    
    try:
        cmd = f'dags {"pause" if pause else "unpause"} {dag_id}'
        
        response = http.request(
            'POST',
            f'https://{webserver}/aws_mwaa/cli/',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'text/plain'
            },
            body=cmd
        )
        
        return response.status == 200
    except Exception as e:
        print(f"Error controlling DAG {dag_id}: {e}")
        return False


def control_dags(env_name, region, pause):
    """Pause or unpause all DAGs in an environment"""
    action = "Pausing" if pause else "Unpausing"
    print(f"{action} DAGs in {env_name} ({region})...")
    
    token, webserver = get_airflow_access(env_name, region)
    if not token or not webserver:
        print(f"Failed to get Airflow access")
        return 0
    
    dag_ids = get_dag_list(token, webserver)
    if not dag_ids:
        print(f"No DAGs found")
        return 0
    
    success_count = 0
    for dag_id in dag_ids:
        if control_dag(token, webserver, dag_id, pause):
            success_count += 1
    
    print(f"{action} {success_count}/{len(dag_ids)} DAGs")
    return success_count


def update_dynamodb_state(table, target_region, reason):
    """Update DynamoDB with new active region"""
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    try:
        # Get current state
        response = table.get_item(Key={'state_id': 'ACTIVE_REGION'})
        current_state = response.get('Item', {})
        failover_count = int(current_state.get('failover_count', 0))
        
        # Update state
        table.put_item(Item={
            'state_id': 'ACTIVE_REGION',
            'active_region': target_region,
            'last_updated': timestamp,
            'failover_count': failover_count + 1,
            'last_failover_time': timestamp,
            'failover_reason': reason,
            'version': int(current_state.get('version', 0)) + 1
        })
        
        print(f"DynamoDB updated: active_region = {target_region}")
        return True
    except Exception as e:
        print(f"Error updating DynamoDB: {e}")
        return False


def send_notification(topic_arn, subject, message):
    """Send SNS notification"""
    try:
        sns.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=message
        )
        print(f"Notification sent")
    except Exception as e:
        print(f"Error sending notification: {e}")


def lambda_handler(event, context):
    """
    Failover Lambda handler
    
    Event payload:
    - target_region: Region to failover to
    - reason: Reason for failover
    - triggered_by: Who/what triggered the failover
    
    Environment variables:
    - PRIMARY_ENV_NAME: Primary MWAA environment name
    - SECONDARY_ENV_NAME: Secondary MWAA environment name
    - PRIMARY_REGION: Primary region
    - SECONDARY_REGION: Secondary region
    - STATE_TABLE_NAME: DynamoDB state table name
    - NOTIFICATION_TOPIC_ARN: SNS topic for notifications
    """
    
    target_region = event['target_region']
    reason = event.get('reason', 'Manual failover')
    triggered_by = event.get('triggered_by', 'unknown')
    
    primary_env = os.environ['PRIMARY_ENV_NAME']
    secondary_env = os.environ['SECONDARY_ENV_NAME']
    primary_region = os.environ['PRIMARY_REGION']
    secondary_region = os.environ['SECONDARY_REGION']
    table_name = os.environ['STATE_TABLE_NAME']
    notification_topic = os.environ.get('NOTIFICATION_TOPIC_ARN')
    
    table = dynamodb.Table(table_name)
    
    print(f"Starting failover to {target_region}")
    print(f"Reason: {reason}")
    print(f"Triggered by: {triggered_by}")
    
    # Determine source and target environments
    if target_region == primary_region:
        target_env = primary_env
        source_env = secondary_env
        source_region = secondary_region
    else:
        target_env = secondary_env
        source_env = primary_env
        source_region = primary_region
    
    start_time = datetime.utcnow()
    
    try:
        # Step 1: Update DynamoDB
        print("\nStep 1: Updating DynamoDB...")
        if not update_dynamodb_state(table, target_region, reason):
            raise Exception("Failed to update DynamoDB")
        
        # Step 2: Pause DAGs in source region
        print(f"\nStep 2: Pausing DAGs in source region ({source_region})...")
        paused_count = control_dags(source_env, source_region, pause=True)
        
        # Step 3: Unpause DAGs in target region
        print(f"\nStep 3: Unpausing DAGs in target region ({target_region})...")
        unpaused_count = control_dags(target_env, target_region, pause=False)
        
        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        print(f"\nFailover complete in {duration:.1f} seconds")
        
        # Send success notification
        if notification_topic:
            send_notification(
                notification_topic,
                "MWAA Failover Complete",
                f"""
Failover has completed successfully.

Target Region: {target_region}
Source Region: {source_region}
Reason: {reason}
Triggered By: {triggered_by}

Actions Taken:
- DynamoDB updated: active_region = {target_region}
- DAGs paused in {source_region}: {paused_count}
- DAGs unpaused in {target_region}: {unpaused_count}

Duration: {duration:.1f} seconds

Next Steps:
1. Verify DAGs are running in {target_region}
2. Monitor for any issues
3. Check Airflow UI in both regions
                """
            )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'target_region': target_region,
                'source_region': source_region,
                'paused_count': paused_count,
                'unpaused_count': unpaused_count,
                'duration_seconds': duration
            })
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"Failover failed: {error_msg}")
        
        # Send failure notification
        if notification_topic:
            send_notification(
                notification_topic,
                "MWAA Failover Failed",
                f"""
Failover has FAILED.

Target Region: {target_region}
Source Region: {source_region}
Reason: {reason}
Triggered By: {triggered_by}

Error: {error_msg}

Action Required:
Manual intervention may be needed. Please check:
1. DynamoDB state table
2. MWAA environment status in both regions
3. DAG pause state in both regions
                """
            )
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': error_msg
            })
        }
