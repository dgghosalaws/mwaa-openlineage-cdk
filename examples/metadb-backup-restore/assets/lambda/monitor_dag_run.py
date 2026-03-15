"""
Monitor restore progress by checking the Glue job status directly.

The restore DAG starts a Glue job and returns immediately. This Lambda
monitors the Glue job run to determine if the restore is complete.

Since DAGs are paused before restore starts, there's no risk of picking
up a stale run — the latest run is always the one we triggered.

Used in a Step Functions Wait loop.
"""
import os
import boto3


def handler(event, context):
    """
    Check restore status by monitoring the Glue job.

    Input:
      - target_env_name: MWAA environment name (used to derive Glue job name)
      - target_region: region
      - dag_run_id: echo through for state tracking
      - backup_path: echo through
      - glue_run_id: if known from previous iteration, use it directly

    Output:
      - status: 'running', 'success', or 'failed'
      - detail: status detail string
    """
    target_env = event.get('target_env_name', os.environ.get('TARGET_ENV_NAME'))
    target_region = event.get('target_region', os.environ.get('TARGET_REGION'))
    dag_run_id = event.get('dag_run_id', '')
    backup_path = event.get('backup_path', '')
    prev_glue_run_id = event.get('glue_run_id', '')

    # Glue job name follows convention: {env_name}_metadb_restore
    glue_job_name = f"{target_env}_metadb_restore"

    glue = boto3.client('glue', region_name=target_region)

    # If we already know the run ID, check it directly
    if prev_glue_run_id:
        try:
            resp = glue.get_job_run(JobName=glue_job_name, RunId=prev_glue_run_id)
            run = resp['JobRun']
        except Exception as e:
            print(f"Error checking known run {prev_glue_run_id}: {e}")
            run = None
    else:
        # Get the latest run — DAGs are paused so no competing runs
        try:
            resp = glue.get_job_runs(JobName=glue_job_name, MaxResults=1)
            runs = resp.get('JobRuns', [])
            run = runs[0] if runs else None
        except Exception as e:
            print(f"Error getting Glue runs: {e}")
            run = None

    if not run:
        print(f"No Glue runs found for {glue_job_name}, DAG may still be starting")
        return {
            'status': 'running',
            'dag_run_id': dag_run_id,
            'glue_run_id': '',
            'target_env_name': target_env,
            'target_region': target_region,
            'backup_path': backup_path,
            'detail': 'Waiting for Glue job to start',
        }

    glue_run_id = run['Id']
    state = run['JobRunState']
    error = run.get('ErrorMessage', '')

    print(f"Glue job {glue_job_name} run {glue_run_id}: {state}")

    if state == 'SUCCEEDED':
        status = 'success'
        detail = f"Glue job {glue_job_name} succeeded (run {glue_run_id})"
    elif state in ('FAILED', 'STOPPED', 'ERROR', 'TIMEOUT'):
        status = 'failed'
        detail = f"Glue job {glue_job_name} {state}: {error}"
    else:
        status = 'running'
        detail = f"Glue job {glue_job_name} {state} (run {glue_run_id})"

    return {
        'status': status,
        'dag_run_id': dag_run_id,
        'glue_run_id': glue_run_id,
        'target_env_name': target_env,
        'target_region': target_region,
        'backup_path': backup_path,
        'detail': detail,
    }
