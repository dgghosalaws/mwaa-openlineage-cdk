"""
Start the MetaDB auto-restore state machine in a different region.

Step Functions can't natively start cross-region nested executions,
so this Lambda bridges the gap.
"""
import json
import os
import boto3


def handler(event, context):
    """
    Start the restore state machine in the target region.

    Input:
      - restore_state_machine_arn: ARN of the restore SM (in target region)
      - target_region: region where the SM lives
      - reason: passthrough

    Output:
      - execution_arn: ARN of the started execution
      - target_region: echo back
    """
    sm_arn = event.get('restore_state_machine_arn',
                       os.environ.get('RESTORE_STATE_MACHINE_ARN', ''))
    target_region = event.get('target_region',
                              os.environ.get('TARGET_REGION', ''))
    reason = event.get('reason', 'Automated failover')

    sfn = boto3.client('stepfunctions', region_name=target_region)

    resp = sfn.start_execution(
        stateMachineArn=sm_arn,
        input=json.dumps({'reason': reason}),
    )

    execution_arn = resp['executionArn']
    print(f"Started restore SM: {execution_arn}")

    return {
        'execution_arn': execution_arn,
        'target_region': target_region,
        'reason': reason,
    }
