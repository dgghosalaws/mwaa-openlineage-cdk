# MWAA OpenLineage Examples

This directory contains production-ready examples for deploying MWAA with disaster recovery and automated failover capabilities.

## Available Examples

### 1. Disaster Recovery (DR)
**Path**: `disaster-recovery/`

Deploys a complete multi-region MWAA DR setup with:
- Primary MWAA environment (us-east-2)
- Secondary MWAA environment (us-east-1)
- DynamoDB state table for coordination
- Network infrastructure in both regions
- S3 buckets for MWAA assets

**Key Features:**
- Cross-region DR architecture
- Shared state management via DynamoDB
- Manual failover scripts
- Test DAG for verification

**Documentation:**
- [Quick Start Guide](disaster-recovery/QUICK_START.md)
- [Complete README](disaster-recovery/README.md)
- [Airflow 3 DR Limitations](disaster-recovery/AIRFLOW3_DR_LIMITATIONS.md)

### 2. Automated Failover
**Path**: `automated-failover/`

Adds automated health monitoring and failover to the DR setup:
- Health check Lambda (runs every minute)
- Automated failover Lambda
- EventBridge rules for scheduling
- SNS notifications for alerts
- Cooldown period to prevent flapping

**Key Features:**
- Continuous health monitoring
- Automatic failover after 3 consecutive failures
- DAG pause/unpause automation
- Email notifications
- 30-minute cooldown period

**Documentation:**
- [Complete README](automated-failover/README.md)
- [Scheduler Heartbeat Notes](automated-failover/SCHEDULER_HEARTBEAT_NOTES.md)

### 3. MetaDB Backup/Restore
**Path**: `metadb-backup-restore/`

Deploys infrastructure for MWAA metadata database backup and restore using AWS Glue:
- Glue IAM roles for JDBC access to MWAA metadb
- Glue jobs for export (read) and restore (COPY command)
- S3 bucket for backup storage
- Step Functions workflows for orchestrating export/restore
- Lambda for Glue connection management
- Airflow DAGs for triggering from within MWAA

**Key Features:**
- Works with both Airflow 2.x and 3.x
- Uses Glue JDBC connection to MWAA's PostgreSQL metadb
- Export: reads tables via Spark, writes pipe-delimited CSV to S3
- Restore: uses PostgreSQL COPY FROM STDIN for fast bulk loading
- Step Functions for external orchestration (no MWAA dependency)
- Airflow DAGs for triggering from within MWAA
- Assumes MWAA environments already exist

**Documentation:**
- [Deploy Script](metadb-backup-restore/deploy.sh)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    DynamoDB State Table                      │
│                     (us-east-2)                             │
│                                                             │
│  - active_region: which region is currently active         │
│  - health status: consecutive failures tracking            │
│  - failover history: audit trail                          │
└──────────────────────┬───────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
┌─────────────────┐           ┌─────────────────┐
│  Primary Region │           │ Secondary Region│
│   (us-east-2)   │           │   (us-east-1)   │
│                 │           │                 │
│  MWAA Env       │           │  MWAA Env       │
│  - DAGs         │           │  - DAGs         │
│  - S3 Bucket    │           │  - S3 Bucket    │
│  - VPC          │           │  - VPC          │
└─────────────────┘           └─────────────────┘
        │                             │
        └──────────────┬──────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │   Automated Failover System  │
        │                              │
        │  - Health Check Lambda       │
        │  - Failover Lambda           │
        │  - EventBridge Rules         │
        │  - SNS Notifications         │
        └──────────────────────────────┘
```

## How DR Works

### Without Automated Failover (Manual)
1. Deploy DR infrastructure in both regions
2. DynamoDB tracks which region is active
3. Manually trigger failover when needed
4. Failover script pauses DAGs in old region, unpauses in new region

### With Automated Failover
1. Health check Lambda monitors primary MWAA every minute
2. Checks environment status (must be AVAILABLE)
3. After 3 consecutive failures, triggers failover Lambda
4. Failover Lambda:
   - Updates DynamoDB active_region
   - Pauses DAGs in failed region
   - Unpauses DAGs in new active region
   - Sends SNS notification
5. 30-minute cooldown prevents rapid failovers

## Key Concepts

### DynamoDB State Table
- **Single source of truth** for which region is active
- Stores health check status and failure counts
- Tracks failover history for audit
- Used by both health check and failover Lambdas

### DAG Pause/Unpause
- **Active region**: DAGs are unpaused and run normally
- **Standby region**: DAGs are paused and don't execute
- Failover switches which region has unpaused DAGs
- No DAG code changes required
- No plugin required

### Why No Plugin?
Airflow listener plugins cannot prevent DAG execution because:
- `on_dag_run_running` hook fires AFTER tasks are queued
- No hook exists that fires before DAG run creation
- Lambda-based pause/unpause is the correct approach

## Deployment Order

1. **Deploy DR Infrastructure** (disaster-recovery/)
   ```bash
   cd disaster-recovery
   ./deploy_complete.sh
   ```

2. **Deploy Automated Failover** (automated-failover/)
   ```bash
   cd ../automated-failover
   cdk deploy MwaaAutomatedFailoverStack --region us-east-2
   ```

3. **Verify Setup**
   - Check DynamoDB for active_region
   - Verify DAGs are paused in standby region
   - Check CloudWatch Logs for health checks

## Testing

### Test Manual Failover
```bash
cd disaster-recovery/scripts
./failover_with_dag_control.sh us-east-1 "Manual test"
```

### Test Automated Failover
1. Check CloudWatch Logs for health check Lambda
2. Verify health checks run every minute
3. Simulate failure (optional - will trigger real failover)
4. Verify failover completes and DAGs switch regions

## Monitoring

### CloudWatch Logs
- Health check: `/aws/lambda/mwaa-openlineage-health-check-dev`
- Failover: `/aws/lambda/mwaa-openlineage-automated-failover-dev`

### DynamoDB
```bash
# Check active region
aws dynamodb get-item \
  --table-name mwaa-openlineage-dr-state-dev \
  --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
  --region us-east-2

# Check health status
aws dynamodb get-item \
  --table-name mwaa-openlineage-dr-state-dev \
  --key '{"state_id": {"S": "HEALTH_us-east-2"}}' \
  --region us-east-2
```

## Cost Considerations

### DR Infrastructure
- 2 MWAA environments: ~$600/month (mw1.small)
- DynamoDB: <$1/month
- S3: <$5/month
- VPC: ~$30/month per region

### Automated Failover
- Lambda invocations: ~$0.20/month
- CloudWatch Logs: ~$0.50/month
- SNS: ~$0.01/month
- **Total added cost**: ~$1/month

## Cleanup

### Remove Automated Failover
```bash
cd automated-failover
cdk destroy MwaaAutomatedFailoverStack --region us-east-2
```

### Remove DR Infrastructure
```bash
cd disaster-recovery
./cleanup_complete.sh
```

## Best Practices

1. **Test in non-production first** - Verify failover works before production use
2. **Monitor closely** - Watch CloudWatch Logs and DynamoDB state
3. **Tune thresholds** - Adjust failure threshold and cooldown based on your needs
4. **Document runbooks** - Create procedures for handling failover events
5. **Regular drills** - Test failover periodically to ensure it works

## Troubleshooting

### DAGs Running in Both Regions
- Check DynamoDB active_region value
- Verify automated failover Lambda has correct permissions
- Check if DAGs are actually paused in standby region

### Health Checks Failing
- Verify MWAA environment status is AVAILABLE
- Check if environment is idle (missing heartbeat is normal)
- Review health check Lambda logs for specific errors

### Failover Not Triggering
- Check consecutive_failures in DynamoDB
- Verify not in cooldown period
- Check EventBridge rule is enabled
- Review health check Lambda permissions

## Support

For issues or questions:
1. Check CloudWatch Logs for both Lambda functions
2. Verify DynamoDB state table contents
3. Review MWAA environment status in both regions
4. Check SNS topic subscriptions

## License

These examples are provided as-is for demonstration purposes.
