# Scheduler Heartbeat Behavior in MWAA

## Overview

The `SchedulerHeartbeat` metric in Amazon MWAA is only emitted when the Airflow scheduler is actively processing DAG files and scheduling tasks. This document explains the behavior and how the automated failover system handles it.

## When Scheduler Heartbeat is Missing

The `SchedulerHeartbeat` CloudWatch metric will have **no datapoints** in the following scenarios:

1. **Idle Environment**: No DAGs are scheduled to run in the near future
2. **All DAGs Paused**: All DAGs in the environment are paused
3. **No Active Tasks**: No tasks are currently running or queued
4. **New Environment**: Freshly created environment with no DAG activity yet

**This is expected behavior, not a failure.**

## Impact on Automated Failover

### Default Configuration (Recommended)

By default, the automated failover system treats missing scheduler heartbeat as a **warning, not a failure**:

```python
REQUIRE_SCHEDULER_HEARTBEAT = False  # Default
```

With this configuration:
- ✅ Environment status check is **required** (must be AVAILABLE)
- ⚠️ Scheduler heartbeat is **optional** (warns if missing, doesn't fail)
- 🔄 Failover only triggers if environment status is not AVAILABLE

This prevents false positives when your MWAA environment is idle.

### Strict Configuration (Optional)

If you have continuously running DAGs and want to detect scheduler issues specifically:

```python
REQUIRE_SCHEDULER_HEARTBEAT = True
```

With this configuration:
- ✅ Environment status check is **required**
- ✅ Scheduler heartbeat is **required**
- 🔄 Failover triggers if either check fails

**Use this only if:**
- You have DAGs that run continuously (every minute or few minutes)
- You want to detect scheduler-specific issues
- You understand this may cause false positives during idle periods

## Configuration Options

Edit `app.py` to configure health check behavior:

```python
# Health check criteria
REQUIRE_SCHEDULER_HEARTBEAT = False  # Make heartbeat mandatory (default: False)
CHECK_ENVIRONMENT_STATUS = True      # Check environment status (default: True, cannot be disabled)
```

### Environment Variables

The Lambda function receives these environment variables:

- `REQUIRE_SCHEDULER_HEARTBEAT`: "True" or "False" (default: "False")
- `CHECK_ENVIRONMENT_STATUS`: "True" or "False" (default: "True")

## Health Check Logic

### Default (Heartbeat Optional)

```python
is_healthy = True

# Environment status check (required)
if env_status != 'AVAILABLE':
    is_healthy = False
    failure_reasons.append("Environment status is not AVAILABLE")

# Scheduler heartbeat check (optional)
if not has_heartbeat:
    print("WARNING: Scheduler heartbeat missing (optional check)")
```

### Strict (Heartbeat Required)

```python
is_healthy = True

# Environment status check (required)
if env_status != 'AVAILABLE':
    is_healthy = False
    failure_reasons.append("Environment status is not AVAILABLE")

# Scheduler heartbeat check (required)
if not has_heartbeat:
    is_healthy = False
    failure_reasons.append("Scheduler heartbeat missing (required)")
```

## Troubleshooting

### False Positive Failovers

If you're experiencing false positive failovers due to missing heartbeat:

1. **Check if environment is idle**:
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace AmazonMWAA \
     --metric-name SchedulerHeartbeat \
     --dimensions Name=Environment,Value=mwaa-openlineage-dev \
     --start-time $(date -u -v-10M +%Y-%m-%dT%H:%M:%S) \
     --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
     --period 60 \
     --statistics Average \
     --region us-east-2
   ```

2. **Verify environment status**:
   ```bash
   aws mwaa get-environment \
     --name mwaa-openlineage-dev \
     --region us-east-2 \
     --query 'Environment.Status'
   ```

3. **Set heartbeat to optional** (if not already):
   ```python
   REQUIRE_SCHEDULER_HEARTBEAT = False
   ```

4. **Redeploy the stack**:
   ```bash
   cdk deploy MwaaAutomatedFailoverStack --region us-east-2
   ```

### Verifying Configuration

Check the Lambda function environment variables:

```bash
aws lambda get-function-configuration \
  --function-name mwaa-openlineage-health-check-dev \
  --region us-east-2 \
  --query 'Environment.Variables'
```

Expected output:
```json
{
  "REQUIRE_SCHEDULER_HEARTBEAT": "False",
  "CHECK_ENVIRONMENT_STATUS": "True",
  ...
}
```

## Recommendations

### For Most Users (Recommended)

Use the default configuration:
- `REQUIRE_SCHEDULER_HEARTBEAT = False`
- `CHECK_ENVIRONMENT_STATUS = True`

This provides reliable failover for actual environment failures while avoiding false positives during idle periods.

### For High-Availability Workloads

If you have continuously running DAGs and want maximum sensitivity:
- `REQUIRE_SCHEDULER_HEARTBEAT = True`
- `CHECK_ENVIRONMENT_STATUS = True`
- Increase `FAILURE_THRESHOLD` to 5 to reduce false positives
- Monitor closely after deployment

### For Testing

During testing, you may want to temporarily make heartbeat required to verify the failover logic works correctly:
- Set `REQUIRE_SCHEDULER_HEARTBEAT = True`
- Pause all DAGs to simulate missing heartbeat
- Verify failover triggers after 3 consecutive failures
- Reset to `False` for production use

## Related Documentation

- [README.md](README.md) - Main automated failover documentation
- [../disaster-recovery/README.md](../disaster-recovery/README.md) - Manual DR setup
- [AWS MWAA CloudWatch Metrics](https://docs.aws.amazon.com/mwaa/latest/userguide/cw-metrics.html)

## Support

If you're experiencing issues with scheduler heartbeat detection:

1. Check CloudWatch Logs for health check Lambda
2. Verify MWAA environment status in AWS Console
3. Review CloudWatch metrics for your environment
4. Adjust configuration based on your workload patterns
