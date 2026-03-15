# MWAA OpenLineage Examples

Production-ready examples for deploying MWAA with disaster recovery and failover capabilities.

## Available Examples

### 1. Disaster Recovery (DR)
**Path**: `disaster-recovery/`

Deploys a multi-region MWAA setup:
- VPC + networking in both regions
- S3 buckets for MWAA assets in both regions
- Two MWAA environments (primary + secondary)
- Test DAG for verification

This is the foundational infrastructure. Deploy this first, then layer on
backup/restore and failover orchestration from the second example.

**Documentation:**
- [Quick Start Guide](disaster-recovery/QUICK_START.md)
- [Complete README](disaster-recovery/README.md)

### 2. MetaDB Backup/Restore with Failover Orchestration
**Path**: `metadb-backup-restore/`

The complete DR solution. Deploys metadata database backup/restore infrastructure
plus an optional failover orchestrator that chains restore → region flip → notification.

**Base infrastructure (per region):**
- Glue jobs for metadb export (JDBC → CSV) and restore (CSV → PostgreSQL COPY)
- S3 buckets for backup storage
- Step Functions for automated restore orchestration
- Lambda functions for Glue connection management
- Airflow DAGs for triggering export/restore from within MWAA

**Failover/Fallback orchestrators (optional, deploy with `-c failover=true`):**
- Failover Orchestrator Step Function: pause primary → cross-region restore into secondary → activate secondary
- Fallback Orchestrator Step Function: pause secondary → restore into primary → activate primary
- Health check Lambda + EventBridge schedule (disabled by default)
- Failover flip Lambda with CLI token auto-refresh
- DynamoDB state table for active region tracking
- SNS notifications

**Key Features:**
- Works with both Airflow 2.x and 3.x
- Cross-region metadb restore via Glue JDBC
- Bidirectional failover/fallback with restore → flip → notify pipeline
- DAGs are paused before restore to ensure data consistency
- Designed for planned failover simulations (not full regional outages)
- EventBridge health check deploys disabled by default for safety

**Documentation:**
- [Complete README](metadb-backup-restore/README.md)

## Deployment Order

1. Deploy DR infrastructure first (`disaster-recovery/`) to create the MWAA environments
2. Deploy backup/restore (`metadb-backup-restore/`) for metadb protection
3. Optionally enable the failover orchestrator with `-c failover=true`

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Primary Region (us-east-2)                     │
│                                                                  │
│  MWAA Primary ──▶ Export Glue Job ──▶ S3 Backup Bucket          │
│                                            │                     │
│  Failover Orchestrator (Step Functions)     │                     │
│    Pause DAGs in primary                   │                     │
│    Start restore in secondary ─────────────┼──────┐              │
│    Poll until complete                     │      │              │
│    Update DDB + unpause secondary DAGs     │      │              │
│    Send SNS notification                   │      │              │
│                                            │      │              │
│  Fallback Orchestrator (Step Functions)     │      │              │
│    Pause DAGs in secondary                 │      │              │
│    Start restore in primary                │      │              │
│    Poll until complete                     │      │              │
│    Update DDB + unpause primary DAGs       │      │              │
│    Send SNS notification                   │      │              │
│                                            │      │              │
│  Health Check Lambda (EventBridge)         │      │              │
│    Monitors MWAA → triggers failover       │      │              │
└────────────────────────────────────────────┼──────┼──────────────┘
                                             │      │
                                             ▼      ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Secondary Region (us-east-1)                    │
│                                                                  │
│  MWAA Secondary ◀── Restore Glue Job ◀── Auto-Restore SM        │
│                                           (Step Functions)       │
│  MWAA Secondary ──▶ Export Glue Job ──▶ S3 Backup Bucket        │
│                                          (for fallback)          │
└──────────────────────────────────────────────────────────────────┘
```

## License

These examples are provided as-is for demonstration purposes.
