"""
Poll a cross-region Step Functions execution for completion.

Returns status so the orchestrator can loop (wait → poll) until done.
"""
import json
import os
import boto3


def handler(event, context):
    """
    Check execution status.

    Input:
      - execution_arn: ARN of the running execution
      - target_region: region where the SM lives
      - reason: passthrough

    Output:
      - status: 'running', 'success', or 'failed'
      - execution_arn: echo back
      - detail: status detail
    """
    execution_arn = event['execution_arn']
    target_region = event.get('target_region',
                              os.environ.get('TARGET_REGION', ''))
    reason = event.get('reason', '')

    sfn = boto3.client('stepfunctions', region_name=target_region)

    resp = sfn.describe_execution(executionArn=execution_arn)
    state = resp['status']  # RUNNING, SUCCEEDED, FAILED, TIMED_OUT, ABORTED

    print(f"Restore execution {execution_arn}: {state}")

    if state == 'SUCCEEDED':
        status = 'success'
        detail = 'MetaDB restore completed successfully'
    elif state == 'RUNNING':
        status = 'running'
        detail = 'MetaDB restore still in progress'
    else:
        status = 'failed'
        error = resp.get('error', '')
        cause = resp.get('cause', '')
        detail = f"Restore {state}: {error} {cause}".strip()

    return {
        'status': status,
        'execution_arn': execution_arn,
        'target_region': target_region,
        'reason': reason,
        'detail': detail,
    }
