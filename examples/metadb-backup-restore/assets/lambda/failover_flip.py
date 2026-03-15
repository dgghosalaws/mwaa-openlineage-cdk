"""
Failover Flip Lambda

Executes the "flip" portion of a failover:
1. Pauses DAGs in the source (old active) region
2. Unpauses DAGs in the target (new active) region
3. Updates DynamoDB active_region state

CLI tokens expire after 60 seconds, so we refresh before each call.
"""
import json
import os
import time
import base64
from datetime import datetime
import boto3
import urllib3

http = urllib3.PoolManager()

TOKEN_REFRESH_SECONDS = 50  # refresh before the 60s expiry


class TokenManager:
    """Manages MWAA CLI tokens with automatic refresh."""

    def __init__(self, env_name, region):
        self.env_name = env_name
        self.region = region
        self.mwaa = boto3.client('mwaa', region_name=region)
        self.token = None
        self.webserver = None
        self.obtained_at = 0

    def get(self):
        """Return a valid (token, webserver) pair, refreshing if needed."""
        now = time.time()
        if self.token is None or (now - self.obtained_at) >= TOKEN_REFRESH_SECONDS:
            resp = self.mwaa.create_cli_token(Name=self.env_name)
            self.token = resp['CliToken']
            self.webserver = resp['WebServerHostname']
            self.obtained_at = time.time()
        return self.token, self.webserver


def run_cli(token_mgr, cmd):
    """Run an Airflow CLI command with a fresh token."""
    token, webserver = token_mgr.get()
    try:
        resp = http.request(
            'POST',
            f'https://{webserver}/aws_mwaa/cli',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'text/plain',
            },
            body=cmd,
        )
        result = json.loads(resp.data.decode('utf-8'))
        stdout = base64.b64decode(result.get('stdout', '')).decode('utf-8')
        stderr = base64.b64decode(result.get('stderr', '')).decode('utf-8')
        return stdout, stderr
    except Exception as e:
        print(f"CLI error ({cmd}): {e}")
        return '', str(e)


def get_dag_ids(token_mgr):
    """Get list of DAG IDs, excluding internal/DR DAGs."""
    stdout, _ = run_cli(token_mgr, 'dags list -o json')
    dag_ids = []
    try:
        dags = json.loads(stdout)
        for d in dags:
            dag_id = d.get('dag_id', '')
            if dag_id and not dag_id.startswith('dr_'):
                dag_ids.append(dag_id)
    except (json.JSONDecodeError, TypeError):
        # Fallback: parse table output
        for line in stdout.strip().split('\n')[2:]:
            if line and not line.startswith('='):
                parts = line.split()
                if parts:
                    dag_id = parts[0]
                    if not dag_id.startswith('dr_'):
                        dag_ids.append(dag_id)
    return dag_ids


def control_dags(env_name, region, pause):
    """Pause or unpause all DAGs in an environment."""
    action = 'pause' if pause else 'unpause'
    print(f"{'Pausing' if pause else 'Unpausing'} DAGs in {env_name} ({region})...")

    token_mgr = TokenManager(env_name, region)

    dag_ids = get_dag_ids(token_mgr)
    if not dag_ids:
        print("No DAGs found")
        return 0

    print(f"Found {len(dag_ids)} DAGs")
    success = 0
    for dag_id in dag_ids:
        stdout, stderr = run_cli(token_mgr, f'dags {action} {dag_id}')
        if 'error' not in (stdout + stderr).lower():
            success += 1
        else:
            print(f"  Failed to {action} {dag_id}: {stderr}")

    print(f"{'Paused' if pause else 'Unpaused'} {success}/{len(dag_ids)} DAGs")
    return success


def update_dynamodb(table_name, target_region, reason):
    """Update DynamoDB with new active region."""
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    timestamp = datetime.utcnow().isoformat() + 'Z'

    try:
        resp = table.get_item(Key={'state_id': 'ACTIVE_REGION'})
        current = resp.get('Item', {})
        failover_count = int(current.get('failover_count', 0))
        version = int(current.get('version', 0))

        table.put_item(Item={
            'state_id': 'ACTIVE_REGION',
            'active_region': target_region,
            'last_updated': timestamp,
            'failover_count': failover_count + 1,
            'last_failover_time': timestamp,
            'failover_reason': reason,
            'version': version + 1,
        })
        print(f"DynamoDB updated: active_region = {target_region}")
        return True
    except Exception as e:
        print(f"DynamoDB update failed: {e}")
        return False


def handler(event, context):
    """
    Flip active region: pause source DAGs, unpause target DAGs, update DynamoDB.

    Input (from Step Functions):
      - target_env_name: MWAA env to make active
      - target_region: region of target env
      - source_env_name: MWAA env to deactivate
      - source_region: region of source env
      - reason: failover reason string

    Environment variables (fallbacks):
      - PRIMARY_ENV_NAME, SECONDARY_ENV_NAME
      - PRIMARY_REGION, SECONDARY_REGION
      - STATE_TABLE_NAME
    """
    target_env = event.get('target_env_name', os.environ.get('TARGET_ENV_NAME', ''))
    target_region = event.get('target_region', os.environ.get('TARGET_REGION', ''))
    source_env = event.get('source_env_name', os.environ.get('SOURCE_ENV_NAME', ''))
    source_region = event.get('source_region', os.environ.get('SOURCE_REGION', ''))
    reason = event.get('reason', 'Automated failover with metadb restore')
    table_name = os.environ.get('STATE_TABLE_NAME', '')

    # If target/source not explicit, derive from primary/secondary config
    if not target_env or not source_env:
        primary_env = os.environ.get('PRIMARY_ENV_NAME', '')
        secondary_env = os.environ.get('SECONDARY_ENV_NAME', '')
        primary_region = os.environ.get('PRIMARY_REGION', '')
        secondary_region = os.environ.get('SECONDARY_REGION', '')
        # Default: fail over TO secondary
        target_env = target_env or secondary_env
        target_region = target_region or secondary_region
        source_env = source_env or primary_env
        source_region = source_region or primary_region

    print(f"Failover flip: {source_env} ({source_region}) → {target_env} ({target_region})")
    start = time.time()

    results = {}

    # Step 1: Update DynamoDB
    if table_name:
        results['dynamodb_updated'] = update_dynamodb(table_name, target_region, reason)
    else:
        print("No STATE_TABLE_NAME configured, skipping DynamoDB update")
        results['dynamodb_updated'] = None

    # Step 2: Pause source DAGs
    results['source_paused'] = control_dags(source_env, source_region, pause=True)

    # Step 3: Unpause target DAGs
    results['target_unpaused'] = control_dags(target_env, target_region, pause=False)

    duration = time.time() - start
    results['duration_seconds'] = round(duration, 1)

    print(f"Failover flip complete in {duration:.1f}s")

    return {
        'status': 'success',
        'target_env_name': target_env,
        'target_region': target_region,
        'source_env_name': source_env,
        'source_region': source_region,
        'reason': reason,
        **results,
    }
