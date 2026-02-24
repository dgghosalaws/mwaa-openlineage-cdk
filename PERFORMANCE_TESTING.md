# MWAA Performance Testing Guide

This guide explains how to test MWAA capacity and auto-scaling behavior using the included performance test DAGs.

## Overview

The performance test framework includes multiple test scenarios to validate MWAA capacity and auto-scaling:

1. **Gradual Load Test** - Quick capacity validation (4.5 minutes)
2. **5K Load Test** - Extreme capacity testing (4.5 minutes)
3. **Sustained Load Test** - Long-duration stability testing (55 minutes)

All tests simulate realistic production workloads by distributing tasks across multiple DAGs. This approach:
- Bypasses per-DAG task limits
- Tests worker auto-scaling behavior
- Validates pool configuration
- Measures system capacity under load
- Tests sustained performance over time

## Available Test Scenarios

### 1. Gradual Load Test (Standard)

**Purpose:** Quick capacity validation and worker auto-scaling verification

**Configuration:**
- 100 DAGs × 70 tasks = 7,000 tasks at peak
- Task duration: 2 minutes
- Total test duration: ~4.5 minutes
- 5 waves with 30-second intervals

**Wave Pattern:**
```
Wave 1: 25 DAGs  = 1,750 tasks   (baseline)
Wave 2: 38 DAGs  = 2,660 tasks   (52% increase)
Wave 3: 50 DAGs  = 3,500 tasks   (100% increase)
Wave 4: 75 DAGs  = 5,250 tasks   (200% increase)
Wave 5: 100 DAGs = 7,000 tasks   (300% increase - peak)
```

**Use Case:** Initial capacity testing, quick validation after configuration changes

### 2. 5K Load Test (Extreme Capacity)

**Purpose:** Test extreme load with intentional queuing

**Configuration:**
- 200 DAGs × 25 tasks = 5,000 tasks at peak
- Task duration: 2 minutes
- Total test duration: ~4.5 minutes
- Target: 4,000 running + 1,000 queued

**Wave Pattern:**
```
Wave 1: 50 DAGs  = 1,250 tasks
Wave 2: 75 DAGs  = 1,875 tasks
Wave 3: 100 DAGs = 2,500 tasks
Wave 4: 150 DAGs = 3,750 tasks
Wave 5: 200 DAGs = 5,000 tasks (PEAK)
```

**Use Case:** Validate queue management, test worker capacity limits

### 3. Sustained Load Test (Long Duration)

**Purpose:** Test stability and performance degradation over extended periods

**Configuration:**
- 100 DAGs × 70 tasks = 7,000 tasks at peak
- Task duration: 20 minutes
- Total test duration: ~55 minutes
- Peak load sustained: 20 minutes

**Wave Pattern:**
```
T+0:00  → Wave 1: 1,400 tasks (ramp up)
T+5:00  → Wave 2: 2,800 tasks (50% to peak)
T+10:00 → Wave 3: 4,200 tasks (75% to peak)
T+15:00 → Wave 4: 5,600 tasks (approaching peak)
T+20:00 → Wave 5: 7,000 tasks (PEAK BEGINS)
T+25:00 → Wave 6: 7,000 tasks (PEAK SUSTAINED)
T+40:00 → Peak ends, gradual ramp down
T+55:00 → Test completes
```

**Peak Period:** 20 minutes of sustained 7,000 tasks (T+20 to T+40)

**Use Case:** 
- Validate long-running task stability
- Test for memory leaks or resource degradation
- Verify sustained high-load performance
- Monitor database connection pool over time

## Test Architecture

## Prerequisites

### 1. Pool Configuration

MWAA's default pool must be configured for high concurrency:

```python
# In mwaa_stack.py airflow_configuration_options:
"core.default_pool_task_slot_count": "2000",
"core.max_active_tasks_per_dag": "2000",
```

**Important:** These settings only apply to NEW pools. For existing environments, you must manually update the pool via Airflow UI:

1. Go to Airflow UI → Admin → Pools
2. Edit `default_pool`
3. Set slots based on your test criteria:
   - For 7000 task gradual test: Set to `7000` or `8000`
   - For 5000 task test: Set to `5000` (expect 4000 running + 1000 queued)
   - For sustained load test: Set to `7000` or `8000`
   - General rule: Set pool size ≥ expected peak tasks
4. Save

**Note:** Actual concurrent running tasks are limited by worker capacity (workers × 80 tasks/worker), not pool size. Pool size determines how many tasks can be scheduled before queuing.

Alternatively, use the included `fix_pool_slots.py` DAG (in `performance-test/` directory) to update pool slots programmatically.

### 2. Worker Configuration

Recommended MWAA environment settings for testing:
- Environment class: `mw1.2xlarge` or larger
- Min workers: 15
- Max workers: 25
- Schedulers: 2 (AWS default)

Expected capacity: ~80 tasks per worker = 2000 tasks with 25 workers

### 3. Monitoring Stack (Optional)

The monitoring stack is deployed by default with MWAA stack. It creates a CloudWatch dashboard showing:
- Worker count and auto-scaling behavior
- Running and queued tasks
- CPU and memory utilization
- Database connections
- Scheduler performance

Access the dashboard:
```bash
# Get dashboard URL
aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-monitoring-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`DashboardUrl`].OutputValue' \
  --output text
```

Or navigate in AWS Console: CloudWatch → Dashboards → `MWAA-{your-environment-name}`

To disable monitoring (not recommended for performance testing):
```json
// In cdk.json
"enable_monitoring": false
```

## Deployment

### Option 1: Deploy with MWAA (Recommended)

Performance test DAGs are included in `assets/dags/performance-test/`:

```bash
# Deploy MWAA stack - includes performance tests
cdk deploy MwaaOpenlineageStack
```

The DAGs will be automatically uploaded to S3 and available in Airflow UI.

### Option 2: Manual Upload

Upload test DAGs manually:

```bash
# Get your S3 bucket name
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name MwaaOpenlineageStack \
  --query 'Stacks[0].Outputs[?OutputKey==`MwaaBucketName`].OutputValue' \
  --output text)

# Upload performance tests
aws s3 cp mwaa-openlineage-cdk/performance-test/test_distributed_gradual_load.py \
  s3://$BUCKET/dags/

aws s3 cp mwaa-openlineage-cdk/performance-test/trigger_master_dag.py \
  s3://$BUCKET/dags/

# Upload 5K load test (optional)
aws s3 cp mwaa-openlineage-cdk/performance-test/test_distributed_5k_load.py \
  s3://$BUCKET/dags/

aws s3 cp mwaa-openlineage-cdk/performance-test/trigger_5k_test.py \
  s3://$BUCKET/dags/

# Upload sustained load test (optional)
aws s3 cp mwaa-openlineage-cdk/performance-test/test_sustained_load.py \
  s3://$BUCKET/dags/

aws s3 cp mwaa-openlineage-cdk/performance-test/trigger_sustained_load.py \
  s3://$BUCKET/dags/
```

## Running the Tests

### Choosing a Test

**Gradual Load Test** - Use for quick capacity validation
- Filter by tag: `capacity-test` or `distributed-gradual`
- Master trigger: `trigger_performance_test`
- Duration: ~4.5 minutes

**5K Load Test** - Use for extreme capacity testing
- Filter by tag: `capacity-test-5k` or `distributed-5k`
- Master trigger: `trigger_5k_performance_test`
- Duration: ~4.5 minutes

**Sustained Load Test** - Use for long-duration stability testing
- Filter by tag: `sustained-load` or `long-duration`
- Master trigger: `trigger_sustained_load_test`
- Duration: ~55 minutes

### Step 1: Verify DAGs Appear

Wait 1-2 minutes for Airflow to parse the DAGs. 

**For Gradual Load Test:**
- 100 test DAGs: `perf_test_wave1_000` through `perf_test_wave5_099`
- 1 master DAG: `trigger_performance_test`

**For 5K Load Test:**
- 200 test DAGs: `perf_5k_wave1_000` through `perf_5k_wave5_199`
- 1 master DAG: `trigger_5k_performance_test`

**For Sustained Load Test:**
- 120 test DAGs: `sustained_load_wave1_000` through `sustained_load_wave6_099`
- 1 master DAG: `trigger_sustained_load_test`

### Step 2: Trigger the Test

**Option A: Using Master DAG (Easiest)**
1. Open Airflow UI
2. Filter by tag: `master-trigger`
3. Click on `trigger_performance_test`
4. Click "Trigger DAG" button
5. Master DAG will trigger all 100 test DAGs automatically

**Option B: Using AWS CLI**
```bash
# Get MWAA environment name
ENV_NAME=$(aws cloudformation describe-stacks \
  --stack-name MwaaOpenlineageStack \
  --query 'Stacks[0].Outputs[?OutputKey==`MwaaEnvironmentName`].OutputValue' \
  --output text)

# Trigger master DAG
aws mwaa create-cli-token --name $ENV_NAME | \
  jq -r '.CliToken' | \
  xargs -I {} curl -X POST \
  "https://$ENV_NAME.airflow.{region}.amazonaws.com/api/v1/dags/trigger_performance_test/dagRuns" \
  -H "Authorization: Bearer {}"
```

### Step 3: Monitor the Test

**Timeline (4.5 minutes total):**
```
T+0:00  → Trigger master DAG
T+0:30  → Wave 1 starts (650 tasks)
T+1:00  → Wave 2 starts (988 tasks)
T+1:30  → Wave 3 starts (1300 tasks)
T+2:00  → Wave 4 starts (1950 tasks)
T+2:30  → Wave 5 starts (2600 tasks) ← PEAK LOAD
T+4:30  → Test completes
```

**What to Monitor:**

1. **Airflow UI - Admin → Pools**
   - Watch `default_pool` slots fill up
   - At peak: should show ~2000/2000 used
   - Queued slots: ~600 (if pool is full)

2. **CloudWatch Dashboard** (automatically deployed)
   - Worker count: Should scale from ~8 to 25
   - Running tasks: Should increase with each wave
   - Queued tasks: Should stay low until pool is full
   - CPU/Memory: Should stay below 90%
   - Access via CloudWatch console or stack outputs

3. **Airflow UI - DAGs**
   - Filter by wave tags: `wave-1`, `wave-2`, etc.
   - Check task status across DAGs
   - Look for failed or stuck tasks

## Success Criteria

### Test Passes If:
- ✅ All 100 test DAGs complete successfully
- ✅ Workers scale smoothly (8 → 25)
- ✅ Pool slots reach ~2000 at peak
- ✅ CPU utilization stays below 90%
- ✅ Memory utilization stays below 90%
- ✅ No scheduler errors in logs
- ✅ Waves start at expected times (±30 seconds)

### Test Fails If:
- ❌ Any DAG fails
- ❌ Workers don't scale to 25
- ❌ Tasks stuck in queued state (beyond pool limit)
- ❌ CPU/Memory exceeds 95%
- ❌ Scheduler crashes or restarts

## Troubleshooting

### Issue: Tasks Stuck in Queued State

**Symptom:** Tasks remain queued even though pool has open slots

**Causes:**
1. Pool slots not configured correctly
2. Workers not scaling up
3. Scheduler overloaded

**Solutions:**
1. Check pool configuration:
   ```bash
   # Upload and trigger diagnostic DAG
   aws s3 cp mwaa-openlineage-cdk/performance-test/check_pool_status.py \
     s3://$BUCKET/dags/
   
   # Trigger in Airflow UI, check logs
   ```

2. Verify worker scaling:
   - Check CloudWatch metrics for worker count
   - Ensure max_workers is set high enough (25+)

3. Check scheduler logs for errors

### Issue: DAGs Not Auto-Enabled

**Symptom:** DAGs appear but are paused

**Cause:** `is_paused_upon_creation=False` only works for brand new DAG IDs

**Solution:**
1. Delete DAG files from S3
2. Wait 2 minutes for Airflow to detect deletion
3. Re-upload DAG files
4. DAGs should appear enabled

Or manually enable via UI:
1. Select all DAGs (filter by `capacity-test` tag)
2. Click "Enable" button

### Issue: Pool Shows Wrong Slot Count

**Symptom:** Pool shows 128 or 500 slots instead of 2000

**Cause:** Configuration didn't update existing pool

**Solution:**
Use the fix_pool_slots.py DAG:
```bash
aws s3 cp mwaa-openlineage-cdk/performance-test/fix_pool_slots.py \
  s3://$BUCKET/dags/

# Trigger in Airflow UI, verify in logs
```

Or manually update via UI:
1. Admin → Pools
2. Edit `default_pool`
3. Set slots to 2000
4. Save

## Cleanup

### Remove Test DAGs

**Option 1: Delete from S3**
```bash
aws s3 rm s3://$BUCKET/dags/performance-test/ --recursive
```

**Option 2: Keep for Future Testing**
Leave the DAGs in place. They won't run unless manually triggered.

### Reset Pool Configuration

If you want to return to default pool settings:
1. Admin → Pools
2. Edit `default_pool`
3. Set slots back to original value (usually 128)
4. Save

## Customizing the Test

### Adjust Task Count

Edit `test_distributed_gradual_load.py`:

```python
# Increase/decrease tasks per DAG
TASKS_PER_DAG = 26  # Change this value

# Adjust task duration
TASK_DURATION = 120  # seconds
```

### Adjust Wave Timing

Edit wave delays in `WAVE_CONFIG`:

```python
WAVE_CONFIG = [
    {'wave': 1, 'dag_start': 0,   'dag_end': 25,  'delay': 30},   # Change delay
    {'wave': 2, 'dag_start': 25,  'dag_end': 38,  'delay': 60},   # Change delay
    # ...
]
```

### Change Number of DAGs

```python
NUM_DAGS = 100  # Increase/decrease total DAGs
```

**Note:** If you change NUM_DAGS, you must also update:
1. Wave boundaries in `WAVE_CONFIG`
2. Master trigger DAG loop range
3. Documentation

## Performance Benchmarks

### Expected Results (mw1.2xlarge, 15-25 workers)

| Metric | Expected Value |
|--------|---------------|
| Peak concurrent tasks | ~2000 (limited by pool) |
| Worker count at peak | 25 |
| Pool utilization | 100% (2000/2000) |
| Queued tasks at peak | ~600 |
| CPU utilization | 70-85% |
| Memory utilization | 60-75% |
| Test duration | 4.5 minutes |
| Success rate | 100% |

### Scaling Behavior

| Time | Wave | Tasks | Workers | Pool Usage |
|------|------|-------|---------|------------|
| T+0:30 | 1 | 650 | 8 | 33% |
| T+1:00 | 2 | 988 | 12 | 49% |
| T+1:30 | 3 | 1300 | 16 | 65% |
| T+2:00 | 4 | 1950 | 24 | 98% |
| T+2:30 | 5 | 2600 | 25 | 100% |

## Additional Resources

- [MWAA Performance Best Practices](https://docs.aws.amazon.com/mwaa/latest/userguide/best-practices-performance.html)
- [Airflow Pool Documentation](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/pools.html)
- [MWAA Auto-scaling](https://docs.aws.amazon.com/mwaa/latest/userguide/mwaa-autoscaling.html)

## Support

For issues or questions:
1. Check CloudWatch logs for errors
2. Review Airflow scheduler/worker logs
3. Verify pool and worker configuration
4. Check AWS service quotas for MWAA
