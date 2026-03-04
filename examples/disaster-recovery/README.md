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
- ❌ Automatic failover (requires health monitoring - see `../automated-failover/` example)
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
- **Type**: Regional table (not Global Table)
- **Location**: Primary region (us-east-2)
- **Access**: Secondary region reads from primary region's table via cross-region access
- **Schema**:
  - `state_id`: Always "ACTIVE_REGION" (single row table)
  - `active_region`: Current active region (e.g., "us-east-2" or "us-east-1")
  - `last_updated`: Timestamp of last state change
  - `failover_count`: Number of failovers
  - `version`: Optimistic locking version number

**Why Regional Table Instead of Global Table?**

This implementation uses a regional DynamoDB table for cost-effectiveness. Here's the tradeoff:

| Aspect | Regional Table (Current) | Global Table |
|--------|-------------------------|--------------|
| Cost | ~$0.43/month | ~$2-3/month |
| Resilience | Depends on primary region | Independent replicas in both regions |
| Read Latency | Cross-region reads (~50-100ms) | Local reads (~single-digit ms) |
| Setup Complexity | Simple | More complex |
| Best For | Manual failover, infrequent updates | Automatic failover, frequent updates |

**Regional table is sufficient because:**
- State is updated only during failover (rare event)
- Single row with minimal data
- Plugin has "fail-open" design - if DynamoDB is unreachable, DAGs run (prevents outages)
- Manual failover means you're already intervening if primary region fails
- Real resilience comes from dual-mechanism approach (plugin + failover script)

**Consider Global Table if:**
- You need automatic failover without any dependency on primary region
- You're implementing active-active (both regions writing)
- You have strict latency requirements for state reads
- You want maximum resilience regardless of cost

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

- AWS CLI configured with appropriate permissions
- Python 3.8+ installed
- boto3 Python library installed

## Deployment Options

Choose the deployment path that matches your situation:

### 🆕 Option 1: Deploy New MWAA Environments with DR (Recommended)

**Best for:** Creating new MWAA environments from scratch with DR capabilities built-in

**Benefits:**
- ✅ DR plugin enabled from first deployment (no manual configuration step)
- ✅ All configuration is version-controlled in CDK code
- ✅ Consistent and repeatable deployments
- ✅ No need to update MWAA environments after deployment

**Steps:**

1. **Include DR configuration in your MWAA CDK stack:**

```python
# In your MWAA CDK stack (e.g., stacks/mwaa_stack.py)
import aws_cdk as cdk
from aws_cdk import aws_mwaa as mwaa

# Primary Region MWAA (us-east-2)
primary_mwaa = mwaa.CfnEnvironment(
    self,
    "PrimaryMwaa",
    name="mwaa-primary-dev",
    # ... other MWAA configuration (network, S3, etc.) ...
    airflow_configuration_options={
        # ... other Airflow config ...
        
        # DR Configuration - Include from the start!
        "dr.enabled": "true",
        "dr.state_table": "mwaa-openlineage-dr-state-dev",
        "dr.state_source": "dynamodb",
        "dr.state_table_region": "us-east-2",
    },
)

# Secondary Region MWAA (us-east-1) - Same DR configuration
secondary_mwaa = mwaa.CfnEnvironment(
    self,
    "SecondaryMwaa",
    name="mwaa-secondary-dev",
    # ... other MWAA configuration ...
    airflow_configuration_options={
        # ... other Airflow config ...
        
        # DR Configuration - Same as primary
        "dr.enabled": "true",
        "dr.state_table": "mwaa-openlineage-dr-state-dev",
        "dr.state_source": "dynamodb",
        "dr.state_table_region": "us-east-2",  # Same table region
    },
)
```

2. **Deploy DynamoDB state table:**

```bash
cd examples/disaster-recovery
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cdk deploy MwaaDRStateStack --region us-east-2
```

3. **Initialize DR state:**

```bash
./scripts/init_dr_state.sh us-east-2
```

4. **Upload DR plugin to S3:**

```bash
# Get your MWAA S3 bucket names
PRIMARY_BUCKET=$(aws mwaa get-environment \
  --name mwaa-primary-dev \
  --region us-east-2 \
  --query 'Environment.SourceBucketArn' \
  --output text | cut -d':' -f6)

SECONDARY_BUCKET=$(aws mwaa get-environment \
  --name mwaa-secondary-dev \
  --region us-east-1 \
  --query 'Environment.SourceBucketArn' \
  --output text | cut -d':' -f6)

# Upload plugin
aws s3 cp assets/plugins/dr_state_plugin.py s3://$PRIMARY_BUCKET/plugins/ --region us-east-2
aws s3 cp assets/plugins/dr_state_plugin.py s3://$SECONDARY_BUCKET/plugins/ --region us-east-1
```

5. **Deploy your MWAA stacks:**

```bash
cdk deploy PrimaryMwaaStack --region us-east-2
cdk deploy SecondaryMwaaStack --region us-east-1
```

**That's it!** Your MWAA environments will be created with DR plugin enabled. No manual configuration step needed.

---

### 🔧 Option 2: Add DR to Existing MWAA Environments

**Best for:** Adding DR capabilities to MWAA environments that are already deployed

**Important:** This requires a manual configuration step after deployment to enable the DR plugin.

#### Step 1: Automated Deployment Script

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

#### Step 2: ⚠️ CRITICAL - Enable DR Plugin (Required Manual Step)

**After the deployment script completes, you MUST configure the DR plugin in both MWAA environments.**

The plugin is uploaded but disabled by default. Enable it with:

**Primary Region (us-east-2):**
```bash
aws mwaa update-environment \
  --name mwaa-openlineage-dev \
  --region us-east-2 \
  --airflow-configuration-options \
    dr.enabled=true,\
    dr.state_table=mwaa-openlineage-dr-state-dev,\
    dr.state_source=dynamodb,\
    dr.state_table_region=us-east-2
```

**Secondary Region (us-east-1):**
```bash
aws mwaa update-environment \
  --name mwaa-openlineage-dev \
  --region us-east-1 \
  --airflow-configuration-options \
    dr.enabled=true,\
    dr.state_table=mwaa-openlineage-dr-state-dev,\
    dr.state_source=dynamodb,\
    dr.state_table_region=us-east-2
```

**Important Configuration Parameters:**

- `dr.enabled`: Set to `true` to enable DR plugin (REQUIRED)
- `dr.state_table`: DynamoDB table name (default: `mwaa-openlineage-dr-state-dev`)
- `dr.state_source`: State source type - `dynamodb` or `parameter_store` (default: `dynamodb`)
- `dr.state_table_region`: AWS region where DynamoDB table is located (REQUIRED for cross-region access)
  - Primary region: Set to `us-east-2` (reads from local table)
  - Secondary region: Set to `us-east-2` (reads from primary region's table via cross-region access)

**Why `dr.state_table_region` is Required:**

The DynamoDB state table is created only in the primary region (us-east-2). Both regions need to read from this same table:
- Without this parameter, each region would try to connect to a table in its own region
- Secondary region (us-east-1) would fail because no table exists there
- With this parameter, both regions connect to the table in us-east-2

**Important Notes:**
- Replace environment names with your actual MWAA environment names
- Replace table name if you used a different name
- This triggers another MWAA environment update (20-30 minutes)
- **Without this step, the DR plugin will NOT work!**

---
```bash
aws mwaa update-environment \
  --name mwaa-openlineage-minimal-dev \
  --region us-east-1 \
  --airflow-configuration-options \
    dr.enabled=true,\
    dr.state_table=mwaa-openlineage-dr-state-dev,\
    dr.state_source=dynamodb,\
    dr.state_table_region=us-east-2
```

**Important Notes:**
- Replace environment names with your actual MWAA environment names
- Replace table name if you used a different name
- This triggers another MWAA environment update (20-30 minutes)
- **Without this step, the DR plugin will NOT work!**

---

### 📋 Option 2 Alternative: Manual Step-by-Step Deployment

If you prefer step-by-step control over the automated script:

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

### Test 1: Verify Plugin Behavior

1. Check active region:
   ```bash
   aws dynamodb get-item \
     --table-name mwaa-openlineage-dr-state-dev \
     --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
     --region us-east-2 \
     --query 'Item.active_region.S'
   ```

2. Open Airflow UI in both regions and verify `dr_test_dag` status:
   - **Active region**: DAG should be UNPAUSED, runs every 10 minutes
   - **Standby region**: DAG should be PAUSED, does NOT run

3. Check DAG run logs in active region to confirm execution

### Test 2: Failover

1. Perform failover to secondary:
   ```bash
   ./scripts/failover_with_dag_control.sh us-east-1 "Testing failover"
   ```

2. Wait 30 seconds, then verify DAG status switched:
   - Old active region (us-east-2): DAGs now PAUSED
   - New active region (us-east-1): DAGs now UNPAUSED

3. Verify plugin safety net by manually unpausing a DAG in standby region - new runs will still be SKIPPED

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

### DR Plugin Configuration Parameters

The DR plugin uses these configuration parameters (set via `airflow_configuration_options`):

- `dr.enabled` - **REQUIRED**: Set to `true` to enable DR plugin
- `dr.state_table` - DynamoDB table name (default: `mwaa-openlineage-dr-state-dev`)
- `dr.state_source` - State source: `dynamodb` or `parameter_store` (default: `dynamodb`)
- `dr.state_table_region` - Region where DynamoDB table is located (default: current region)

**Important:** Configuration is set ONCE during MWAA deployment/update. After that, failover happens instantly by updating DynamoDB - no MWAA environment update needed!

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
- **DynamoDB**: Minimal (~$0.43/month for single regional table with low traffic)
- **Data transfer**: Cross-region reads from DynamoDB (secondary region reads from primary)
- **S3**: Separate buckets per region

**Cost optimization:**
- Use smaller environment class for standby (mw1.small)
- Reduce min_workers for standby
- Consider stopping standby during non-critical periods

**Note**: This uses a regional DynamoDB table (not Global Table) to minimize costs. The secondary region performs cross-region reads from the primary region's table.

## Troubleshooting

### DAGs Not Pausing/Unpausing

1. Verify plugin is installed: `aws s3 ls s3://YOUR-MWAA-BUCKET/plugins/`
2. Check scheduler logs for plugin messages
3. Verify IAM permissions for DynamoDB access
4. Confirm DynamoDB state table is accessible from both regions

### Failover Script Fails

1. Verify AWS credentials have required permissions
2. Check MWAA API is accessible in both regions
3. Verify DynamoDB table exists and is accessible
4. Check network connectivity between regions

## Next Steps

1. **Choose your deployment path** - See "Deployment Options" section above:
   - Option 1: Deploy new MWAA with DR built-in (no manual config needed)
   - Option 2: Add DR to existing MWAA (requires manual config step)
2. **Verify plugin is working** - Check scheduler logs for "DR state checking ENABLED" message
3. **Test failover** - Use `./scripts/failover_with_dag_control.sh` to test switching regions
4. **Implement data replication** - S3 cross-region replication, database replication
5. **Add monitoring** - CloudWatch alarms, health checks
6. **Automate failover** - See `../automated-failover/` example
7. **Test regularly** - Schedule DR drills
8. **Document runbooks** - Detailed operational procedures

## Related Documentation

- `AIRFLOW3_DR_LIMITATIONS.md` - Airflow 3.0 metadata backup limitations

## Support

For issues or questions:
1. Check `AIRFLOW3_DR_LIMITATIONS.md` for known limitations
2. Review CloudWatch and Airflow scheduler logs
3. Verify DynamoDB state table configuration

## License

This example is provided as-is for demonstration purposes.
