"""
MWAA Health Check Lambda

Monitors MWAA environment health and tracks consecutive failures.
Triggers failover when failure threshold is reached.
"""
import json
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal

mwaa = boto3.client('mwaa')
cloudwatch = boto3.client('cloudwatch')
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
lambda_client = boto3.client('lambda')


def get_environment_status(env_name, region):
    """Check MWAA environment status"""
    try:
        mwaa_regional = boto3.client('mwaa', region_name=region)
        response = mwaa_regional.get_environment(Name=env_name)
        return response['Environment']['Status']
    except Exception as e:
        print(f"Error getting environment status: {e}")
        return 'UNKNOWN'


def get_scheduler_heartbeat(env_name, region):
    """Check scheduler heartbeat metric"""
    try:
        cw_regional = boto3.client('cloudwatch', region_name=region)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=5)
        
        response = cw_regional.get_metric_statistics(
            Namespace='AmazonMWAA',
            MetricName='SchedulerHeartbeat',
            Dimensions=[{'Name': 'Environment', 'Value': env_name}],
            StartTime=start_time,
            EndTime=end_time,
            Period=60,
            Statistics=['Average']
        )
        
        return len(response['Datapoints']) > 0
    except Exception as e:
        print(f"Error getting scheduler heartbeat: {e}")
        return False


def update_health_state(table, region, is_healthy):
    """Update health state in DynamoDB"""
    timestamp = datetime.utcnow().isoformat()
    
    try:
        # Get current state
        response = table.get_item(Key={'state_id': f'HEALTH_{region}'})
        current_state = response.get('Item', {})
        
        consecutive_failures = int(current_state.get('consecutive_failures', 0))
        
        if is_healthy:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
        
        # Update state
        table.put_item(Item={
            'state_id': f'HEALTH_{region}',
            'is_healthy': is_healthy,
            'consecutive_failures': consecutive_failures,
            'last_check': timestamp,
            'last_failure_time': timestamp if not is_healthy else current_state.get('last_failure_time', ''),
        })
        
        return consecutive_failures
    except Exception as e:
        print(f"Error updating health state: {e}")
        return 0


def check_cooldown(table):
    """Check if we're in cooldown period after recent failover"""
    try:
        response = table.get_item(Key={'state_id': 'ACTIVE_REGION'})
        if 'Item' not in response:
            return False
        
        last_failover = response['Item'].get('last_failover_time')
        if not last_failover:
            return False
        
        cooldown_minutes = int(os.environ.get('COOLDOWN_MINUTES', '30'))
        last_failover_dt = datetime.fromisoformat(last_failover.replace('Z', '+00:00'))
        cooldown_end = last_failover_dt + timedelta(minutes=cooldown_minutes)
        
        in_cooldown = datetime.utcnow().replace(tzinfo=last_failover_dt.tzinfo) < cooldown_end
        
        if in_cooldown:
            remaining = (cooldown_end - datetime.utcnow().replace(tzinfo=last_failover_dt.tzinfo)).total_seconds() / 60
            print(f"In cooldown period. {remaining:.1f} minutes remaining.")
        
        return in_cooldown
    except Exception as e:
        print(f"Error checking cooldown: {e}")
        return False


def trigger_failover(secondary_region, reason):
    """Trigger failover Lambda function"""
    try:
        failover_function = os.environ['FAILOVER_FUNCTION_ARN']
        
        payload = {
            'target_region': secondary_region,
            'reason': reason,
            'triggered_by': 'automated_health_check'
        }
        
        response = lambda_client.invoke(
            FunctionName=failover_function,
            InvocationType='Event',  # Async
            Payload=json.dumps(payload)
        )
        
        print(f"Failover triggered: {response['StatusCode']}")
        return True
    except Exception as e:
        print(f"Error triggering failover: {e}")
        return False


def send_notification(topic_arn, subject, message):
    """Send SNS notification"""
    try:
        sns.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=message
        )
    except Exception as e:
        print(f"Error sending notification: {e}")


def lambda_handler(event, context):
    """
    Health check Lambda handler
    
    Environment variables:
    - PRIMARY_ENV_NAME: Primary MWAA environment name
    - PRIMARY_REGION: Primary region
    - SECONDARY_REGION: Secondary region
    - STATE_TABLE_NAME: DynamoDB state table name
    - FAILURE_THRESHOLD: Number of consecutive failures before failover (default: 3)
    - COOLDOWN_MINUTES: Cooldown period after failover (default: 30)
    - NOTIFICATION_TOPIC_ARN: SNS topic for notifications
    - FAILOVER_FUNCTION_ARN: Failover Lambda function ARN
    - REQUIRE_SCHEDULER_HEARTBEAT: Make heartbeat check mandatory (default: False)
    - CHECK_ENVIRONMENT_STATUS: Check environment status (default: True)
    """
    
    primary_env = os.environ['PRIMARY_ENV_NAME']
    primary_region = os.environ['PRIMARY_REGION']
    secondary_region = os.environ['SECONDARY_REGION']
    table_name = os.environ['STATE_TABLE_NAME']
    failure_threshold = int(os.environ.get('FAILURE_THRESHOLD', '3'))
    notification_topic = os.environ.get('NOTIFICATION_TOPIC_ARN')
    require_heartbeat = os.environ.get('REQUIRE_SCHEDULER_HEARTBEAT', 'False').lower() == 'true'
    check_env_status = os.environ.get('CHECK_ENVIRONMENT_STATUS', 'True').lower() == 'true'
    
    table = dynamodb.Table(table_name)
    
    print(f"Checking health of {primary_env} in {primary_region}")
    print(f"Configuration: require_heartbeat={require_heartbeat}, check_env_status={check_env_status}")
    
    # Check if we're in cooldown period
    if check_cooldown(table):
        return {
            'statusCode': 200,
            'body': json.dumps('In cooldown period, skipping health check')
        }
    
    # Check current active region
    try:
        response = table.get_item(Key={'state_id': 'ACTIVE_REGION'})
        active_region = response['Item']['active_region']
        
        # Only check health of active region
        if active_region != primary_region:
            print(f"Primary region is not active (active: {active_region}), skipping check")
            return {
                'statusCode': 200,
                'body': json.dumps('Primary region is not active')
            }
    except Exception as e:
        print(f"Error getting active region: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }
    
    # Perform health checks
    env_status = get_environment_status(primary_env, primary_region) if check_env_status else 'AVAILABLE'
    has_heartbeat = get_scheduler_heartbeat(primary_env, primary_region)
    
    # Determine overall health based on configuration
    is_healthy = True
    failure_reasons = []
    
    if check_env_status and env_status != 'AVAILABLE':
        is_healthy = False
        failure_reasons.append(f"Environment status is {env_status} (expected AVAILABLE)")
    
    if require_heartbeat and not has_heartbeat:
        is_healthy = False
        failure_reasons.append("Scheduler heartbeat missing (required)")
    elif not has_heartbeat:
        print("WARNING: Scheduler heartbeat missing (optional check, not failing)")
    
    print(f"Health check results:")
    print(f"  Environment status: {env_status}")
    print(f"  Scheduler heartbeat: {has_heartbeat}")
    print(f"  Overall health: {'HEALTHY' if is_healthy else 'UNHEALTHY'}")
    if failure_reasons:
        print(f"  Failure reasons: {', '.join(failure_reasons)}")
    
    # Update health state
    consecutive_failures = update_health_state(table, primary_region, is_healthy)
    
    print(f"Consecutive failures: {consecutive_failures}/{failure_threshold}")
    
    # Check if failover threshold reached
    if consecutive_failures >= failure_threshold:
        print(f"Failure threshold reached! Triggering failover to {secondary_region}")
        
        reason = f"Automated failover: {consecutive_failures} consecutive health check failures. Reasons: {', '.join(failure_reasons)}"
        
        # Send notification
        if notification_topic:
            send_notification(
                notification_topic,
                f"MWAA Automated Failover Triggered",
                f"""
Automated failover has been triggered for MWAA environment.

Primary Environment: {primary_env}
Primary Region: {primary_region}
Secondary Region: {secondary_region}

Reason: {reason}

Environment Status: {env_status}
Scheduler Heartbeat: {has_heartbeat}
Consecutive Failures: {consecutive_failures}

Failure Details:
{chr(10).join('- ' + r for r in failure_reasons)}

Failover is now in progress. You will receive another notification when complete.
                """
            )
        
        # Trigger failover
        success = trigger_failover(secondary_region, reason)
        
        if success:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'action': 'failover_triggered',
                    'consecutive_failures': consecutive_failures,
                    'target_region': secondary_region,
                    'failure_reasons': failure_reasons
                })
            }
        else:
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to trigger failover')
            }
    
    # Send warning notification if approaching threshold
    if consecutive_failures > 0 and notification_topic:
        send_notification(
            notification_topic,
            f"MWAA Health Check Warning",
            f"""
MWAA environment health check failed.

Primary Environment: {primary_env}
Primary Region: {primary_region}

Environment Status: {env_status}
Scheduler Heartbeat: {has_heartbeat}

Consecutive Failures: {consecutive_failures}/{failure_threshold}

Failure Details:
{chr(10).join('- ' + r for r in failure_reasons) if failure_reasons else '- No specific failures (environment may be idle)'}

Automated failover will trigger if {failure_threshold - consecutive_failures} more consecutive failures occur.
            """
        )
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'is_healthy': is_healthy,
            'consecutive_failures': consecutive_failures,
            'env_status': env_status,
            'has_heartbeat': has_heartbeat,
            'failure_reasons': failure_reasons
        })
    }
