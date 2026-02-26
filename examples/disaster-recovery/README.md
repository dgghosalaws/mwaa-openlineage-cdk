# MWAA Disaster Recovery Example

This example demonstrates how to deploy MWAA in a disaster recovery (DR) configuration across two AWS regions with automatic DAG control based on the active region.

## What This Example Provides

### Core DR Capabilities:
- **Dual-region MWAA deployment** - Primary and secondary MWAA environments
- **DynamoDB state management** - Tracks which region is active
- **Automatic DAG run skipping** - Plugin prevents DAG runs in standby region
- **Manual failover with DAG control** - Scripts to switch active region and pause/unpause DAGs

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
│  ✓ DAGs UNPAUSED │                       │  ✓ DAGs UNPAUSED │
│  ✓ Runs execute  │                       │  ✓ Runs execute  │
│                  │                       │                  │
│  If standby:     │                       │  If standby:     │
│  ✗ DAGs PAUSED   │                       │  ✗ DAGs PAUSED   │
│  ✗ Plugin skips  │                       │  ✗ Plugin skips  │
│    new runs      │                       │    new runs      │
└──────────────────┘                       └──────────────────┘
```

### How DAG Control Works

The DR solution uses a dual-mechanism approach:

1. **Failover Script (Active Control)**:
   - Runs during failover
   - Pauses DAGs in old active region via Airflow API
   - Unpauses DAGs in new active region via Airflow API
   - Ensures DAGs are in correct state immediately after failover

2. **DR State Plugin (Safety Net)**:
   - Runs on every DAG run start
   - Checks DynamoDB for active region
   - Skips DAG run if current region is not active
   - Provides protection even if DAG is accidentally unpaused in standby region

This dual approach ensures no DAG runs execute in the standby region, even if:
- Someone manually unpauses a DAG in standby region
- Failover script fails to pause a DAG
- New DAGs are added after failover

## Components

### 1. DynamoDB State Table
- **Purpose**: Single source of truth for active region
- **Location**: Primary region (us-east-2)
- **Access**: Both regions read from this table
- **Schema**:
  - `state_id`: Always "ACTIVE_REGION" (single row table)
  - `active_region`: Current active region (e.g., "us-east-2" or "us-east-1")
  - `last_updated`: Timestamp of last state change
  - `failover_count`: Number of failovers
  - `version`: Optimistic locking version number

### 2. DR State Plugin
- **File**: `assets/plugins/dr_state_plugin.py`
- **Purpose**: Automatically skips DAG runs in standby region
- **How it works**: 
  - Runs on every DAG run start
  - Reads active region from DynamoDB
  - If current region is not active, marks DAG run as SKIPPED
  - Provides safety net to prevent accidental execution in standby region
- **Note**: This plugin SKIPS new DAG runs but doesn't pause the DAG itself. DAGs are paused/unpaused during failover via the failover script.

### 3. Deployment Script
- `deploy_dr_simple.sh` - Automated deployment to existing MWAA environments
- Verifies MWAA environments exist
- Deploys DynamoDB state table
- Uploads plugin and triggers MWAA updates

### 4. Failover Scripts
- `scripts/failover_with_dag_control.sh` - Switch active region and control DAGs
  - Updates DynamoDB to set new active region
  - Pauses all DAGs in old active region (via Airflow API)
  - Unpauses all DAGs in new active region (via Airflow API)
  - Completes in ~15-20 seconds
- `scripts/init_dr_state.sh` - Initialize DynamoDB state

### 5. Test DAG (Optional)
- `assets/dags/dr_test_dag.py` - Airflow 3.0 compatible test DAG
- Runs every 10 minutes in active region
- Automatically paused in standby region
- Prints region info and execution details
- Helps verify DR plugin is working correctly

## Prerequisites

This DR example adds disaster recovery capabilities to EXISTING MWAA environments. You must have:

- **Two MWAA environments already deployed** in different AWS regions
- AWS CLI configured with appropriate permissions
- Python 3.8+ installed
- boto3 Python library installed

If you don't have MWAA environments yet, deploy them first using the main repository stacks or AWS Console, then return here to add DR capabilities.

## Deployment

### Option A: Automated Deployment (Recommended)

Use the provided script to deploy all components:

```bash
cd examples/disaster-recovery
chmod +x deploy_dr_simple.sh
./deploy_dr_simple.sh
```

The script will:
1. Verify your existing MWAA environments
2. Deploy DynamoDB state table
3. Initialize DR state (set active region)
4. Upload DR plugin to both MWAA environments
5. Trigger MWAA environment updates to load the plugin
6. Upload test DAG (optional)

Important: MWAA takes 20-30 minutes to apply plugin updates. The environments will show "Updating" status during this time.

### Option B: Manual Deployment

If you prefer step-by-step control:

#### Step 1: Configure Your Environment Names

Edit `deploy_dr_simple.sh` and update these variables:

```bash
PRIMARY_MWAA_NAME="your-primary-mwaa-name"
SECONDARY_MWAA_NAME="your-secondary-mwaa-name"
PRIMARY_REGION="us-east-2"
SECONDARY_REGION="us-east-1"
```

#### Step 2: Deploy DynamoDB State Table

```bash
cd examples/disaster-recovery
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

cdk deploy MwaaDRStateStack --region us-east-2
```

#### Step 3: Initialize DR State

```bash
./scripts/init_dr_state.sh us-east-2
```

This sets us-east-2 as the initial active region.

#### Step 4: Upload DR Plugin

Get your MWAA S3 bucket names:

```bash
PRIMARY_BUCKET=$(aws mwaa get-environment \
  --name YOUR-PRIMARY-MWAA-NAME \
  --region us-east-2 \
  --query 'Environment.SourceBucketArn' \
  --output text | cut -d':' -f6)

SECONDARY_BUCKET=$(aws mwaa get-environment \
  --name YOUR-SECONDARY-MWAA-NAME \
  --region us-east-1 \
  --query 'Environment.SourceBucketArn' \
  --output text | cut -d':' -f6)
```

Upload plugin to both regions:

```bash
aws s3 cp assets/plugins/dr_state_plugin.py \
  s3://$PRIMARY_BUCKET/plugins/ \
  --region us-east-2

aws s3 cp assets/plugins/dr_state_plugin.py \
  s3://$SECONDARY_BUCKET/plugins/ \
  --region us-east-1
```

#### Step 5: Trigger MWAA to Load Plugin

```bash
# Update primary environment
aws mwaa update-environment \
  --name YOUR-PRIMARY-MWAA-NAME \
  --region us-east-2 \
  --plugins-s3-path plugins/dr_state_plugin.py

# Update secondary environment
aws mwaa update-environment \
  --name YOUR-SECONDARY-MWAA-NAME \
  --region us-east-1 \
  --plugins-s3-path plugins/dr_state_plugin.py
```

Wait 20-30 minutes for MWAA to apply updates.

#### Step 6: Upload Test DAG (Optional but Recommended)

```bash
aws s3 cp assets/dags/dr_test_dag.py \
  s3://$PRIMARY_BUCKET/dags/ \
  --region us-east-2

aws s3 cp assets/dags/dr_test_dag.py \
  s3://$SECONDARY_BUCKET/dags/ \
  --region us-east-1
```

MWAA automatically detects new DAGs within 30 seconds.

#### Step 7: Verify Plugin is Working

Check Airflow scheduler logs in both regions:

Active region should show:
```
INFO - DR State Plugin: Current region us-east-2 is ACTIVE
INFO - DR State Plugin: Unpausing all DAGs
```

Standby region should show:
```
INFO - DR State Plugin: Current region us-east-1 is STANDBY
INFO - DR State Plugin: Pausing all DAGs
```

Check the test DAG in Airflow UI:
- **Active region**: `dr_test_dag` should be UNPAUSED and running every 10 minutes
- **Standby region**: `dr_test_dag` should be PAUSED and NOT running

## Failover Procedure

### How Failover Works

The DR solution uses two mechanisms to prevent DAG execution in standby region:

1. **Plugin Safety Net**: The DR state plugin automatically skips any NEW DAG runs that start in the standby region
2. **Failover Script**: During failover, the script actively pauses DAGs in the old active region and unpauses them in the new active region

This dual approach ensures:
- No DAG runs execute in standby region (plugin prevents new runs)
- DAGs are properly paused/unpaused during failover (script manages state)
- Fast failover (~15-20 seconds total)

### Manual Failover

To switch from us-east-2 (primary) to us-east-1 (secondary):

```bash
./scripts/failover_with_dag_control.sh us-east-1 "Planned maintenance"
```

This will:
1. Update DynamoDB: active_region = us-east-1 (~1 second)
2. Pause all DAGs in us-east-2 via Airflow API (~5-10 seconds)
3. Unpause all DAGs in us-east-1 via Airflow API (~5-10 seconds)
4. Verify state change

Total time: ~15-20 seconds

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

1. Perform failover to secondary:
   ```bash
   ./scripts/failover_with_dag_control.sh us-east-1 "Testing failover"
   ```

2. Wait 30 seconds for failover to complete

3. Check `dr_test_dag` status in both regions:
   - Old active region (us-east-2): DAG should now be PAUSED
   - New active region (us-east-1): DAG should now be UNPAUSED

4. Verify DAG runs:
   - Old active region: No new runs (DAG is paused)
   - New active region: New runs every 10 minutes (DAG is unpaused)

5. Check logs in new active region to confirm execution

6. Verify plugin safety net:
   - If you manually unpause a DAG in standby region, new runs will still be SKIPPED by the plugin
   - This provides double protection against accidental execution

## Configuration

### DynamoDB State Table

The state table uses this schema:

```json
{
  "state_id": "ACTIVE_REGION",
  "active_region": "us-east-2",
  "last_updated": "2024-02-26T10:30:00Z",
  "failover_count": 0,
  "version": 1
}
```

### DR Plugin Configuration

The DR state plugin reads configuration from Airflow configuration options. Add these to your MWAA environment configuration:

```json
{
  "dr.enabled": "true",
  "dr.state_table": "mwaa-openlineage-dr-state-dev",
  "dr.state_source": "dynamodb",
  "dr.state_table_region": "us-east-2"
}
```

You can add these via AWS Console or CLI:

```bash
aws mwaa update-environment \
  --name YOUR-MWAA-NAME \
  --region YOUR-REGION \
  --airflow-configuration-options \
    dr.enabled=true,\
    dr.state_table=mwaa-openlineage-dr-state-dev,\
    dr.state_source=dynamodb,\
    dr.state_table_region=us-east-2
```

The plugin also supports environment variables as fallback:
- `DR_ENABLED` - Enable/disable DR plugin
- `DR_STATE_TABLE` - DynamoDB table name
- `DR_STATE_SOURCE` - State source (dynamodb)
- `DR_STATE_TABLE_REGION` - DynamoDB table region

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
