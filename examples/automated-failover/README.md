# MWAA Automated Failover

This example adds automated failover capabilities to the MWAA DR setup. It continuously monitors the primary MWAA environment and automatically triggers failover to the secondary region when health issues are detected.

## Prerequisites

1. **Disaster Recovery Example Deployed**: You must first deploy the `disaster-recovery` example
2. **MWAA Environments**: Both primary and secondary MWAA environments must be running
3. **DynamoDB State Table**: The DR state table must exist
4. **AWS CDK**: Installed and configured

## What This Example Provides

### Automated Failover Features:
- **Continuous health monitoring** - Checks primary MWAA every 1 minute
- **Automatic failover** - Triggers after 3 consecutive health check failures
- **Flapping prevention** - 30-minute cooldown period after failover
- **Email notifications** - Alerts on health warnings and failover events
- **Manual override** - Can still trigger manual failover when needed

### Health Check Criteria:
1. **MWAA Environment Status**: Must be AVAILABLE
2. **Scheduler Heartbeat**: Must have recent heartbeat metrics in CloudWatch

If both checks fail 3 times in a row, automated failover is triggered.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  EventBridge Rule                            │
│                  (every 1 minute)                           │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Health Check Lambda                             │
│                                                             │
│  1. Check MWAA environment status                          │
│  2. Check scheduler heartbeat                              │
│  3. Update health state in DynamoDB                        │
│  4. Track consecutive failures                             │
│  5. Trigger failover if threshold reached                  │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       │ (if 3 failures)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Failover Lambda                                 │
│                                                             │
│  1. Update DynamoDB (active region)                        │
│  2. Pause DAGs in failed region                            │
│  3. Unpause DAGs in secondary region                       │
│  4. Send SNS notification                                  │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  SNS Topic                                   │
│              (Email Notifications)                          │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

Edit `app.py` to configure:

```python
# MWAA environment names
PRIMARY_ENV_NAME = "mwaa-openlineage-dev"
SECONDARY_ENV_NAME = "mwaa-openlineage-minimal-dev"

# Regions
PRIMARY_REGION = "us-east-2"
SECONDARY_REGION = "us-east-1"

# Health check configuration
HEALTH_CHECK_INTERVAL = "rate(1 minute)"  # How often to check
FAILURE_THRESHOLD = 3  # Failures before failover
COOLDOWN_MINUTES = 30  # Cooldown after failover

# Notification emails
NOTIFICATION_EMAILS = [
    "your-email@example.com",
]
```

### Configuration Options:

- **HEALTH_CHECK_INTERVAL**: How often to check health
  - `rate(1 minute)` - Check every minute (recommended)
  - `rate(5 minutes)` - Check every 5 minutes (less sensitive)

- **FAILURE_THRESHOLD**: Consecutive failures before failover
  - `3` - Failover after 3 failures (recommended, ~3 minutes)
  - `5` - Failover after 5 failures (more conservative, ~5 minutes)

- **COOLDOWN_MINUTES**: Prevent flapping after failover
  - `30` - 30 minute cooldown (recommended)
  - `60` - 1 hour cooldown (more conservative)

## Deployment

### Step 1: Install Dependencies

```bash
cd examples/automated-failover
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Configure Notification Emails

Edit `app.py` and add your email addresses:

```python
NOTIFICATION_EMAILS = [
    "ops-team@example.com",
    "oncall@example.com",
]
```

### Step 3: Deploy Stack

```bash
cdk deploy MwaaAutomatedFailoverStack --region us-east-2
```

### Step 4: Confirm SNS Subscriptions

Check your email and confirm the SNS subscription for each email address you added.

### Step 5: Verify Deployment

Check CloudWatch Logs for the health check Lambda:

```bash
aws logs tail /aws/lambda/mwaa-openlineage-health-check-dev \
  --follow \
  --region us-east-2
```

You should see health check logs every minute.

## How It Works

### Normal Operation

1. **Every 1 minute**: Health check Lambda runs
2. **Checks primary MWAA**: Environment status + scheduler heartbeat
3. **If healthy**: Resets failure counter, no action taken
4. **If unhealthy**: Increments failure counter, sends warning notification

### Failover Trigger

1. **3 consecutive failures**: Health check threshold reached
2. **Cooldown check**: Ensures not in cooldown period from recent failover
3. **Trigger failover**: Invokes failover Lambda asynchronously
4. **Notification sent**: "Failover Triggered" email

### Failover Execution

1. **Update DynamoDB**: Set active_region to secondary
2. **Pause DAGs**: In failed primary region
3. **Unpause DAGs**: In secondary region
4. **Notification sent**: "Failover Complete" email
5. **Cooldown starts**: 30 minutes before next failover allowed

### Cooldown Period

After failover, the system enters a 30-minute cooldown period:
- Health checks continue running
- Failures are tracked but don't trigger failover
- Prevents rapid back-and-forth failovers (flapping)
- Manual failover still possible if needed

## Notifications

You'll receive email notifications for:

1. **Health Check Warning**: When a health check fails
   - Includes failure count and threshold
   - Sent for each failure

2. **Failover Triggered**: When automated failover starts
   - Includes reason and failure count
   - Sent immediately when threshold reached

3. **Failover Complete**: When failover finishes successfully
   - Includes actions taken and duration
   - Sent after DAGs are paused/unpaused

4. **Failover Failed**: If failover encounters an error
   - Includes error details
   - Requires manual intervention

## Testing

### Test 1: Verify Health Checks

1. Check CloudWatch Logs:
   ```bash
   aws logs tail /aws/lambda/mwaa-openlineage-health-check-dev \
     --follow \
     --region us-east-2
   ```

2. You should see logs every minute showing:
   - Environment status: AVAILABLE
   - Scheduler heartbeat: True
   - Overall health: HEALTHY
   - Consecutive failures: 0/3

### Test 2: Simulate Failure (Optional)

To test automated failover without actually breaking MWAA:

1. Temporarily modify the health check Lambda to always return unhealthy
2. Wait 3 minutes for threshold to be reached
3. Verify failover is triggered
4. Restore original health check code
5. Verify system returns to normal

**Warning**: This will trigger an actual failover to your secondary region!

### Test 3: Manual Failover Still Works

Automated failover doesn't prevent manual failover:

```bash
cd ../disaster-recovery
./scripts/failover_with_dag_control.sh us-east-1 "Manual test"
```

## Monitoring

### CloudWatch Logs

Health check logs:
```bash
aws logs tail /aws/lambda/mwaa-openlineage-health-check-dev --follow --region us-east-2
```

Failover logs:
```bash
aws logs tail /aws/lambda/mwaa-openlineage-automated-failover-dev --follow --region us-east-2
```

### DynamoDB State

Check health state:
```bash
aws dynamodb get-item \
  --table-name mwaa-openlineage-dr-state-dev \
  --key '{"state_id": {"S": "HEALTH_us-east-2"}}' \
  --region us-east-2
```

Check active region:
```bash
aws dynamodb get-item \
  --table-name mwaa-openlineage-dr-state-dev \
  --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
  --region us-east-2
```

### CloudWatch Metrics

Create custom dashboard to monitor:
- Health check invocations
- Health check failures
- Failover invocations
- MWAA scheduler heartbeat

## Disabling Automated Failover

### Temporary Disable

Disable the EventBridge rule:

```bash
aws events disable-rule \
  --name mwaa-openlineage-health-check-dev \
  --region us-east-2
```

Re-enable:

```bash
aws events enable-rule \
  --name mwaa-openlineage-health-check-dev \
  --region us-east-2
```

### Permanent Disable

Delete the stack:

```bash
cdk destroy MwaaAutomatedFailoverStack --region us-east-2
```

Manual failover will still work via the disaster-recovery scripts.

## Cost Considerations

Automated failover adds minimal cost:

- **Lambda invocations**: ~43,200/month (1/minute × 60 × 24 × 30)
  - Health check: ~$0.20/month
  - Failover: ~$0.01/month (only when triggered)
- **CloudWatch Logs**: ~$0.50/month
- **SNS notifications**: ~$0.01/month
- **DynamoDB**: Negligible (few reads/writes)

**Total**: ~$1/month for automated failover

## Troubleshooting

### Health Checks Not Running

1. Check EventBridge rule is enabled:
   ```bash
   aws events describe-rule --name mwaa-openlineage-health-check-dev --region us-east-2
   ```

2. Check Lambda function exists and has correct permissions

3. Check CloudWatch Logs for errors

### False Positive Failures

If health checks fail but MWAA is actually healthy:

1. Check CloudWatch metrics for scheduler heartbeat
2. Verify MWAA environment status in console
3. Adjust FAILURE_THRESHOLD to be more conservative (e.g., 5 instead of 3)
4. Increase HEALTH_CHECK_INTERVAL to reduce sensitivity

### Failover Not Triggering

1. Check consecutive_failures in DynamoDB health state
2. Verify not in cooldown period
3. Check health check Lambda has permission to invoke failover Lambda
4. Check CloudWatch Logs for errors

### Flapping (Rapid Failovers)

If system keeps failing over back and forth:

1. Increase COOLDOWN_MINUTES (e.g., 60 instead of 30)
2. Increase FAILURE_THRESHOLD (e.g., 5 instead of 3)
3. Investigate root cause of instability
4. Consider disabling automated failover until issue resolved

## Best Practices

1. **Test thoroughly**: Test automated failover in non-production first
2. **Monitor closely**: Watch CloudWatch Logs and metrics after deployment
3. **Tune thresholds**: Adjust based on your MWAA stability and requirements
4. **Document runbooks**: Create procedures for handling failover events
5. **Regular drills**: Periodically test failover (manual or automated)
6. **Alert fatigue**: Don't set thresholds too sensitive to avoid alert fatigue

## Limitations

- **Primary region only**: Only monitors primary region health
- **No automatic fallback**: Doesn't automatically fail back to primary when it recovers
- **Single health check**: Only checks MWAA, not downstream dependencies
- **No data replication**: Doesn't handle S3, database, or secrets replication

## Next Steps

1. **Add fallback automation**: Automatically return to primary when healthy
2. **Enhanced health checks**: Check downstream dependencies (databases, S3, etc.)
3. **Custom metrics**: Add application-specific health metrics
4. **Integration testing**: Automated tests after failover
5. **Runbook automation**: Automated remediation steps

## Related Documentation

- `../disaster-recovery/README.md` - Manual DR setup (prerequisite)
- `../disaster-recovery/AIRFLOW3_DR_LIMITATIONS.md` - DR limitations

## Support

For issues:
1. Check CloudWatch Logs for both Lambda functions
2. Verify DynamoDB state table
3. Check SNS topic subscriptions
4. Review MWAA environment status in both regions

## License

This example is provided as-is for demonstration purposes.
