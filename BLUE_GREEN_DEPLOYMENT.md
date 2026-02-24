# Blue-Green Deployment with Zero-Downtime Switching

## Overview

This project supports an optional blue-green deployment mode for MWAA environments, enabling zero-downtime maintenance and instant failover capability using AWS Systems Manager Parameter Store.

## What is Blue-Green Deployment?

Blue-Green deployment maintains two identical MWAA environments:
- **Blue Environment**: Primary environment
- **Green Environment**: Secondary environment

Only one environment is "active" at a time, determined by a Parameter Store flag. Switching between environments is instant (< 1 second) with no MWAA downtime.

## When to Use Blue-Green

**Use blue-green deployment when you need:**
- Zero-downtime maintenance windows
- Instant failover capability
- Safe testing of Airflow upgrades
- Quick rollback capability
- Production-critical workloads

**Don't use blue-green if:**
- Cost is a primary concern (doubles MWAA cost)
- Development/testing environment
- Downtime windows are acceptable

## Configuration

### Enable Blue-Green Mode

Edit `cdk.json`:
```json
{
  "context": {
    "enable_blue_green": true,  // Set to true for blue-green
    "project_name": "mwaa-openlineage",
    "environment": "dev",
    "region": "us-east-2"
  }
}
```

### Deployment Modes

| Mode | enable_blue_green | MWAA Environments | Cost/Month |
|------|-------------------|-------------------|------------|
| Standard | false | 1 | ~$350 |
| Blue-Green | true | 2 | ~$700 |

## Deployment

### Deploy Blue-Green Stack

```bash
# 1. Enable blue-green in cdk.json
# Set "enable_blue_green": true

# 2. Deploy all stacks
cdk deploy --all

# 3. Wait for deployment (~45 minutes with parallel creation)
# - Network stack: ~5 min
# - Marquez stack: ~10 min
# - Blue-Green MWAA stack: ~30 min (Blue and Green deploy in parallel)
```

### What Gets Deployed

**Infrastructure:**
- 1 VPC with public/private subnets
- 1 Marquez server (shared by both environments)
- 2 MWAA environments (Blue + Green)
- 2 S3 buckets (one per environment)
- Parameter Store parameter for switching

**Stacks Created:**
- `mwaa-openlineage-network-dev`
- `mwaa-openlineage-marquez-dev`
- `mwaa-openlineage-mwaa-bluegreen-dev`

## Zero-Downtime Switching

### How It Works

1. **Parameter Store Control**
   - Parameter: `/mwaa/blue-green/active-environment`
   - Values: "blue" or "green"
   - Default: "blue"

2. **DAG Runtime Check**
   - Each DAG checks parameter at start
   - Active environment executes tasks
   - Standby environment skips tasks

3. **Instant Switch**
   - Update parameter value
   - Takes effect on next DAG run
   - No MWAA configuration changes needed

### ⚠️ Important: DAG Management in Standby Environment

**The zero-downtime switching approach shown in this guide is for illustrative purposes.** It demonstrates how to use Parameter Store to control which environment executes DAGs.

**For production deployments, consider these additional strategies based on your requirements:**

1. **If DAGs should NOT run at all in standby environment:**
   - Keep DAGs paused/disabled by default in the standby environment
   - Only enable DAGs after switching to make that environment active
   - Use Airflow CLI or API to manage DAG states during switches

2. **If DAGs should be ready but not execute:**
   - Use the Parameter Store check pattern (as shown in examples)
   - Ensure all DAGs include the active environment check
   - Test thoroughly to prevent accidental dual execution

3. **If using different DAG sets per environment:**
   - Deploy different DAG files to each environment's S3 bucket
   - Use environment-specific configurations
   - Maintain separate DAG repositories per environment

**Best Practice:** Choose the approach that best fits your operational requirements and risk tolerance. The Parameter Store pattern works well for demonstration and simple use cases, but production systems may require more robust DAG lifecycle management.

### Switch Commands

**Switch to Green:**
```bash
python3 switch_zero_downtime.py --to green --region us-east-2
```

**Switch to Blue:**
```bash
python3 switch_zero_downtime.py --to blue --region us-east-2
```

**Check Current Active:**
```bash
aws ssm get-parameter \
  --name /mwaa/blue-green/active-environment \
  --region us-east-2 \
  --query 'Parameter.Value' \
  --output text
```

### Switch Timeline

```
Before Switch:
  Parameter: "blue"
  Blue: ACTIVE (executes DAGs)
  Green: STANDBY (skips DAGs)

Execute Switch: (< 1 second)
  $ python3 switch_zero_downtime.py --to green

After Switch:
  Parameter: "green"
  Blue: STANDBY (skips DAGs)
  Green: ACTIVE (executes DAGs)
```

## DAG Implementation

### Zero-Downtime DAG Pattern

Upload the example DAG to both environments:

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

# Upload to Blue
aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-blue-dev-${ACCOUNT}/dags/

# Upload to Green
aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-green-dev-${ACCOUNT}/dags/
```

### DAG Code Pattern

```python
import boto3
import os

# Get environment color from MWAA config
ENV_COLOR = os.environ.get('AIRFLOW__CUSTOM__ENVIRONMENT_COLOR', 'unknown')
PARAMETER_NAME = '/mwaa/blue-green/active-environment'

def get_active_environment():
    """Get active environment from Parameter Store"""
    ssm = boto3.client('ssm')
    response = ssm.get_parameter(Name=PARAMETER_NAME)
    return response['Parameter']['Value']

def check_if_active(**context):
    """Check if this environment is active"""
    active_env = get_active_environment()
    
    if ENV_COLOR == active_env:
        return 'execute_tasks'  # ACTIVE
    else:
        return 'skip_execution'  # STANDBY

# Use BranchPythonOperator for conditional execution
check_active = BranchPythonOperator(
    task_id='check_if_active',
    python_callable=check_if_active,
)
```

## Use Cases

### 1. Zero-Downtime Maintenance

**Scenario**: Need to update Airflow configuration

```bash
# 1. Switch to Green
python3 switch_zero_downtime.py --to green

# 2. Update Blue environment configuration
aws mwaa update-environment --name mwaa-openlineage-blue-dev ...

# 3. Wait for Blue update (~20-30 min)
# Green continues running DAGs

# 4. Test Blue environment
# Trigger test DAGs manually

# 5. Switch back to Blue
python3 switch_zero_downtime.py --to blue
```

### 2. Airflow Version Upgrade

```bash
# 1. Switch to Green
python3 switch_zero_downtime.py --to green

# 2. Upgrade Blue to new Airflow version
aws mwaa update-environment \
  --name mwaa-openlineage-blue-dev \
  --airflow-version 3.1.0

# 3. Wait for upgrade (~30 min)
# Green continues running

# 4. Test Blue with new version
# Run test DAGs

# 5. If successful, switch to Blue
python3 switch_zero_downtime.py --to blue

# 6. Upgrade Green to match
aws mwaa update-environment \
  --name mwaa-openlineage-green-dev \
  --airflow-version 3.1.0
```

### 3. Emergency Failover

```bash
# If Blue has issues, instantly switch to Green
python3 switch_zero_downtime.py --to green

# Investigate Blue issues while Green handles workload
# Fix Blue, then switch back when ready
```

## Monitoring

### Check Environment Status

```bash
# Blue status
aws mwaa get-environment \
  --name mwaa-openlineage-blue-dev \
  --region us-east-2 \
  --query 'Environment.Status'

# Green status
aws mwaa get-environment \
  --name mwaa-openlineage-green-dev \
  --region us-east-2 \
  --query 'Environment.Status'
```

### Check Active Environment

```bash
aws ssm get-parameter \
  --name /mwaa/blue-green/active-environment \
  --region us-east-2 \
  --query 'Parameter.[Value,Version,LastModifiedDate]' \
  --output table
```

### View Switch History

```bash
aws ssm get-parameter-history \
  --name /mwaa/blue-green/active-environment \
  --region us-east-2 \
  --query 'Parameters[*].[Version,Value,LastModifiedDate]' \
  --output table
```

## Architecture

### Standard Mode
```
VPC
├── Marquez (EC2, private subnet)
└── MWAA (1 environment)
```

### Blue-Green Mode
```
VPC
├── Marquez (EC2, private subnet, shared)
├── MWAA Blue (environment 1)
├── MWAA Green (environment 2)
└── Parameter Store (active flag)
```

## Cost Comparison

| Component | Standard | Blue-Green |
|-----------|----------|------------|
| MWAA Environments | 1 x $300 | 2 x $300 |
| Marquez EC2 | $30 | $30 |
| S3 Buckets | $1 | $2 |
| NAT Gateway | $32 | $32 |
| Parameter Store | $0 | $0 |
| **Total/Month** | **~$363** | **~$664** |

## Cleanup

### Destroy Blue-Green Stack

```bash
# Destroy all stacks
cdk destroy --all

# Or destroy individually (reverse order)
cdk destroy mwaa-openlineage-mwaa-bluegreen-dev
cdk destroy mwaa-openlineage-marquez-dev
cdk destroy mwaa-openlineage-network-dev
```

## Troubleshooting

### DAG Not Switching

**Issue**: DAG continues running in old environment after switch

**Solution**:
1. Check parameter value:
   ```bash
   aws ssm get-parameter --name /mwaa/blue-green/active-environment
   ```
2. Verify DAG has runtime check logic
3. Trigger DAG manually to test
4. Check task logs for environment check output

### AccessDeniedException

**Issue**: DAG can't read Parameter Store

**Solution**:
1. Verify IAM permissions exist:
   ```bash
   aws iam get-role-policy \
     --role-name <execution-role-name> \
     --policy-name SSMParameterStoreAccess
   ```
2. If missing, MWAA environment needs update to refresh IAM
3. Or redeploy with updated CDK code

### Both Environments Executing

**Issue**: Both Blue and Green running DAGs

**Solution**:
1. Check if DAGs have runtime check logic
2. Verify parameter exists and has correct value
3. Check DAG logs for environment check output
4. Ensure DAG uses BranchPythonOperator pattern

## Best Practices

1. **Always test switches in non-production first**
2. **Keep both environments in sync** (same Airflow version, config)
3. **Monitor both environments** even when one is standby
4. **Document switch procedures** for your team
5. **Test failover regularly** to ensure it works when needed
6. **Use descriptive commit messages** when switching
7. **Maintain switch history** for audit purposes

## Security Considerations

1. **Parameter Store Access**:
   - Only MWAA execution roles can read parameter
   - Parameter is in private VPC
   - No public access

2. **Environment Isolation**:
   - Separate S3 buckets per environment
   - Separate IAM roles
   - Shared Marquez with separate namespaces

3. **Audit Trail**:
   - Parameter Store maintains version history
   - CloudWatch logs all switch operations
   - CloudTrail logs all API calls

## Additional Resources

- **[ZERO_DOWNTIME_GUIDE.md](ZERO_DOWNTIME_GUIDE.md)** - Detailed implementation guide
- **[DEPLOYMENT_MODES.md](DEPLOYMENT_MODES.md)** - Comparison of all deployment modes
- **[QUICK_START.md](QUICK_START.md)** - Quick reference guide
- **[switch_zero_downtime.py](switch_zero_downtime.py)** - Switch script
- **[assets/dags/example_blue_green_zero_downtime.py](assets/dags/example_blue_green_zero_downtime.py)** - Example DAG

## Support

For issues or questions about blue-green deployment:
1. Check CloudWatch logs for both environments
2. Verify Parameter Store parameter value
3. Review DAG logs for environment check output
4. Open an issue on GitHub with details

## Summary

Blue-green deployment with zero-downtime switching provides:
- ✅ Instant failover (< 1 second)
- ✅ Zero MWAA downtime during switches
- ✅ Safe testing of changes
- ✅ Quick rollback capability
- ✅ Production-ready HA solution

The additional cost (~$300/month) provides significant operational benefits for production workloads requiring high availability.
