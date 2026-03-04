# DAG Factory Performance Testing - User Guide

Quick guide for running performance tests using DAG Factory with real concurrent tasks.

## Overview

Two test types available:
1. **Concurrent Load Test** - Quick burst test (~2 minutes)
2. **Sustained Load Test** - Long-duration test with gradual ramp-up/down (~40 minutes)

## Prerequisites

- MWAA environment running Airflow 3.0.6+
- `dag-factory==1.0.1` in requirements.txt
- S3 bucket for DAG storage
- AWS CLI configured

## Test 1: Concurrent Load Test

Tests immediate concurrent load capacity.

### Quick Start

```bash
cd mwaa-openlineage-cdk/performance-test

# Generate config (default: 2000 tasks)
python3 generate_dag_factory_config_real.py

# Or specify custom task count
python3 generate_dag_factory_config_real.py --tasks 4000

# Upload to S3
BUCKET="your-mwaa-bucket-name"
REGION="your-region"

aws s3 cp performance_test_tasks_real.py s3://${BUCKET}/dags/ --region ${REGION}
aws s3 cp dag_factory_config_concurrent_real.yaml s3://${BUCKET}/dags/ --region ${REGION}
aws s3 cp dag_factory_concurrent_real.py s3://${BUCKET}/dags/ --region ${REGION}
aws s3 cp trigger_dag_factory_concurrent_real.py s3://${BUCKET}/dags/ --region ${REGION}

# Wait 2-5 minutes for MWAA to parse DAGs
# Then trigger in Airflow UI: trigger_dag_factory_concurrent_real_test
```

**Test Duration:** ~2 minutes

## Test 2: Sustained Load Test

Tests sustained load with gradual ramp-up and ramp-down.

### Quick Start

```bash
cd mwaa-openlineage-cdk/performance-test

# Generate config (default: 2000 peak tasks)
python3 generate_dag_factory_sustained.py

# Or specify custom peak
python3 generate_dag_factory_sustained.py --peak-tasks 4000

# Or customize peak and duration
python3 generate_dag_factory_sustained.py --peak-tasks 3000 --peak-duration 30

# Upload to S3 (use the helper script)
./upload_sustained_test.sh your-mwaa-bucket-name your-region

# Wait 2-5 minutes for MWAA to parse DAGs
# Then trigger in Airflow UI: trigger_dag_factory_sustained_test
```

**Test Pattern (40 minutes):**
- 0-5 min: Ramp up from 500 → peak tasks
- 5-25 min: Sustain peak load (20 minutes)
- 25-40 min: Ramp down peak → 0 tasks

**Test Duration:** ~40 minutes

## Monitoring

**Airflow UI:**
- Check DAG runs and task status
- Review logs for any failures

**CloudWatch:**
- Worker utilization
- Task queue depth
- Task success/failure rates

## Cleanup

```bash
BUCKET="your-bucket-name"
REGION="your-region"

# Remove concurrent test files
aws s3 rm s3://${BUCKET}/dags/dag_factory_concurrent_real.py --region ${REGION}
aws s3 rm s3://${BUCKET}/dags/dag_factory_config_concurrent_real.yaml --region ${REGION}
aws s3 rm s3://${BUCKET}/dags/trigger_dag_factory_concurrent_real.py --region ${REGION}

# Remove sustained test files
aws s3 rm s3://${BUCKET}/dags/dag_factory_sustained.py --region ${REGION}
aws s3 rm s3://${BUCKET}/dags/dag_factory_config_sustained.yaml --region ${REGION}
aws s3 rm s3://${BUCKET}/dags/trigger_dag_factory_sustained.py --region ${REGION}

# Remove shared task functions
aws s3 rm s3://${BUCKET}/dags/performance_test_tasks_real.py --region ${REGION}
```

Wait 2-5 minutes for MWAA to remove the DAGs from the UI.

## Troubleshooting

**DAGs not appearing:**
- Wait 5 minutes for parsing
- Check Airflow logs for parsing errors
- Verify all files are uploaded

**Tasks failing:**
- Check worker capacity
- Review task logs in Airflow UI
- Verify `performance_test_tasks_real.py` is uploaded

**Excessive queuing:**
- Check actual worker count
- Verify worker capacity: workers × 80 tasks/worker
- Consider increasing worker count

## Support

For detailed information, see [README.md](README.md) in the performance-test directory.
