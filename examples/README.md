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

**Failover orchestrator (optional, deploy with `-c failover=true`):**
- Failover Orchestrator Step Function with cross-region restore + region flip
- Health check Lambda + EventBridge schedule (disabled by default)
- Failover flip Lambda with CLI token auto-refresh
- DynamoDB state table for active region tracking
- SNS notifications

**Key Features:**
- Works with both Airflow 2.x and 3.x
- Cross-region metadb restore via Glue JDBC
- Automated failover with restore → flip → notify pipeline
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
│    Start restore in secondary ─────────────┼──────┐              │
│    Poll until complete                     │      │              │
│    Flip region (pause/unpause DAGs)        │      │              │
│    Send SNS notification                   │      │              │
│                                            │      │              │
│  Health Check Lambda (EventBridge)         │      │              │
│    Monitors MWAA → triggers orchestrator   │      │              │
└────────────────────────────────────────────┼──────┼──────────────┘
                                             │      │
                                             ▼      ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Secondary Region (us-east-1)                    │
│                                                                  │
│  MWAA Secondary ◀── Restore Glue Job ◀── Auto-Restore SM        │
│                                           (Step Functions)       │
└──────────────────────────────────────────────────────────────────┘
```

## License

These examples are provided as-is for demonstration purposes.
