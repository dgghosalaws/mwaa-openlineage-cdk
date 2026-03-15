"""
MWAA Health Check Lambda

Monitors the primary MWAA environment. When consecutive failures reach
the threshold, starts the Failover Orchestrator Step Function (which
restores metadb then flips the active region).
"""
import json
import os
from datetime import datetime, timedelta
import boto3

mwaa_client = boto3.client('mwaa')
cloudwatch_client = boto3.client('cloudwatch')
dynamodb = boto3.resource('dynamodb')
sns_client = boto3.client('sns')
sfn_client = boto3.client('stepfunctions')


def get_environment_status(env_name, region):
    """Check MWAA environment status."""
    try:
        client = boto3.client('mwaa', region_name=region)
        resp = client.get_environment(Name=env_name)
        return resp['Environment']['Status']
    except Exception as e:
        print(f"Error getting env status: {e}")
        return 'UNKNOWN'


def get_scheduler_heartbeat(env_name, region):
    """Check scheduler heartbeat metric (last 5 minutes)."""
    try:
        cw = boto3.client('cloudwatch', region_name=region)
        end = datetime.utcnow()
        start = end - timedelta(minutes=5)
        resp = cw.get_metric_statistics(
            Namespace='AmazonMWAA',
            MetricName='SchedulerHeartbeat',
            Dimensions=[{'Name': 'Environment', 'Value': env_name}],
            StartTime=start, EndTime=end,
            Period=60, Statistics=['Average'],
        )
        return len(resp['Datapoints']) > 0
    except Exception as e:
        print(f"Error getting heartbeat: {e}")
        return False


def update_health_state(table, region, is_healthy):
    """Update health state in DynamoDB, return consecutive failure count."""
    timestamp = datetime.utcnow().isoformat()
    try:
        resp = table.get_item(Key={'state_id': f'HEALTH_{region}'})
        current = resp.get('Item', {})
        failures = int(current.get('consecutive_failures', 0))
        failures = 0 if is_healthy else failures + 1

        table.put_item(Item={
            'state_id': f'HEALTH_{region}',
            'is_healthy': is_healthy,
            'consecutive_failures': failures,
            'last_check': timestamp,
            'last_failure_time': timestamp if not is_healthy else current.get('last_failure_time', ''),
        })
        return failures
    except Exception as e:
        print(f"Error updating health state: {e}")
        return 0


def check_cooldown(table, cooldown_minutes):
    """Return True if we're in cooldown after a recent failover."""
    try:
        resp = table.get_item(Key={'state_id': 'ACTIVE_REGION'})
        item = resp.get('Item')
        if not item:
            return False
        last = item.get('last_failover_time')
        if not last:
            return False
        last_dt = datetime.fromisoformat(last.replace('Z', '+00:00'))
        cooldown_end = last_dt + timedelta(minutes=cooldown_minutes)
        now = datetime.utcnow().replace(tzinfo=last_dt.tzinfo)
        if now < cooldown_end:
            remaining = (cooldown_end - now).total_seconds() / 60
            print(f"In cooldown period. {remaining:.1f} min remaining.")
            return True
        return False
    except Exception as e:
        print(f"Error checking cooldown: {e}")
        return False


def start_failover(state_machine_arn, reason):
    """Start the Failover Orchestrator Step Function."""
    try:
        resp = sfn_client.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps({'reason': reason}),
        )
        arn = resp['executionArn']
        print(f"Failover orchestrator started: {arn}")
        return True
    except Exception as e:
        print(f"Error starting failover: {e}")
        return False


def send_notification(topic_arn, subject, message):
    try:
        sns_client.publish(TopicArn=topic_arn, Subject=subject, Message=message)
    except Exception as e:
        print(f"Error sending notification: {e}")


def handler(event, context):
    """
    Health check handler.

    Env vars:
      PRIMARY_ENV_NAME, PRIMARY_REGION, SECONDARY_REGION,
      STATE_TABLE_NAME, FAILURE_THRESHOLD, COOLDOWN_MINUTES,
      NOTIFICATION_TOPIC_ARN, FAILOVER_STATE_MACHINE_ARN
    """
    primary_env = os.environ['PRIMARY_ENV_NAME']
    primary_region = os.environ['PRIMARY_REGION']
    secondary_region = os.environ['SECONDARY_REGION']
    table_name = os.environ['STATE_TABLE_NAME']
    threshold = int(os.environ.get('FAILURE_THRESHOLD', '3'))
    cooldown = int(os.environ.get('COOLDOWN_MINUTES', '30'))
    topic_arn = os.environ.get('NOTIFICATION_TOPIC_ARN', '')
    sm_arn = os.environ.get('FAILOVER_STATE_MACHINE_ARN', '')

    table = dynamodb.Table(table_name)

    print(f"Health check: {primary_env} in {primary_region}")

    # Cooldown check
    if check_cooldown(table, cooldown):
        return {'statusCode': 200, 'body': 'In cooldown period'}

    # Only check if primary is the active region
    try:
        resp = table.get_item(Key={'state_id': 'ACTIVE_REGION'})
        active = resp.get('Item', {}).get('active_region', primary_region)
        if active != primary_region:
            print(f"Primary not active (active={active}), skipping")
            return {'statusCode': 200, 'body': 'Primary not active'}
    except Exception as e:
        print(f"Error reading active region: {e}")

    # Health checks
    env_status = get_environment_status(primary_env, primary_region)
    has_heartbeat = get_scheduler_heartbeat(primary_env, primary_region)

    is_healthy = True
    reasons = []
    if env_status != 'AVAILABLE':
        is_healthy = False
        reasons.append(f"Environment status: {env_status}")
    if not has_heartbeat:
        # Log warning but don't fail on heartbeat alone
        print("WARNING: Scheduler heartbeat missing")

    print(f"Status: {env_status}, Heartbeat: {has_heartbeat}, Healthy: {is_healthy}")

    failures = update_health_state(table, primary_region, is_healthy)
    print(f"Consecutive failures: {failures}/{threshold}")

    if failures >= threshold:
        reason = f"Automated: {failures} consecutive failures. {', '.join(reasons)}"
        print(f"Threshold reached — starting failover orchestrator")

        if topic_arn:
            send_notification(topic_arn,
                "MWAA Failover Triggered",
                f"Primary: {primary_env} ({primary_region})\n"
                f"Failing over to: {secondary_region}\n"
                f"Reason: {reason}\n\n"
                f"The failover orchestrator will restore metadb then flip regions.")

        if sm_arn:
            start_failover(sm_arn, reason)

        return {'statusCode': 200, 'body': json.dumps({
            'action': 'failover_triggered', 'failures': failures, 'reasons': reasons,
        })}

    # Warning notification if approaching threshold
    if failures > 0 and topic_arn:
        send_notification(topic_arn,
            "MWAA Health Check Warning",
            f"Primary: {primary_env} ({primary_region})\n"
            f"Status: {env_status}, Heartbeat: {has_heartbeat}\n"
            f"Failures: {failures}/{threshold}\n"
            f"Failover triggers after {threshold - failures} more failures.")

    return {'statusCode': 200, 'body': json.dumps({
        'is_healthy': is_healthy, 'failures': failures,
        'env_status': env_status, 'has_heartbeat': has_heartbeat,
    })}
