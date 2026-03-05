# MWAA DR - Quick Start Guide

Complete MWAA disaster recovery setup in ~50 minutes with a single command.

## What You Get

- ✅ Two MWAA environments (primary in us-east-2, secondary in us-east-1)
- ✅ Network infrastructure (VPC, subnets, security groups) in both regions
- ✅ DynamoDB state table for DR coordination
- ✅ DR plugin enabled from deployment (no manual configuration)
- ✅ Test DAG for immediate verification
- ✅ Failover scripts ready to use

## Prerequisites

```bash
# Required
- AWS CLI configured
- Python 3.8+
- Node.js 14+
- AWS CDK: npm install -g aws-cdk

# Check your setup
aws sts get-caller-identity
python3 --version
node --version
cdk --version
```

## Deploy (Single Command)

```bash
cd examples/disaster-recovery
chmod +x deploy_complete.sh
./deploy_complete.sh
```

Deployment time: ~50-60 minutes
- Network stacks: ~5 minutes each
- DynamoDB: ~2 minutes
- MWAA primary: ~25 minutes
- MWAA secondary: ~25 minutes

## Verify

### 1. Check MWAA Status

```bash
# Primary
aws mwaa get-environment \
  --name mwaa-openlineage-dr-primary-dev \
  --region us-east-2 \
  --query 'Environment.Status'

# Secondary
aws mwaa get-environment \
  --name mwaa-openlineage-dr-secondary-dev \
  --region us-east-1 \
  --query 'Environment.Status'
```

Both should return `"AVAILABLE"`.

### 2. Check DR Plugin Logs

Open Airflow UI → Admin → Logs → Scheduler Logs

**Primary (us-east-2):**
```
INFO - DR state checking ENABLED (DynamoDB)
INFO - table: mwaa-openlineage-dr-state-dev
INFO - table_region: us-east-2, current_region: us-east-2
```

**Secondary (us-east-1):**
```
INFO - DR state checking ENABLED (DynamoDB)
INFO - table_region: us-east-2, current_region: us-east-1
INFO - Skipping DAG run dr_test_dag - not active region
```

### 3. Check Test DAG

Open Airflow UI → DAGs → `dr_test_dag`

- **Primary**: DAG runs every 10 minutes, shows SUCCESS
- **Secondary**: DAG runs are SKIPPED

### 4. Check DR State

```bash
aws dynamodb get-item \
  --table-name mwaa-openlineage-dr-state-dev \
  --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
  --region us-east-2 \
  --query 'Item.active_region.S'
```

Should return `"us-east-2"`.

## Test Failover

```bash
# Switch to secondary region
./scripts/failover_with_dag_control.sh us-east-1 "Testing failover"

# Wait 30 seconds, then verify
aws dynamodb get-item \
  --table-name mwaa-openlineage-dr-state-dev \
  --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
  --region us-east-2 \
  --query 'Item.active_region.S'
```

Should now return `"us-east-1"`.

Check Airflow UI:
- **us-east-1**: DAGs now running
- **us-east-2**: DAG runs now SKIPPED

## Cleanup

```bash
chmod +x cleanup_complete.sh
./cleanup_complete.sh
```

Cleanup time: ~20-30 minutes

## Troubleshooting

### MWAA Environment Not Available

```bash
# Check status
aws mwaa get-environment \
  --name mwaa-openlineage-dr-primary-dev \
  --region us-east-2

# Check CloudFormation stack
aws cloudformation describe-stacks \
  --stack-name MwaaDRMwaaPrimary \
  --region us-east-2
```

### DR Plugin Not Working

1. Check plugin is uploaded:
```bash
aws s3 ls s3://mwaa-openlineage-dr-primary-dev-ACCOUNT/plugins/
```

2. Check MWAA configuration:
```bash
aws mwaa get-environment \
  --name mwaa-openlineage-dr-primary-dev \
  --region us-east-2 \
  --query 'Environment.AirflowConfigurationOptions'
```

Should show:
```json
{
  "dr.enabled": "true",
  "dr.state_table": "mwaa-openlineage-dr-state-dev",
  "dr.state_table_region": "us-east-2"
}
```

### Failover Script Fails

1. Check DynamoDB table exists:
```bash
aws dynamodb describe-table \
  --table-name mwaa-openlineage-dr-state-dev \
  --region us-east-2
```

2. Check IAM permissions for MWAA role to read DynamoDB

3. Check network connectivity between regions

## Next Steps

1. **Add your DAGs** - Upload to S3 buckets in both regions
2. **Configure data replication** - S3 cross-region replication, database replication
3. **Set up monitoring** - CloudWatch alarms, health checks
4. **Automate failover** - See `../automated-failover/` example
5. **Test regularly** - Schedule DR drills

## Architecture

```
Primary (us-east-2)          Secondary (us-east-1)
┌─────────────────┐          ┌─────────────────┐
│  MWAA Primary   │          │ MWAA Secondary  │
│  + DR Plugin    │          │  + DR Plugin    │
│                 │          │                 │
│  If active:     │          │  If active:     │
│  ✓ DAGs run     │          │  ✓ DAGs run     │
│                 │          │                 │
│  If standby:    │          │  If standby:    │
│  ✗ Runs SKIPPED │          │  ✗ Runs SKIPPED │
└────────┬────────┘          └────────┬────────┘
         │                            │
         └────────────┬───────────────┘
                      │
              ┌───────▼────────┐
              │   DynamoDB     │
              │  State Table   │
              │  (us-east-2)   │
              │                │
              │  active_region │
              │  = us-east-2   │
              └────────────────┘
```

## Cost Estimate

- **MWAA**: 2 x mw1.small = ~$600/month
- **NAT Gateways**: 2 x $32/month = $64/month
- **DynamoDB**: ~$0.43/month
- **S3**: Minimal (< $5/month)
- **Data Transfer**: Cross-region reads (minimal)

**Total**: ~$670/month

Reduce costs:
- Use mw1.micro for standby
- Reduce min_workers for standby
- Stop standby during non-critical periods

## Support

- Full documentation: `README.md`
- Airflow 3.0 limitations: `AIRFLOW3_DR_LIMITATIONS.md`
- Automated failover: `../automated-failover/README.md`
