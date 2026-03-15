"""
Validate the MetaDB restore by checking key tables have data.

Uses MWAA CLI to run Airflow commands that query the database indirectly
(e.g. list DAGs, list DAG runs) to confirm data was restored.
"""
import json
import os
import base64
import boto3
import urllib3


http = urllib3.PoolManager()


def run_cli_command(cli_token, webserver, cmd):
    """Run an Airflow CLI command and return stdout."""
    response = http.request(
        'POST',
        f'https://{webserver}/aws_mwaa/cli',
        headers={
            'Authorization': f'Bearer {cli_token}',
            'Content-Type': 'text/plain',
        },
        body=cmd,
    )
    result = json.loads(response.data.decode('utf-8'))
    stdout = base64.b64decode(result.get('stdout', '')).decode('utf-8')
    stderr = base64.b64decode(result.get('stderr', '')).decode('utf-8')
    return stdout, stderr


def handler(event, context):
    """
    Validate restore.
    
    Input:
      - target_env_name: MWAA environment
      - target_region: region
      - backup_path: original backup path (for reference)
      
    Output:
      - valid: True/False
      - checks: dict of check results
    """
    target_env = event.get('target_env_name', os.environ.get('TARGET_ENV_NAME'))
    target_region = event.get('target_region', os.environ.get('TARGET_REGION'))
    
    mwaa = boto3.client('mwaa', region_name=target_region)
    
    token_resp = mwaa.create_cli_token(Name=target_env)
    cli_token = token_resp['CliToken']
    webserver = token_resp['WebServerHostname']
    
    checks = {}
    
    # Check 1: DAGs exist
    stdout, _ = run_cli_command(cli_token, webserver, 'dags list')
    dag_lines = [l for l in stdout.strip().split('\n') if l and not l.startswith('=') and 'dag_id' not in l.lower()]
    dag_count = len(dag_lines) - 1 if dag_lines else 0  # subtract header
    checks['dags_exist'] = dag_count > 0
    checks['dag_count'] = max(dag_count, 0)
    print(f"Check 1 - DAGs exist: {checks['dags_exist']} ({checks['dag_count']} DAGs)")
    
    # Check 2: Variables accessible
    stdout, _ = run_cli_command(cli_token, webserver, 'variables list')
    checks['variables_accessible'] = 'error' not in stdout.lower()
    print(f"Check 2 - Variables accessible: {checks['variables_accessible']}")
    
    # Check 3: Pools exist (slot_pool)
    stdout, _ = run_cli_command(cli_token, webserver, 'pools list')
    checks['pools_exist'] = 'default_pool' in stdout.lower()
    print(f"Check 3 - Pools exist: {checks['pools_exist']}")
    
    # Check 4: MWAA environment is healthy
    env_resp = mwaa.get_environment(Name=target_env)
    env_status = env_resp['Environment']['Status']
    checks['env_healthy'] = env_status == 'AVAILABLE'
    checks['env_status'] = env_status
    print(f"Check 4 - Environment healthy: {checks['env_healthy']} ({env_status})")
    
    # Overall validation
    valid = all([
        checks['dags_exist'],
        checks['variables_accessible'],
        checks['pools_exist'],
        checks['env_healthy'],
    ])
    
    print(f"\nOverall validation: {'PASSED' if valid else 'FAILED'}")
    
    return {
        'valid': valid,
        'checks': checks,
        'target_env_name': target_env,
        'target_region': target_region,
        'backup_path': event.get('backup_path', ''),
    }
