# MWAA MetaDB Backup/Restore

Backup and restore MWAA metadata database (PostgreSQL) across regions using AWS Glue.

## Prerequisites

- Two MWAA environments already deployed (e.g. via the `disaster-recovery/` example)
- CDK bootstrapped in both regions
- AWS CLI configured

## What Gets Deployed

Per region:
- S3 bucket for backups (`mwaa-metadb-backups-<account>-<region>`)
- Glue IAM role (`mwaa-metadb-glue-<region>`)
- Glue jobs for export and restore
- Step Functions workflows for orchestration
- Lambda for Glue connection management

## Deploy

```bash
cd examples/metadb-backup-restore
./deploy.sh
```

Or with flags: `./deploy.sh --skip-cdk` (upload assets only) or `./deploy.sh --skip-upload` (CDK only).

## Required Changes to Existing MWAA Execution Roles

The DAGs run inside MWAA and need permissions to create Glue connections, manage Glue jobs,
read MWAA environment config, and access backup S3 buckets. Add this inline policy
(`MetaDBGlueAccess`) to each MWAA execution role:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "glue:CreateConnection",
                "glue:DeleteConnection",
                "glue:GetConnection",
                "glue:UpdateConnection",
                "glue:CreateJob",
                "glue:UpdateJob",
                "glue:GetJob",
                "glue:GetJobRun",
                "glue:GetJobRuns",
                "glue:StartJobRun"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeSubnets",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeVpcEndpoints",
                "ec2:DescribeRouteTables",
                "ec2:CreateNetworkInterface",
                "ec2:DeleteNetworkInterface",
                "ec2:DescribeNetworkInterfaces"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "airflow:GetEnvironment"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "iam:PassRole"
            ],
            "Resource": "arn:aws:iam::<ACCOUNT_ID>:role/mwaa-metadb-glue-*",
            "Condition": {
                "StringEquals": {
                    "iam:PassedToService": "glue.amazonaws.com"
                }
            }
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::mwaa-metadb-backups-<ACCOUNT_ID>-*",
                "arn:aws:s3:::mwaa-metadb-backups-<ACCOUNT_ID>-*/*"
            ]
        }
    ]
}
```

Note: the IAM action is `airflow:GetEnvironment` (not `mwaa:GetEnvironment`).

## Required MWAA Configuration Options (Manual Step)

These must be set manually in the MWAA console (or in your MWAA CDK stack's
`airflow_configuration_options`). The DAGs read these at import time via
`airflow.configuration.conf.get()`.

In the AWS Console: MWAA → Environments → Edit → Airflow configuration options, add:

| Key | Value | Description |
|-----|-------|-------------|
| `metadb_export.aws_region` | `us-east-1` (or your region) | Region where Glue and S3 resources live |
| `metadb_export.glue_role_name` | `mwaa-metadb-glue-<region>` | Glue IAM role created by this stack |
| `metadb_export.export_s3_bucket` | `mwaa-metadb-backups-<account>-<region>` | S3 bucket for backups |
| `metadb_export.max_age_days` | `30` | Max age of records to export (export DAG only) |

The restore DAG (`glue_mwaa_restore`) reads from `metadb_restore.*` first, falling back
to `metadb_export.*`, so the same config covers both unless you need different values.

You must set these on every MWAA environment that will run export or restore DAGs.
After saving, MWAA will update the environment (takes ~5 minutes).

## Upload Assets to S3 (Manual Step)

CDK creates the infrastructure but does not upload the Glue scripts or DAG files.
After deploying, upload them manually:

```bash
# Glue scripts → backup buckets
aws s3 cp assets/glue/mwaa_metadb_export.py  s3://mwaa-metadb-backups-<ACCOUNT>-<REGION>/scripts/ --region <REGION>
aws s3 cp assets/glue/mwaa_metadb_restore.py s3://mwaa-metadb-backups-<ACCOUNT>-<REGION>/scripts/ --region <REGION>

# DAGs → MWAA DAG buckets
aws s3 cp assets/dags/glue_mwaa_export.py  s3://<MWAA_DAG_BUCKET>/dags/ --region <REGION>
aws s3 cp assets/dags/glue_mwaa_restore.py s3://<MWAA_DAG_BUCKET>/dags/ --region <REGION>
```

Repeat for each region. The MWAA DAG bucket name can be found in the MWAA console
under Environment details → DAGs folder.

## Cross-Region Restore

For cross-region restore (e.g. restore us-east-1 backup into us-east-2), add a
`CrossRegionBackupAccess` inline policy to the Glue role in the target region:

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

## Usage

### Export (from MWAA UI)

Trigger DAG `glue_mwaa_export` — no config needed. Exports to:
`s3://<backup-bucket>/exports/<env-name>/YYYY/MM/DD/`

### Restore (from MWAA UI)

Trigger DAG `glue_mwaa_restore` with config:
```json
{
    "backup_path": "s3://mwaa-metadb-backups-<account>-<region>/exports/<env-name>/YYYY/MM/DD",
    "restore_mode": "append",
    "tables": ["variable", "connection", "slot_pool", "dag_run", "task_instance"]
}
```

- `backup_path`: S3 path to backup (required)
- `restore_mode`: `append` (default) or `clean` (truncate before restore)
- `tables`: list of tables (optional, defaults to all)

### Automated Restore (via Step Functions)

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:<region>:<account>:stateMachine:mwaa-metadb-auto-restore-<region> \
  --input '{}'
```

This runs: FindLatestBackup → TriggerRestoreDAG → Monitor → Validate → Notify.

## How It Works

1. DAG runs inside MWAA, reads DB credentials from environment variables
2. Creates a Glue JDBC connection with real credentials and MWAA VPC config
3. Updates the Glue job to attach the connection (places Glue ENIs in MWAA VPC)
4. Export: reads tables via Spark JDBC, writes pipe-delimited CSV to S3
5. Restore: reads CSV from S3, writes to metadb via PostgreSQL COPY FROM STDIN (pg8000)

Works with both Airflow 2.x (`SQL_ALCHEMY_CONN`) and Airflow 3.x (`DB_SECRETS`/`POSTGRES_HOST`).
