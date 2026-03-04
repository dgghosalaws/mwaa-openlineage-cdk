# MWAA CloudWatch Monitoring

This project includes a CloudWatch monitoring dashboard that provides real-time visibility into MWAA performance and capacity.

## Overview

The monitoring stack is **deployed by default** with MWAA and creates a comprehensive CloudWatch dashboard showing:
- Worker auto-scaling behavior
- Task execution metrics
- Resource utilization (CPU, memory)
- Database connections
- Scheduler performance

## Accessing the Dashboard

### Standard Deployment

**Option 1: Via CloudFormation Outputs**

```bash
# Get dashboard URL
aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-monitoring-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`DashboardUrl`].OutputValue' \
  --output text
```

**Option 2: Via AWS Console**

1. Go to CloudWatch → Dashboards
2. Find dashboard: `mwaa-openlineage-mwaa-performance-dev`
3. Click to open

### Blue-Green Deployment

In blue-green mode, two separate dashboards are created:

**Blue Environment Dashboard:**
```bash
# Get Blue dashboard URL
aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-monitoring-blue-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`DashboardUrl`].OutputValue' \
  --output text
```

**Green Environment Dashboard:**
```bash
# Get Green dashboard URL
aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-monitoring-green-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`DashboardUrl`].OutputValue' \
  --output text
```

**Via AWS Console:**
1. Go to CloudWatch → Dashboards
2. Find dashboards:
   - `mwaa-openlineage-blue-mwaa-performance-dev` (Blue environment)
   - `mwaa-openlineage-green-mwaa-performance-dev` (Green environment)
3. Monitor both to compare performance during switches

## Dashboard Metrics

### Blue-Green Monitoring Strategy

When using blue-green deployment, two separate dashboards are created to monitor each environment independently:

**Benefits:**
- Compare performance between blue and green environments
- Monitor active environment during production traffic
- Validate standby environment before switching
- Detect performance degradation during switches
- Track resource utilization differences

**Best Practices:**
1. Monitor both dashboards side-by-side during switches
2. Verify standby environment metrics before switching
3. Compare task execution times between environments
4. Watch for queue buildup during traffic migration
5. Set up alarms on both environments

**During Zero-Downtime Switch:**
- Active environment: Monitor for graceful task completion
- Standby environment: Watch for traffic ramp-up
- Both: Compare CPU/Memory utilization patterns

### Worker Metrics
- **Worker Count**: Current number of active workers
- **Worker Auto-scaling**: Min/max worker configuration
- **Worker Utilization**: Tasks per worker

### Task Metrics
- **Running Tasks**: Currently executing tasks
- **Queued Tasks**: Tasks waiting for execution
- **Successful Tasks**: Completed successfully
- **Failed Tasks**: Tasks that failed

### Resource Utilization
- **CPU Utilization**: Percentage across all workers
- **Memory Utilization**: Percentage across all workers
- **Database Connections**: Active connections to metadata DB

### Scheduler Metrics
- **Scheduler Heartbeat**: Scheduler health indicator
- **DAG Processing Time**: Time to parse DAGs
- **Task Scheduling Latency**: Time from task ready to running

## Use Cases

### 1. Performance Testing
Monitor worker scaling during load tests:
- Watch worker count increase with load
- Verify tasks don't queue unnecessarily
- Check CPU/memory stay below 90%

See [PERFORMANCE_TESTING.md](PERFORMANCE_TESTING.md) for details.

### 2. Capacity Planning
Determine optimal worker configuration:
- Observe peak worker usage
- Identify bottlenecks (CPU, memory, database)
- Right-size environment class

### 3. Troubleshooting
Diagnose performance issues:
- High queued tasks → Need more workers or pool slots
- High CPU → Need larger environment class
- High database connections → Check DAG complexity

### 4. Cost Optimization
Monitor resource usage to reduce costs:
- Identify over-provisioned workers
- Optimize min/max worker settings
- Adjust environment class if underutilized

## Metrics Reference

| Metric | Namespace | Description |
|--------|-----------|-------------|
| QueuedTasks | AmazonMWAA | Tasks waiting for execution |
| RunningTasks | AmazonMWAA | Currently executing tasks |
| WorkerCount | AmazonMWAA | Number of active workers |
| CPUUtilization | AmazonMWAA | CPU usage percentage |
| MemoryUtilization | AmazonMWAA | Memory usage percentage |
| DatabaseConnections | AmazonMWAA | Active DB connections |
| SchedulerHeartbeat | AmazonMWAA | Scheduler health (1=healthy) |

## Alarms (Optional)

You can create CloudWatch alarms based on dashboard metrics:

### High CPU Alarm
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name mwaa-high-cpu \
  --alarm-description "MWAA CPU above 90%" \
  --metric-name CPUUtilization \
  --namespace AmazonMWAA \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 90 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=Environment,Value=mwaa-openlineage-dev
```

### High Queued Tasks Alarm
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name mwaa-high-queue \
  --alarm-description "MWAA queued tasks above 100" \
  --metric-name QueuedTasks \
  --namespace AmazonMWAA \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 100 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=Environment,Value=mwaa-openlineage-dev
```

## Disabling Monitoring

Monitoring is enabled by default. To disable:

```json
// In cdk.json
{
  "context": {
    "enable_monitoring": false
  }
}
```

Then redeploy:
```bash
cdk deploy --all
```

**Note**: Disabling monitoring is not recommended, especially for performance testing or production environments.

## Custom Metrics

You can add custom metrics to the dashboard by modifying `stacks/mwaa_monitoring_stack.py`:

```python
# Add custom metric widget
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title="Custom Metric",
        left=[
            cloudwatch.Metric(
                namespace="AmazonMWAA",
                metric_name="YourMetric",
                dimensions_map={
                    "Environment": mwaa_environment_name
                },
                statistic="Average",
                period=Duration.minutes(5)
            )
        ]
    )
)
```

## Troubleshooting

### Dashboard Not Appearing

1. Verify monitoring stack deployed:
   ```bash
   aws cloudformation describe-stacks \
     --stack-name mwaa-openlineage-monitoring-dev
   ```

2. Check if monitoring is enabled in cdk.json:
   ```json
   "enable_monitoring": true
   ```

3. Redeploy if needed:
   ```bash
   cdk deploy mwaa-openlineage-monitoring-dev
   ```

### No Metrics Showing

1. Wait 5-10 minutes after MWAA deployment
2. Trigger a DAG to generate metrics
3. Check MWAA environment is AVAILABLE
4. Verify environment name matches dashboard configuration

### Metrics Delayed

CloudWatch metrics have a 1-5 minute delay. This is normal. For real-time monitoring, use Airflow UI.

## Additional Resources

- [MWAA CloudWatch Metrics](https://docs.aws.amazon.com/mwaa/latest/userguide/access-metrics-cw-console.html)
- [CloudWatch Dashboards](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Dashboards.html)
- [Performance Testing Guide](PERFORMANCE_TESTING.md)
