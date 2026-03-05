# MWAA Disaster Recovery Example

This example provides a complete, self-contained MWAA DR setup that deploys everything needed for a functional disaster recovery configuration across two AWS regions.

## What This Example Provides

### Complete DR Infrastructure:
- **Network infrastructure** - VPC, subnets, security groups in both regions
- **Minimal MWAA environments** - Primary and secondary MWAA (no OpenLineage/Marquez)
- **DynamoDB state management** - Tracks which region is active
- **Manual failover scripts** - Switch active region and pause/unpause DAGs
- **Test DAG included** - Verify DR behavior immediately after deployment

### What's NOT Included (Requires Separate Implementation):
- ❌ Metadata backup/restore (Airflow 3.0 limitation - see AIRFLOW3_DR_LIMITATIONS.md)
- ❌ Automatic failover (requires health monitoring - see `../automated-failover/` example)
- ❌ Data replication (S3, databases)
- ❌ OpenLineage/Marquez (this is a minimal MWAA example)

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
                              │ Read/Write by failover script
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
        ▼                                           ▼
┌──────────────────┐                       ┌──────────────────┐
│  Primary Region  │                       │ Secondary Region │
│   (us-east-2)    │                       │   (us-east-1)    │
│                  │                       │                  │
│  MWAA Env        │                       │  MWAA Env        │
│                  │                       │                  │
│  If active:      │                       │  If active:      │
│  ✓ DAGs UNPAUSED │                       │  ✓ DAGs UNPAUSED │
│  ✓ Runs execute  │                       │  ✓ Runs execute  │
│                  │                       │                  │
│  If standby:     │                       │  If standby:     │
│  ✗ DAGs PAUSED   │                       │  ✗ DAGs PAUSED   │
│  ✗ No execution  │                       │  ✗ No execution  │
└──────────────────┘                       └──────────────────┘
```

## How DR Works

### Failover Process
1. **Update DynamoDB**: Set `active_region` to target region
2. **Pause DAGs**: In the old active region (prevents execution)
3. **Unpause DAGs**: In the new active region (allows execution)
4. **Verify**: Check DAG states in both regions

### Why DAG Pause/Unpause?
- **Active region**: DAGs are unpaused and run on schedule
- **Standby region**: DAGs are paused and don't execute
- **No DAG code changes required**: Works with any existing DAGs
- **No plugin required**: Uses Airflow's built-in pause functionality

### DynamoDB State Table
- **Single source of truth** for which region is active
- Stores failover history and timestamps
- Used by failover scripts and automated failover system
- Simple, reliable, and cost-effective

## Components

### 1. DynamoDB State Table
- **Table**: `mwaa-openlineage-dr-state-dev`
- **Region**: us-east-2 (primary)
- **Purpose**: Tracks active region and failover history
- **Cost**: <$1/month

### 2. MWAA Environments
- **Primary**: `mwaa-openlineage-dr-primary-dev` (us-east-2)
- **Secondary**: `mwaa-openlineage-dr-secondary-dev` (us-east-1)
- **Size**: mw1.small (1-2 workers)
- **Version**: Airflow 3.0.6

### 3. Failover Scripts
- **Manual failover**: `scripts/failover_with_dag_control.sh`
- **DAG control**: Pause/unpause all DAGs in a region
- **State management**: Update DynamoDB active region

### 4. Test DAG
- **File**: `assets/dags/dr_test_dag.py`
- **Purpose**: Verify DR behavior
- **Schedule**: Every 5 minutes
- **Tasks**: Print region info, check region, verify execution

## Prerequisites

1. **AWS Account**: With permissions to create MWAA, VPC, DynamoDB, S3
2. **AWS CDK**: Installed and configured
3. **Python 3.9+**: For CDK deployment
4. **AWS CLI**: For manual operations

## Deployment

### Option 1: Complete Deployment (Recommended)

Deploy everything in one command:

```bash
cd examples/disaster-recovery
./deploy_complete.sh
```

This script:
1. Installs Python dependencies
2. Deploys all CDK stacks (network, S3, DynamoDB, MWAA)
3. Uploads DAGs and requirements to S3
4. Initializes DynamoDB state (sets us-east-2 as active)
5. Waits for MWAA environments to be ready

**Duration**: ~30-40 minutes (MWAA creation takes time)

After deployment completes, you'll have:
- ✅ Two MWAA environments (primary in us-east-2, secondary in us-east-1)
- ✅ DynamoDB state table with us-east-2 as active region
- ✅ Test DAG running in primary, paused in secondary
- ✅ Ready to test failover

### Option 2: Manual Step-by-Step Deployment

If you prefer manual control:

#### Step 1: Install Dependencies

```bash
cd examples/disaster-recovery
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### Step 2: Deploy Infrastructure

```bash
# Deploy all stacks
cdk deploy --all
```

This creates:
- Network stacks (VPC, subnets, security groups) in both regions
- S3 buckets for MWAA assets in both regions
- DynamoDB state table in us-east-2
- MWAA environments in both regions

#### Step 3: Upload Assets

```bash
# Get bucket names
PRIMARY_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name MwaaDRS3Primary \
  --region us-east-2 \
  --query 'Stacks[0].Outputs[?OutputKey==`MwaaBucketName`].OutputValue' \
  --output text)

SECONDARY_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name MwaaDRS3Secondary \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`MwaaBucketName`].OutputValue' \
  --output text)

# Upload DAGs
aws s3 cp assets/dags/dr_test_dag.py s3://$PRIMARY_BUCKET/dags/ --region us-east-2
aws s3 cp assets/dags/dr_test_dag.py s3://$SECONDARY_BUCKET/dags/ --region us-east-1

# Upload requirements
aws s3 cp assets/requirements/requirements.txt s3://$PRIMARY_BUCKET/ --region us-east-2
aws s3 cp assets/requirements/requirements.txt s3://$SECONDARY_BUCKET/ --region us-east-1
```

#### Step 4: Initialize DynamoDB State

```bash
aws dynamodb put-item \
  --table-name mwaa-openlineage-dr-state-dev \
  --item '{
    "state_id": {"S": "ACTIVE_REGION"},
    "active_region": {"S": "us-east-2"},
    "last_updated": {"S": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}
  }' \
  --region us-east-2
```

#### Step 5: Wait for MWAA Environments

```bash
# Check primary
aws mwaa get-environment \
  --name mwaa-openlineage-dr-primary-dev \
  --region us-east-2 \
  --query 'Environment.Status'

# Check secondary
aws mwaa get-environment \
  --name mwaa-openlineage-dr-secondary-dev \
  --region us-east-1 \
  --query 'Environment.Status'
```

Wait until both show `AVAILABLE` (takes 20-30 minutes).

## Testing

### 1. Verify Initial State

Check DynamoDB:
```bash
aws dynamodb get-item \
  --table-name mwaa-openlineage-dr-state-dev \
  --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
  --region us-east-2 \
  --query 'Item.active_region.S'
```

Should show: `us-east-2`

### 2. Check DAG States

Primary (should be unpaused):
```bash
# Access MWAA UI for primary region
aws mwaa create-web-login-token \
  --name mwaa-openlineage-dr-primary-dev \
  --region us-east-2
```

Secondary (should be paused):
```bash
# Access MWAA UI for secondary region
aws mwaa create-web-login-token \
  --name mwaa-openlineage-dr-secondary-dev \
  --region us-east-1
```

### 3. Test Manual Failover

```bash
cd scripts
./failover_with_dag_control.sh us-east-1 "Manual failover test"
```

This will:
1. Update DynamoDB: `active_region = us-east-1`
2. Pause DAGs in us-east-2
3. Unpause DAGs in us-east-1
4. Show summary of actions taken

### 4. Verify Failover

Check DynamoDB again:
```bash
aws dynamodb get-item \
  --table-name mwaa-openlineage-dr-state-dev \
  --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
  --region us-east-2
```

Should now show: `us-east-1`

Check DAG states in both regions - they should be swapped.

### 5. Failback to Primary

```bash
cd scripts
./failover_with_dag_control.sh us-east-2 "Failback to primary"
```

## Monitoring

### CloudWatch Logs

Primary MWAA logs:
```bash
aws logs tail airflow-mwaa-openlineage-dr-primary-dev-Scheduler \
  --follow \
  --region us-east-2
```

Secondary MWAA logs:
```bash
aws logs tail airflow-mwaa-openlineage-dr-secondary-dev-Scheduler \
  --follow \
  --region us-east-1
```

### DynamoDB State

Check current state:
```bash
aws dynamodb scan \
  --table-name mwaa-openlineage-dr-state-dev \
  --region us-east-2
```

### MWAA Environment Status

```bash
# Primary
aws mwaa get-environment \
  --name mwaa-openlineage-dr-primary-dev \
  --region us-east-2 \
  --query 'Environment.[Status,LastUpdate.Status]'

# Secondary
aws mwaa get-environment \
  --name mwaa-openlineage-dr-secondary-dev \
  --region us-east-1 \
  --query 'Environment.[Status,LastUpdate.Status]'
```

## Automated Failover

For automated health monitoring and failover, see the `automated-failover` example:

```bash
cd ../automated-failover
```

This adds:
- Health check Lambda (runs every minute)
- Automatic failover after 3 consecutive failures
- SNS notifications
- Cooldown period to prevent flapping

## Cleanup

### Remove All Resources

```bash
./cleanup_complete.sh
```

This will:
1. Delete MWAA environments (takes 20-30 minutes)
2. Empty and delete S3 buckets
3. Delete DynamoDB table
4. Delete VPCs and network resources
5. Delete all CDK stacks

### Manual Cleanup

If the script fails, manually delete in this order:

```bash
# Delete MWAA environments
cdk destroy MwaaDRMwaaPrimary --region us-east-2
cdk destroy MwaaDRMwaaSecondary --region us-east-1

# Delete S3 buckets (empty first)
cdk destroy MwaaDRS3Primary --region us-east-2
cdk destroy MwaaDRS3Secondary --region us-east-1

# Delete DynamoDB
cdk destroy MwaaDRStateStack --region us-east-2

# Delete networks
cdk destroy MwaaDRNetworkPrimary --region us-east-2
cdk destroy MwaaDRNetworkSecondary --region us-east-1
```

## Cost Estimate

- **MWAA environments**: ~$300/month each (mw1.small) = $600/month
- **DynamoDB**: <$1/month
- **S3**: <$5/month
- **VPC**: ~$30/month per region = $60/month
- **Data transfer**: Variable (cross-region)

**Total**: ~$665/month for complete DR setup

## Troubleshooting

### MWAA Environment Stuck in UPDATING
- Check CloudWatch Logs for errors
- Verify S3 bucket has correct files
- Check IAM role permissions

### DAGs Not Appearing
- Verify files uploaded to S3 `dags/` folder
- Check DAG processing logs in CloudWatch
- Ensure no Python syntax errors in DAG files

### Failover Script Fails
- Verify AWS CLI credentials
- Check MWAA environment names are correct
- Ensure DynamoDB table exists and is accessible

### DAGs Running in Both Regions
- Check DynamoDB `active_region` value
- Verify DAG pause states in both MWAA UIs
- Run failover script again to correct state

## Best Practices

1. **Test regularly**: Run failover drills monthly
2. **Monitor closely**: Watch CloudWatch Logs and DynamoDB
3. **Document procedures**: Create runbooks for failover scenarios
4. **Automate when ready**: Add automated failover after testing manual process
5. **Plan for data**: Implement S3 replication and database DR separately

## Limitations

See [AIRFLOW3_DR_LIMITATIONS.md](AIRFLOW3_DR_LIMITATIONS.md) for detailed information about:
- Metadata backup/restore limitations in Airflow 3.0
- What can and cannot be recovered during failover
- Workarounds and best practices

## Next Steps

1. **Test failover**: Run through the testing steps above
2. **Add automation**: Deploy the `automated-failover` example
3. **Implement data DR**: Set up S3 replication, database backups
4. **Create runbooks**: Document your specific failover procedures
5. **Train team**: Ensure team knows how to execute failover

## Support

For issues or questions:
1. Check CloudWatch Logs for both MWAA environments
2. Verify DynamoDB state table contents
3. Review MWAA environment status in AWS Console
4. Check S3 buckets have correct files

## License

This example is provided as-is for demonstration purposes.
