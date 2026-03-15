"""
Trigger the glue_mwaa_restore DAG on the target MWAA environment.

Uses MWAA CLI token to trigger the DAG with the backup path config.
Returns the dag_run_id for monitoring.
"""
import json
import os
import base64
import boto3
import urllib3


http = urllib3.PoolManager()


def handler(event, context):
    """
    Trigger restore DAG.
    
    Input:
      - backup_path: S3 path to backup
      - target_env_name: MWAA environment to restore into
      - target_region: region of target MWAA
      - restore_mode: 'append' or 'clean' (default: append)
      - tables: list of tables to restore (default: all)
      
    Output:
      - dag_run_id: ID of the triggered DAG run
      - target_env_name: echo back for downstream steps
      - target_region: echo back
    """
    backup_path = event['backup_path']
    target_env = event.get('target_env_name', os.environ.get('TARGET_ENV_NAME'))
    target_region = event.get('target_region', os.environ.get('TARGET_REGION'))
    restore_mode = event.get('restore_mode', 'append')
    tables = event.get('tables', None)  # None = all tables
    
    mwaa = boto3.client('mwaa', region_name=target_region)
    
    # Get CLI token
    token_resp = mwaa.create_cli_token(Name=target_env)
    cli_token = token_resp['CliToken']
    webserver = token_resp['WebServerHostname']
    
    # Build DAG config
    dag_conf = {
        'backup_path': backup_path,
        'restore_mode': restore_mode,
    }
    if tables:
        dag_conf['tables'] = tables
    
    conf_json = json.dumps(dag_conf)
    
    # Trigger DAG via CLI
    cmd = f"dags trigger glue_mwaa_restore --conf '{conf_json}'"
    print(f"Triggering: {cmd}")
    
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
    
    print(f"stdout: {stdout}")
    if stderr:
        print(f"stderr: {stderr}")

    # Extract dag_run_id from output
    # AF3 output: "Created <DagRun ...dag_run_id=manual__2026-03-15T...>"
    dag_run_id = None
    if 'dag_run_id=' in stdout:
        dag_run_id = stdout.split('dag_run_id=')[1].split(',')[0].split('>')[0].strip()
    elif 'manual__' in stdout:
        for part in stdout.split():
            if 'manual__' in part:
                dag_run_id = part.strip(',').strip('>')
                break
    
    if not dag_run_id:
        # Fallback: use a generated ID based on timestamp
        from datetime import datetime
        dag_run_id = f"manual__{datetime.utcnow().isoformat()}"
    
    print(f"DAG run ID: {dag_run_id}")
    
    return {
        'dag_run_id': dag_run_id,
        'target_env_name': target_env,
        'target_region': target_region,
        'backup_path': backup_path,
        'restore_mode': restore_mode,
    }
