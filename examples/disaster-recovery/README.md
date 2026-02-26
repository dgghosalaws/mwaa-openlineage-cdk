# MWAA Disaster Recovery Example

This example demonstrates how to deploy MWAA in a disaster recovery (DR) configuration across two AWS regions with automatic DAG control based on the active region.

## What This Example Provides

### Core DR Capabilities:
- **Dual-region MWAA deployment** - Primary and secondary MWAA environments
- **DynamoDB state management** - Tracks which region is active
- **Automatic DAG control** - DAGs pause/unpause based on active region
- **Manual failover** - Scripts to switch active region

### What's NOT Included (Requires Separate Implementation):
- ❌ Metadata backup/restore (Airflow 3.0 limitation - see AIRFLOW3_DR_LIMITATIONS.md)
- ❌ Automatic failover (requires health monitoring)
- ❌ Data replication (S3, databases)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     DynamoDB State Table                     │
│                      (us-east-2)                            │
│                                                             │
│  state_id: ACTIVE_REGION                                   │
│  active_region: "us-east-1" or "us-east-2"               │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Reads state
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
        ▼                                           ▼
┌──────────────────┐                       ┌──────────────────┐
│  Primary Region  │                       │ Secondary Region │
│   (us-east-2)    │                       │   (us-east-1)    │
│                  │                       │                  │
│  MWAA Env        │                       │  MWAA Env        │
│  + Plugin        │                       │  + Plugin        │
│                  │                       │                  │
│  If active:      │                       │  If active:      │
│  ✓ DAGs run      │                       │  ✓ DAGs run      │
│                  │                       │                  │
│  If standby:     │                       │  If standby:     │
│  ✗ DAGs paused   │                       │  ✗ DAGs paused   │
└──────────────────┘                       └──────────────────┘
```

## Components

### 1. DynamoDB State Table
- **Purpose**: Single source of truth for active region
- **Location**: Primary region (us-east-2)
- **Access**: Both regions read from this table

### 2. DR State Plugin
- **File**: `assets/plugins/dr_state_plugin.py`
- **Purpose**: Automatically pauses/unpauses DAGs based on active region
- **How it works**: 
  - Runs on scheduler startup and periodically
  - Reads active region from DynamoDB
  - Pauses all DAGs if current region is not active
  - Unpauses all DAGs if current region is active

### 3. CDK Stacks
- `mwaa_dr_state_stack.py` - DynamoDB state table
- `mwaa_dr_primary_stack.py` - Primary MWAA environment
- `mwaa_dr_secondary_stack.py` - Secondary MWAA environment

### 4. Failover Scripts
- `failover_with_dag_control.sh` - Switch active region
- `init_dr_state.sh` - Initialize DynamoDB state

### 5. Test DAG (Optional)
- `assets/dags/dr_test_dag.py` - Airflow 3.0 compatible test DAG
- Runs every 10 minutes in active region
- Automatically paused in standby region
- Prints region info and execution details
- Helps verify DR plugin is working correctly

## Prerequisites

- AWS CDK installed
- Two AWS regions configured
- Existing VPC and networking (or use main repo's network stack)

## Deployment

### Step 1: Deploy DynamoDB State Table

```bash
cd examples/disaster-recovery
cdk deploy MwaaDRStateStack --region us-east-2
```

### Step 2: Initialize DR State

```bash
./scripts/init_dr_state.sh us-east-2
```

This sets us-east-2 as the initial active region.

### Step 3: Deploy Primary MWAA Environment

```bash
cdk deploy MwaaDRPrimaryStack --region us-east-2
```

### Step 4: Deploy Secondary MWAA Environment

```bash
cdk deploy MwaaDRSecondaryStack --region us-east-1
```

### Step 5: Deploy Test DAG (Optional but Recommended)

Upload the test DAG to both regions:

```bash
# Upload to primary region
aws s3 cp assets/dags/dr_test_dag.py \
  s3://YOUR-PRIMARY-MWAA-BUCKET/dags/ \
  --region us-east-2

# Upload to secondary region
aws s3 cp assets/dags/dr_test_dag.py \
  s3://YOUR-SECONDARY-MWAA-BUCKET/dags/ \
  --region us-east-1
```

### Step 6: Verify Plugin is Working

Check Airflow scheduler logs in both regions to see:
```
INFO - DR State Plugin: Current region us-east-2 is ACTIVE
INFO - DR State Plugin: Unpausing all DAGs
```

or

```
INFO - DR State Plugin: Current region us-east-1 is STANDBY
INFO - DR State Plugin: Pausing all DAGs
```

Check the test DAG in Airflow UI:
- **Active region**: `dr_test_dag` should be UNPAUSED and running every 10 minutes
- **Standby region**: `dr_test_dag` should be PAUSED and NOT running

## Failover Procedure

### Manual Failover

To switch from us-east-2 (primary) to us-east-1 (secondary):

```bash
./scripts/failover_with_dag_control.sh us-east-1 "Planned maintenance"
```

This will:
1. Update DynamoDB: active_region = us-east-1
2. Pause DAGs in us-east-2 (via API)
3. Unpause DAGs in us-east-1 (via API)
4. Verify state change

### Fallback

To switch back to primary:

```bash
./scripts/failover_with_dag_control.sh us-east-2 "Returning to primary"
```

## Testing

### Test 1: Verify Plugin Behavior with Test DAG

1. Deploy the test DAG to both regions (see Step 5 above)

2. Check active region:
   ```bash
   aws dynamodb get-item \
     --table-name mwaa-openlineage-dr-state-dev \
     --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
     --region us-east-2 \
     --query 'Item.active_region.S'
   ```

3. Open Airflow UI in both regions

4. Verify `dr_test_dag` status:
   - **Active region**: DAG should be UNPAUSED, runs every 10 minutes
   - **Standby region**: DAG should be PAUSED, does NOT run

5. Check DAG run logs in active region:
   - Should see "This DAG is running in: us-east-2" (or your active region)
   - Should see region info and execution details

6. Verify standby region:
   - DAG should be paused
   - No new DAG runs should appear
   - If DAG runs in standby, plugin is NOT working correctly

### Test 2: Failover

1. Perform failover to secondary
2. Wait 2-3 minutes for plugin to detect change
3. Check `dr_test_dag` status in both regions:
   - Old active region: DAG should now be PAUSED
   - New active region: DAG should now be UNPAUSED
4. Verify DAG runs:
   - Old active region: No new runs
   - New active region: New runs every 10 minutes
5. Check logs in new active region to confirm execution

## Configuration

### MWAA Configuration Options

Both environments need these Airflow configuration options:

```json
{
  "dr.enabled": "true",
  "dr.state_table": "mwaa-openlineage-dr-state-dev",
  "dr.state_source": "dynamodb",
  "dr.state_table_region": "us-east-2"
}
```

### Plugin Configuration

The DR state plugin reads configuration from:
1. Airflow configuration options (preferred)
2. Environment variables (fallback)

## Limitations

### Airflow 3.0 Metadata Backup
Airflow 3.0 removed direct database access, making traditional metadata backup impossible. See `AIRFLOW3_DR_LIMITATIONS.md` for details.

**Recommended alternatives:**
- Use AWS Backup for MWAA environments
- Use RDS snapshots (if accessible)
- Maintain DAG code in Git
- Use Infrastructure as Code (CDK)

### Data Replication
This example does NOT handle:
- S3 bucket replication (configure separately)
- Database replication (configure separately)
- Secrets Manager replication (configure separately)

### Automatic Failover
This example provides manual failover only. For automatic failover, you need:
- Health monitoring (CloudWatch, Route53 health checks)
- Automated decision logic
- Notification system

## Cost Considerations

Running dual-region MWAA:
- **MWAA environments**: 2x cost (one per region)
- **DynamoDB**: Minimal (single table, low traffic)
- **Data transfer**: Cross-region reads from DynamoDB
- **S3**: Separate buckets per region

**Cost optimization:**
- Use smaller environment class for standby (mw1.small)
- Reduce min_workers for standby
- Consider stopping standby during non-critical periods

## Troubleshooting

### DAGs Not Pausing/Unpausing

1. Check plugin is installed:
   ```bash
   aws s3 ls s3://YOUR-MWAA-BUCKET/plugins/
   ```

2. Check scheduler logs for plugin messages

3. Verify IAM permissions for DynamoDB access

4. Check DynamoDB state table is accessible

### Failover Script Fails

1. Verify AWS credentials have permissions
2. Check MWAA API is accessible
3. Verify DynamoDB table exists and is accessible
4. Check network connectivity between regions

## Next Steps

1. **Implement data replication** - S3 cross-region replication, database replication
2. **Add monitoring** - CloudWatch alarms, health checks
3. **Automate failover** - Lambda functions, Step Functions
4. **Test regularly** - Schedule DR drills
5. **Document runbooks** - Detailed operational procedures

## Related Documentation

- `AIRFLOW3_DR_LIMITATIONS.md` - Airflow 3.0 metadata backup limitations

## Support

For issues or questions:
1. Check AIRFLOW3_DR_LIMITATIONS.md for known limitations
2. Review CloudWatch logs
3. Check Airflow scheduler logs
4. Verify DynamoDB state table

## License

This example is provided as-is for demonstration purposes.
