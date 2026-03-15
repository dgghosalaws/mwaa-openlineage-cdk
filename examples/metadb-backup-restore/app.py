#!/usr/bin/env python3
"""
MWAA MetaDB Backup/Restore - CDK App

Deploys infrastructure for MWAA metadata database backup and restore
across two regions. Assumes MWAA environments already exist.

Existing MWAA environments:
- Primary:   mwaa-openlineage-dr-primary-dev   (us-east-2)
- Secondary: mwaa-openlineage-dr-secondary-dev (us-east-1)

This app deploys per region:
- Glue IAM role for JDBC access to MWAA metadb
- Glue jobs for export and restore
- S3 bucket for backup storage
- Step Functions workflows for orchestrating export/restore
- Lambda for Glue connection management
"""
import aws_cdk as cdk
from stacks.metadb_backup_restore_stack import MetaDBBackupRestoreStack

app = cdk.App()

# Configuration
PRIMARY_MWAA_ENV = "mwaa-openlineage-dr-primary-dev"
SECONDARY_MWAA_ENV = "mwaa-openlineage-dr-secondary-dev"
PRIMARY_REGION = "us-east-2"
SECONDARY_REGION = "us-east-1"

account = app.node.try_get_context("account") or cdk.Aws.ACCOUNT_ID

# Primary region stack (restores from secondary's backups)
MetaDBBackupRestoreStack(
    app,
    "MetaDBBackupRestorePrimary",
    mwaa_env_name=PRIMARY_MWAA_ENV,
    mwaa_region=PRIMARY_REGION,
    source_env_name=SECONDARY_MWAA_ENV,
    source_region=SECONDARY_REGION,
    backup_bucket_name=f"mwaa-metadb-backups-{account}-{PRIMARY_REGION}",
    env=cdk.Environment(account=account, region=PRIMARY_REGION),
    description="MWAA MetaDB Backup/Restore - Primary (us-east-2)",
)

# Secondary region stack (restores from primary's backups)
MetaDBBackupRestoreStack(
    app,
    "MetaDBBackupRestoreSecondary",
    mwaa_env_name=SECONDARY_MWAA_ENV,
    mwaa_region=SECONDARY_REGION,
    source_env_name=PRIMARY_MWAA_ENV,
    source_region=PRIMARY_REGION,
    backup_bucket_name=f"mwaa-metadb-backups-{account}-{SECONDARY_REGION}",
    env=cdk.Environment(account=account, region=SECONDARY_REGION),
    description="MWAA MetaDB Backup/Restore - Secondary (us-east-1)",
)

app.synth()
