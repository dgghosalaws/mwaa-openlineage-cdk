# MWAA MetaDB Backup/Restore with Failover Orchestration

Backup and restore MWAA metadata database (PostgreSQL) across regions using AWS Glue,
with automated failover and fallback orchestration via Step Functions.

## Overview

This example provides two layers of functionality:

1. **Base Infrastructure** — Per-region backup/restore using Glue jobs, Step Functions, and S3
2. **Failover/Fallback Orchestrators** — Cross-region automated failover (primary → secondary) and fallback (secondary → primary), each chaining: pause DAGs → MetaDB restore → activate target → notify

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Primary Region (us-east-2)                   │
│                                                                     │
│  ┌──────────────┐   ┌──────────────────┐   ┌────────────────────┐  │
│  │ MWAA Primary │   │ Export Glue Job   │   │ S3 Backup Bucket   │  │
│  │              │──▶│ (mwaa_metadb_     │──▶│ (exports/<env>/    │  │
│  │              │   │  export.py)       │   │  YYYY/MM/DD/)      │  │
│  └──────────────┘   └──────────────────┘   └────────┬───────────┘  │
│                                                      │              │
│  ┌──────────────────────────────────────┐            │              │
│  │ Failover Orchestrator (Step Fn)      │            │              │
│  │  primary → secondary                 │            │              │
│  │  1. Pause DAGs in primary     ───────┼────────────┼──────┐      │
│  │  2. Start restore in secondary       │            │      │      │
│  │  3. Poll until complete              │            │      │      │
│  │  4. Activate secondary (DDB+unpause) │            │      │      │
│  │  5. Send SNS notification            │            │      │      │
│  └──────────────────────────────────────┘            │      │      │
│                                                      │      │      │
│  ┌──────────────────────────────────────┐            │      │      │
│  │ Fallback Orchestrator (Step Fn)      │            │      │      │
│  │  secondary → primary                 │            │      │      │
│  │  1. Pause DAGs in secondary   ───────┼──────┐     │      │      │
│  │  2. Start restore in primary         │      │     │      │      │
│  │  3. Poll until complete              │      │     │      │      │
│  │  4. Activate primary (DDB+unpause)   │      │     │      │      │
│  │  5. Send SNS notification            │      │     │      │      │
│  └──────────────────────────────────────┘      │     │      │      │
│                                                │     │      │      │
│  ┌──────────────────────────────────────┐      │     │      │      │
│  │ Health Check Lambda (EventBridge)    │      │     │      │      │
│  │  → monitors primary MWAA status      │      │     │      │      │
│  │  → triggers failover on failure      │      │     │      │      │
│  └──────────────────────────────────────┘      │     │      │      │
│                                                │     │      │      │
│  ┌──────────────────────────────────────┐      │     │      │      │
│  │ DynamoDB: mwaa-failover-state        │      │     │      │      │
│  │  → tracks active region              │      │     │      │      │
│  │  → failover count + cooldown         │      │     │      │      │
│  └──────────────────────────────────────┘      │     │      │      │
└────────────────────────────────────────────────┼─────┼──────┼──────┘
                                                 │     │      │
                                                 ▼     ▼      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Secondary Region (us-east-1)                    │
│                                                                      │
│  ┌──────────────┐   ┌──────────────────┐   ┌─────────────────────┐  │
│  │ MWAA         │   │ Restore Glue Job │   │ Auto-Restore SM     │  │
│  │ Secondary    │◀──│ (mwaa_metadb_    │◀──│ (Step Functions)    │  │
│  │              │   │  restore.py)     │   │  FindBackup→Glue→   │  │
│  └──────────────┘   └──────────────────┘   │  Monitor→Validate   │  │
│                                             └─────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## Important: Planned Failover Only

> **This failover orchestrator is designed for planned failover simulations and
> MWAA-level failures — not full regional outages.** All orchestration components
> (Step Functions, Lambdas, DynamoDB, EventBridge) run in the primary region.
> If that region goes down entirely, none of these will execute.
>
> For true cross-region DR where the primary is completely unavailable, trigger
> the restore manually from the secondary region or use a multi-region pattern
> (e.g., Route 53 health checks with a failover Lambda in the secondary region).
>
> This solution is well-suited for:
> - **Planned failover drills** — validate your DR process end-to-end
> - **MWAA environment failures** — scheduler crashes, environment stuck in UPDATING
> - **Maintenance windows** — gracefully move workloads to the secondary region
> - **Partial service degradation** — MWAA is unhealthy but the region's control plane is up

## Project Structure

```
metadb-backup-restore/
├── app.py                          # CDK app entry point
├── cdk.json                        # CDK configuration
├── deploy.sh                       # Deployment helper script
├── requirements.txt                # Python dependencies
├── stacks/
│   ├── metadb_backup_restore_stack.py   # Base backup/restore infrastructure
│   └── failover_orchestrator_stack.py   # Failover + fallback orchestrators
└── assets/
    ├── dags/
    │   ├── glue_mwaa_export.py     # Airflow DAG: export metadb to S3
    │   └── glue_mwaa_restore.py    # Airflow DAG: restore metadb from S3
    ├── glue/
    │   ├── mwaa_metadb_export.py   # Glue script: JDBC export to CSV
    │   └── mwaa_metadb_restore.py  # Glue script: CSV restore via pg8000
    └── lambda/
        ├── find_latest_backup.py        # Finds most recent backup in S3
        ├── trigger_restore_dag.py       # Triggers restore DAG via MWAA CLI
        ├── monitor_dag_run.py           # Monitors Glue job status directly
        ├── validate_restore.py          # Validates restore completed
        ├── start_cross_region_restore.py # Starts restore SM in another region
        ├── poll_cross_region_restore.py  # Polls cross-region SM execution
        ├── failover_flip.py             # Pauses/unpauses DAGs, updates DynamoDB
        └── health_check.py              # Monitors MWAA health, triggers failover
```

## Prerequisites

- Two MWAA environments already deployed (e.g., via the `disaster-recovery/` example)
- CDK bootstrapped in both regions (`npx cdk bootstrap aws://<ACCOUNT>/<REGION>`)
- AWS CLI configured with appropriate permissions
- Node.js and Python 3.11+

## Deployment

### Step 1: Deploy Base Stacks (Both Regions)

```bash
cd examples/metadb-backup-restore
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Deploy backup/restore infrastructure to both regions
npx cdk deploy MetaDBBackupRestorePrimary MetaDBBackupRestoreSecondary \
  -c account=<ACCOUNT_ID> --require-approval never
```

This creates per region:
- S3 bucket: `mwaa-metadb-backups-<account>-<region>`
- Glue IAM role: `mwaa-metadb-glue-<region>`
- Glue jobs for export and restore
- Auto-restore Step Function: `mwaa-metadb-auto-restore-<region>`
- Lambda functions for orchestration

### Step 2: Upload Assets to S3

CDK creates infrastructure but does not upload Glue scripts or DAG files:

```bash
ACCOUNT=<ACCOUNT_ID>

# Primary region (us-east-2)
aws s3 cp assets/glue/mwaa_metadb_export.py  s3://mwaa-metadb-backups-${ACCOUNT}-us-east-2/scripts/ --region us-east-2
aws s3 cp assets/glue/mwaa_metadb_restore.py s3://mwaa-metadb-backups-${ACCOUNT}-us-east-2/scripts/ --region us-east-2
aws s3 cp assets/dags/glue_mwaa_export.py    s3://<PRIMARY_MWAA_DAG_BUCKET>/dags/ --region us-east-2
aws s3 cp assets/dags/glue_mwaa_restore.py   s3://<PRIMARY_MWAA_DAG_BUCKET>/dags/ --region us-east-2

# Secondary region (us-east-1)
aws s3 cp assets/glue/mwaa_metadb_export.py  s3://mwaa-metadb-backups-${ACCOUNT}-us-east-1/scripts/ --region us-east-1
aws s3 cp assets/glue/mwaa_metadb_restore.py s3://mwaa-metadb-backups-${ACCOUNT}-us-east-1/scripts/ --region us-east-1
aws s3 cp assets/dags/glue_mwaa_export.py    s3://<SECONDARY_MWAA_DAG_BUCKET>/dags/ --region us-east-1
aws s3 cp assets/dags/glue_mwaa_restore.py   s3://<SECONDARY_MWAA_DAG_BUCKET>/dags/ --region us-east-1
```

Find the MWAA DAG bucket name in the MWAA console under Environment details → DAGs folder.

### Step 3: Configure MWAA Airflow Configuration Options

Set these in the MWAA console (or your MWAA CDK stack's `airflow_configuration_options`):

| Key | Value | Description |
|-----|-------|-------------|
| `metadb_export.aws_region` | `us-east-2` (your region) | Region where Glue/S3 resources live |
| `metadb_export.glue_role_name` | `mwaa-metadb-glue-<region>` | Glue IAM role created by this stack |
| `metadb_export.export_s3_bucket` | `mwaa-metadb-backups-<account>-<region>` | S3 bucket for backups |
| `metadb_export.max_age_days` | `30` | Max age of records to export |

Set these on every MWAA environment that runs export or restore DAGs.
After saving, MWAA updates the environment (~5 minutes).

### Step 4: Add IAM Permissions to MWAA Execution Roles

Add this inline policy (`MetaDBGlueAccess`) to each MWAA execution role:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "glue:CreateConnection", "glue:DeleteConnection",
                "glue:GetConnection", "glue:UpdateConnection",
                "glue:CreateJob", "glue:UpdateJob", "glue:GetJob",
                "glue:GetJobRun", "glue:GetJobRuns", "glue:StartJobRun"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups",
                "ec2:DescribeVpcEndpoints", "ec2:DescribeRouteTables",
                "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",
                "ec2:DescribeNetworkInterfaces"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": ["airflow:GetEnvironment"],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": ["iam:PassRole"],
            "Resource": "arn:aws:iam::<ACCOUNT_ID>:role/mwaa-metadb-glue-*",
            "Condition": {
                "StringEquals": { "iam:PassedToService": "glue.amazonaws.com" }
            }
        },
        {
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            "Resource": [
                "arn:aws:s3:::mwaa-metadb-backups-<ACCOUNT_ID>-*",
                "arn:aws:s3:::mwaa-metadb-backups-<ACCOUNT_ID>-*/*"
            ]
        }
    ]
}
```

### Step 5: Add Cross-Region S3 Access to Glue Roles

For cross-region restore, add `CrossRegionBackupAccess` to the Glue role in the target region:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["s3:GetObject*", "s3:GetBucket*", "s3:List*"],
            "Resource": [
                "arn:aws:s3:::mwaa-metadb-backups-<ACCOUNT_ID>-<SOURCE_REGION>",
                "arn:aws:s3:::mwaa-metadb-backups-<ACCOUNT_ID>-<SOURCE_REGION>/*"
            ]
        }
    ]
}
```

### Step 6: Run an Initial Export

Before restore or failover can work, at least one export must exist:

1. Go to the primary MWAA Airflow UI
2. Trigger the `glue_mwaa_export` DAG
3. Wait for the Glue job to complete (~3-5 minutes)
4. Verify backup exists: `aws s3 ls s3://mwaa-metadb-backups-<ACCOUNT>-<REGION>/exports/<ENV_NAME>/`

Recommended: schedule exports every 15-30 minutes for fresh backups.

### Step 7: Deploy Failover Orchestrator (Optional)

```bash
npx cdk deploy FailoverOrchestrator \
  -c failover=true -c account=<ACCOUNT_ID> --require-approval never
```

This deploys to the primary region only:
- Failover Orchestrator Step Function (primary → secondary)
- Fallback Orchestrator Step Function (secondary → primary)
- Health Check Lambda + EventBridge rule (1-minute schedule, disabled by default)
- Failover Flip Lambda (pause/unpause DAGs, update DynamoDB)
- Cross-region restore bridge Lambdas (start + poll)
- DynamoDB state table
- SNS notification topic

### Step 8: Seed DynamoDB State

After deploying the orchestrator, seed the initial active region:

```bash
aws dynamodb put-item \
  --table-name mwaa-failover-state-<REGION> \
  --item '{
    "state_id": {"S": "ACTIVE_REGION"},
    "active_region": {"S": "<PRIMARY_REGION>"},
    "version": {"N": "0"},
    "failover_count": {"N": "0"}
  }' \
  --region <REGION>
```

### Step 9: Enable Health Check (When Ready)

The EventBridge health check rule deploys disabled by default. Enable it when
you're ready for automated health monitoring:

```bash
aws events enable-rule \
  --name mwaa-failover-health-check-<REGION> \
  --region <REGION>
```

To disable again:

```bash
aws events disable-rule \
  --name mwaa-failover-health-check-<REGION> \
  --region <REGION>
```

---

## Usage

### Manual Export

Trigger the export DAG from the Airflow UI or CLI:

```bash
# Via Airflow UI: trigger glue_mwaa_export DAG
# Via CLI (from MWAA console):
aws mwaa create-cli-token --name <ENV_NAME> --region <REGION>
# Then POST to the webserver: dags trigger glue_mwaa_export
```

Exports land in: `s3://mwaa-metadb-backups-<ACCOUNT>-<REGION>/exports/<ENV_NAME>/YYYY/MM/DD/`

### Manual Restore (Same Region)

Start the auto-restore Step Function from the AWS console:

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:<REGION>:<ACCOUNT>:stateMachine:mwaa-metadb-auto-restore-<REGION> \
  --input '{}' \
  --region <REGION>
```

The Step Function will: find the latest backup → trigger the restore DAG → monitor the Glue job → validate.

### Manual Failover (Primary → Secondary)

Start the failover orchestrator from the AWS console or CLI:

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:<PRIMARY_REGION>:<ACCOUNT>:stateMachine:mwaa-failover-orchestrator-<PRIMARY_REGION> \
  --input '{"reason": "Planned failover drill"}' \
  --region <PRIMARY_REGION>
```

The orchestrator will:
1. Pause all DAGs in the primary region (excluding `glue_mwaa_*` and `dr_*` DAGs)
2. Start the auto-restore Step Function in the secondary region
3. Poll every 60 seconds until the restore completes
4. Activate the secondary region: update DynamoDB + unpause DAGs in secondary
5. Send an SNS notification

### Manual Fallback (Secondary → Primary)

After a failover, return traffic to the primary region:

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:<PRIMARY_REGION>:<ACCOUNT>:stateMachine:mwaa-fallback-orchestrator-<PRIMARY_REGION> \
  --input '{"reason": "Returning to primary after drill"}' \
  --region <PRIMARY_REGION>
```

The fallback orchestrator mirrors the failover flow in reverse:
1. Pause all DAGs in the secondary region
2. Start the auto-restore Step Function in the primary region (restores secondary's latest export into primary)
3. Poll until complete
4. Activate the primary region: update DynamoDB + unpause DAGs in primary
5. Send an SNS notification

> **Important:** For fallback to work, the secondary region must have at least one
> export. Run `glue_mwaa_export` in the secondary environment before attempting fallback.

---

## Failover Orchestrator — Deep Dive

### Why Cross-Region Lambdas?

Step Functions cannot natively start a state machine in another region. The
`start_cross_region_restore` Lambda bridges this gap by using a boto3 client
pointed at the target region to call `start_execution`. Similarly,
`poll_cross_region_restore` uses `describe_execution` against the remote region.

### CLI Token Refresh

MWAA CLI tokens expire after 60 seconds. The `failover_flip` Lambda uses a
`TokenManager` class that automatically refreshes the token before each CLI call
if more than 50 seconds have elapsed. This is critical when pausing/unpausing
many DAGs sequentially.

### DynamoDB State Table

The `mwaa-failover-state-<REGION>` table tracks:

| Field | Description |
|-------|-------------|
| `state_id` | Always `ACTIVE_REGION` (partition key) |
| `active_region` | Currently active region (e.g., `us-east-2`) |
| `failover_count` | Total number of failovers performed |
| `last_failover_time` | ISO timestamp of last failover |
| `failover_reason` | Reason string from the orchestrator input |
| `version` | Optimistic locking counter |

### Health Check Behavior

The health check Lambda (triggered by EventBridge every minute when enabled):

1. Calls `airflow:GetEnvironment` on the primary MWAA environment
2. If status is not `AVAILABLE`, increments a failure counter in DynamoDB
3. After `FAILURE_THRESHOLD` consecutive failures (default: 3), starts the failover orchestrator
4. Respects a `COOLDOWN_MINUTES` window (default: 30) to prevent repeated failovers
5. Publishes health status to SNS on state changes

The EventBridge rule deploys **disabled by default**. Enable it only after testing.

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `health_check_interval` | `rate(1 minute)` | EventBridge schedule expression |
| `failure_threshold` | `3` | Consecutive failures before triggering failover |
| `cooldown_minutes` | `30` | Minimum time between automated failovers |
| `notification_email` | (none) | Email for SNS subscription (optional) |

---

## How It Works

### Export Process

1. The `glue_mwaa_export` DAG runs in Airflow
2. It creates a Glue JDBC connection to the MWAA PostgreSQL metadb
3. The Glue job (`mwaa_metadb_export.py`) reads key tables via JDBC and writes CSV files to S3
4. Exports are partitioned by date: `exports/<env>/YYYY/MM/DD/`

### Restore Process

1. The auto-restore Step Function finds the latest backup in S3
2. It triggers the `glue_mwaa_restore` DAG via MWAA CLI
3. The DAG starts a Glue job (`mwaa_metadb_restore.py`) that:
   - Reads CSV files from S3
   - Connects to the target MWAA metadb via pg8000 (pure Python PostgreSQL driver)
   - Cleans float-formatted integers from Spark (e.g., `1.0` → `1`)
   - Restores data using `INSERT ... ON CONFLICT DO UPDATE` (upsert)
   - Writes a restore summary to the local region's backup bucket
4. The monitor Lambda checks the Glue job status directly (not the DAG status)
5. The validate Lambda confirms the restore completed

### Airflow Compatibility

- The restore DAG uses a **fire-and-forget** pattern: it starts the Glue job and returns immediately
- This avoids Celery executor timeouts (Airflow kills tasks that run too long)
- The DAG will show as "failed" in the Airflow UI — this is expected behavior
- Actual restore status is tracked by the monitor Lambda watching the Glue job

---

## Design Decisions

### Why `glue_mwaa_*` DAGs Are Excluded from Pause/Unpause

The `failover_flip` Lambda excludes DAGs matching `glue_mwaa_*` when pausing or
unpausing. These are the export and restore DAGs themselves — pausing them would
prevent the restore from running during failover.

### Why Latest Glue Run Is Safe

The monitor Lambda simply checks the latest Glue job run (no time-based filtering).
This is safe because DAGs are always paused before the restore starts, so there are
no competing Glue runs. The latest run is always the one triggered by the orchestrator.

---

## CDK Stacks Reference

| Stack | Region | Resources |
|-------|--------|-----------|
| `MetaDBBackupRestorePrimary` | Primary (us-east-2) | S3 bucket, Glue role, Glue jobs, auto-restore Step Function, Lambdas |
| `MetaDBBackupRestoreSecondary` | Secondary (us-east-1) | S3 bucket, Glue role, Glue jobs, auto-restore Step Function, Lambdas |
| `FailoverOrchestrator` | Primary (us-east-2) | Failover SM, Fallback SM, Health Check Lambda, EventBridge rule, DynamoDB table, SNS topic, Flip Lambda, Cross-region bridge Lambdas |

Deploy base stacks:
```bash
npx cdk deploy MetaDBBackupRestorePrimary MetaDBBackupRestoreSecondary \
  -c account=<ACCOUNT_ID> --require-approval never
```

Deploy orchestrator (optional):
```bash
npx cdk deploy FailoverOrchestrator \
  -c failover=true -c account=<ACCOUNT_ID> --require-approval never
```

---

## Troubleshooting

### No backups found

The auto-restore Step Function fails at the "FindLatestBackup" step.

- Verify exports exist: `aws s3 ls s3://mwaa-metadb-backups-<ACCOUNT>-<SOURCE_REGION>/exports/`
- Run `glue_mwaa_export` in the source environment first
- Check that the `source_env_name` and `source_region` are configured correctly in the stack

### Restore DAG shows "failed" in Airflow UI

This is expected. The restore DAG uses fire-and-forget: it starts the Glue job and
exits immediately. Airflow marks it as failed because the task doesn't wait for
completion. Check the actual Glue job status in the AWS Glue console.

### Health check triggers unexpected failover

- Disable the EventBridge rule: `aws events disable-rule --name mwaa-failover-health-check-<REGION>`
- Check the DynamoDB table for the `consecutive_failures` counter
- Increase `failure_threshold` or `cooldown_minutes` if needed
- Review CloudWatch logs for the health check Lambda

### Cross-region restore fails with AccessDenied

The Glue role in the target region needs `CrossRegionBackupAccess` policy to read
from the source region's S3 bucket. See [Step 5](#step-5-add-cross-region-s3-access-to-glue-roles).

### Fallback fails — no export in secondary

Fallback restores the secondary's latest export into the primary. If the secondary
has never run an export, there's nothing to restore. Run `glue_mwaa_export` in the
secondary environment before attempting fallback.

### Glue job fails with connection error

- Verify the MWAA environment is in `AVAILABLE` state
- Check that the Glue role has the correct VPC/subnet/security group permissions
- Ensure the MWAA Airflow configuration options are set (see [Step 3](#step-3-configure-mwaa-airflow-configuration-options))
- Check Glue job logs in CloudWatch: `/aws-glue/jobs/error`
