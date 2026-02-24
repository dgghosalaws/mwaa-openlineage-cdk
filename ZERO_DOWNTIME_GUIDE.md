# Zero-Downtime Blue-Green Switching Guide

## Overview

This implementation provides **true zero-downtime** switching between Blue and Green MWAA environments using AWS Systems Manager Parameter Store.

### Key Benefits

✅ **Instant switching** - Takes effect on next DAG run (seconds, not minutes)  
✅ **Zero downtime** - No MWAA configuration updates required  
✅ **Both environments always available** - No UPDATING state  
✅ **Safe** - Running tasks complete normally  
✅ **Reversible** - Switch back instantly if issues occur  

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Parameter Store                             │
│  /mwaa/blue-green/active-environment = "blue" or "green"    │
└─────────────────────────────────────────────────────────────┘
                           ↓
        ┌──────────────────┴──────────────────┐
        ↓                                      ↓
┌───────────────────┐              ┌───────────────────┐
│  Blue Environment │              │ Green Environment │
│    (AVAILABLE)    │              │    (AVAILABLE)    │
│                   │              │                   │
│  DAG checks param │              │  DAG checks param │
│  Executes if      │              │  Executes if      │
│  param = "blue"   │              │  param = "green"  │
└───────────────────┘              └───────────────────┘
```

### DAG Behavior

Each DAG run:
1. Reads the Parameter Store value
2. Compares it to its own environment color
3. **If match**: Proceeds with execution
4. **If no match**: Skips execution (standby mode)

## Deployment

### 1. Deploy the Updated Stack

The stack now includes:
- Parameter Store parameter: `/mwaa/blue-green/active-environment`
- IAM permissions for MWAA to read the parameter
- Zero-downtime DAG example

```bash
cd mwaa-openlineage-cdk
cdk deploy --all --app "python3 app_blue_green.py"
```

### 2. Upload the Zero-Downtime DAG

```bash
# Upload to both environments
aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-blue-dev-$(aws sts get-caller-identity --query Account --output text)/dags/

aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-green-dev-$(aws sts get-caller-identity --query Account --output text)/dags/
```

### 3. Verify DAG Parsing

```bash
# Check Blue environment
aws logs tail airflow-mwaa-openlineage-blue-dev-DAGProcessing --since 2m | grep zero_downtime

# Check Green environment
aws logs tail airflow-mwaa-openlineage-green-dev-DAGProcessing --since 2m | grep zero_downtime
```

## Switching Environments

### Method 1: Using the Script (Recommended)

```bash
# Switch to Green
python3 switch_zero_downtime.py --to green

# Switch to Blue
python3 switch_zero_downtime.py --to blue
```

The script will:
- Show current and target environments
- Ask for confirmation
- Update the parameter
- Provide next steps

### Method 2: Using AWS CLI

```bash
# Switch to Green
aws ssm put-parameter \
  --name /mwaa/blue-green/active-environment \
  --value green \
  --overwrite

# Switch to Blue
aws ssm put-parameter \
  --name /mwaa/blue-green/active-environment \
  --value blue \
  --overwrite
```

### Method 3: Using AWS Console

1. Go to Systems Manager → Parameter Store
2. Find `/mwaa/blue-green/active-environment`
3. Click "Edit"
4. Change value to "blue" or "green"
5. Save

## Testing the Switch

### 1. Check Current Active Environment

```bash
aws ssm get-parameter \
  --name /mwaa/blue-green/active-environment \
  --query 'Parameter.Value' \
  --output text
```

### 2. Trigger DAG in Both Environments

Open both Airflow UIs and manually trigger `example_blue_green_zero_downtime`:

- **Blue UI**: https://[blue-webserver-url]
- **Green UI**: https://[green-webserver-url]

### 3. Check Task Logs

**Active environment** logs will show:
```
Environment Check
============================================================
Current Environment: blue
Active Environment: blue
============================================================
✓ This environment (blue) is ACTIVE - proceeding with execution
```

**Standby environment** logs will show:
```
Environment Check
============================================================
Current Environment: green
Active Environment: blue
============================================================
⊘ This environment (green) is STANDBY - skipping execution
```

### 4. Perform the Switch

```bash
python3 switch_zero_downtime.py --to green
```

### 5. Trigger DAGs Again

Now Green should execute and Blue should skip!

## Monitoring

### Check Active Environment

```bash
aws ssm get-parameter \
  --name /mwaa/blue-green/active-environment \
  --query 'Parameter.Value' \
  --output text
```

### View DAG Execution Logs

```bash
# Blue environment
aws logs tail airflow-mwaa-openlineage-blue-dev-Task --since 5m | grep "Environment Check"

# Green environment
aws logs tail airflow-mwaa-openlineage-green-dev-Task --since 5m | grep "Environment Check"
```

### Check Parameter History

```bash
aws ssm get-parameter-history \
  --name /mwaa/blue-green/active-environment \
  --query 'Parameters[*].[LastModifiedDate,Value]' \
  --output table
```

## Migrating Existing DAGs

To add zero-downtime switching to your existing DAGs:

### 1. Add the Environment Check

```python
import os
import boto3
from airflow.operators.python import BranchPythonOperator
from airflow.operators.empty import EmptyOperator

ENV_COLOR = os.environ.get('AIRFLOW__CUSTOM__ENVIRONMENT_COLOR', 'unknown')
PARAMETER_NAME = '/mwaa/blue-green/active-environment'

def check_if_active(**context):
    """Check if this environment is active"""
    ssm = boto3.client('ssm')
    response = ssm.get_parameter(Name=PARAMETER_NAME)
    active_env = response['Parameter']['Value']
    
    if ENV_COLOR == active_env:
        return 'your_first_task'  # Continue execution
    else:
        return 'skip_execution'   # Skip execution
```

### 2. Add Branch Operator

```python
with DAG(...) as dag:
    check_active = BranchPythonOperator(
        task_id='check_if_active',
        python_callable=check_if_active,
    )
    
    skip = EmptyOperator(task_id='skip_execution')
    
    your_first_task = ...  # Your existing first task
    
    check_active >> [skip, your_first_task]
    # Rest of your DAG...
```

## Comparison: Zero-Downtime vs Configuration-Based

| Feature | Zero-Downtime (Parameter Store) | Configuration-Based (MWAA Config) |
|---------|--------------------------------|-----------------------------------|
| Switch Time | Instant (seconds) | 20-30 minutes |
| MWAA Downtime | None | Both environments UPDATING |
| Running Tasks | Complete normally | Complete normally |
| Reversibility | Instant | 20-30 minutes |
| Complexity | Slightly more (DAG logic) | Simpler (MWAA handles it) |
| Use Case | Production, frequent switches | Maintenance windows |

## Troubleshooting

### DAG Not Skipping in Standby Environment

**Check**: Does the DAG have SSM permissions?
```bash
aws mwaa get-environment --name mwaa-openlineage-blue-dev \
  --query 'Environment.ExecutionRoleArn' --output text
```

**Fix**: Ensure IAM role has `ssm:GetParameter` permission

### Parameter Not Found Error

**Check**: Does the parameter exist?
```bash
aws ssm get-parameter --name /mwaa/blue-green/active-environment
```

**Fix**: Create it manually:
```bash
aws ssm put-parameter \
  --name /mwaa/blue-green/active-environment \
  --value blue \
  --type String \
  --description "Active MWAA environment"
```

### Both Environments Executing

**Check**: Parameter value
```bash
aws ssm get-parameter --name /mwaa/blue-green/active-environment --query 'Parameter.Value' --output text
```

**Check**: Environment color in DAG logs
```bash
aws logs tail airflow-mwaa-openlineage-blue-dev-Task --since 5m | grep "Current Environment"
```

## Best Practices

1. **Test in non-production first**: Verify the switch works as expected
2. **Monitor both environments**: Watch logs during and after switch
3. **Document switches**: Keep a log of when and why you switched
4. **Automate monitoring**: Set up CloudWatch alarms for failed DAG runs
5. **Regular testing**: Test switching monthly even if not needed
6. **Backup plan**: Know how to switch back quickly

## Cost Considerations

- **Parameter Store**: Free (Standard tier, <10,000 parameters)
- **SSM API Calls**: Minimal cost (DAGs check once per run)
- **Both Environments Running**: 2x MWAA cost, but provides true HA

## Next Steps

1. Deploy the updated stack with Parameter Store
2. Upload the zero-downtime DAG to both environments
3. Test switching between Blue and Green
4. Migrate your existing DAGs to use the pattern
5. Set up monitoring and alerting
6. Document your switch procedures

## Summary

Zero-downtime blue-green switching provides instant failover capability without any MWAA downtime. It's ideal for production environments where availability is critical and you need the ability to switch quickly for maintenance, testing, or incident response.
