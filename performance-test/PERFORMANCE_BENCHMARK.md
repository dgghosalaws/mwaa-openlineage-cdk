# MWAA Performance Benchmark Report

## Environment Under Test

| Parameter | Value |
|-----------|-------|
| Airflow Version | 3.0.6 |
| Environment Class | mw1.2xlarge |
| Min Workers | 20 |
| Max Workers | 50 |
| Schedulers | 3 |
| Region | us-east-2 |

### Airflow Configuration Overrides

| Setting | Value | Purpose |
|---------|-------|---------|
| `core.dagbag_import_timeout` | 600s | Large DAG sets with dag-factory |
| `core.default_pool_task_slot_count` | 5000 | No pool bottleneck |
| `core.max_active_tasks_per_dag` | 5000 | No per-DAG throttling |
| `scheduler.task_queued_timeout` | 3600s | Prevent task failures during worker scaling |

## Test Methodology

Tests used [dag-factory](https://astronomer.github.io/dag-factory/latest/) to generate DAGs from YAML configs. Each DAG contains parallel `PythonOperator` tasks that sleep in configurable cycles for a fixed duration. DAGs are organized into waves with staggered delays to create a ramp-up pattern.

### Test Generator

```bash
python generate_dag_factory_sustained.py \
  --sets 1 \
  --peak-tasks 3300 \
  --peak-duration 20 \
  --total-duration 36 \
  --task-duration 900 \
  --dag-duration 20
```

### Test Parameters

| Parameter | Value |
|-----------|-------|
| DAGs | 65 |
| Tasks per DAG | 50 |
| Task sleep cycle | 15 min (900s) |
| DAG run duration | 20 min |
| Total test duration | 36 min |
| Peak concurrent tasks | 3250 (65 × 50) |

### Wave Pattern

| Wave | Delay | DAGs | Cumulative Tasks | Duration |
|------|-------|------|------------------|----------|
| 1 | T+0 | 10 | 500 | 20 min |
| 2 | T+2 | 22 | 1600 | 20 min |
| 3 | T+4 | 16 | 2400 | 20 min |
| 4 | T+5 | 4 | 2600 | 20 min |
| 5 | T+10 | 4 | 2800 | 20 min |
| 6 | T+15 | 4 | 3000 | 20 min |
| 7 | T+20 | 5 | 3250 | 20 min |

## Test Results

### Sustained Load — 2700 Concurrent Tasks (Stable)

Test config: `--peak-tasks 3200 --peak-duration 13 --total-duration 30`

| Metric | Value |
|--------|-------|
| Peak running tasks | 3150 |
| Queued tasks at peak | 0 |
| Workers at peak | 44 |
| Tasks per worker | ~61 |
| Task failures | 0 |
| Duration | 30 min |

All 65 DAGs completed without failures. No queuing observed. Workers scaled from 20 to 44 during ramp-up.

### Sustained Load — 3300 Peak Tasks, 65 DAGs (Report)

Test config: `--peak-tasks 3300 --peak-duration 20 --total-duration 36 --task-duration 900 --dag-duration 20`

```
Execution Soak Test Report - Set 01
============================================================
DAG Runs (65 DAGs):
  failed: 3
  success: 62

Task Instances (3315 total):
  failed: 3
  success: 3312

Failed Tasks (3):
  - factory_sustained_set_01_dag_011: load_task_31 (attempt 1)
  - factory_sustained_set_01_dag_028: load_task_00 (attempt 1)
  - factory_sustained_set_01_dag_058: load_task_25 (attempt 1)

Duration Stats:
  Shortest: 20m 25s
  Longest:  42m 49s
  Average:  32m 0s

Trigger DAG:
  trigger_dag_factory_sustained_test_set_01: success (0m 31s)
```

| Metric | Value |
|--------|-------|
| DAGs | 65 (62 success, 3 failed) |
| Total task instances | 3315 |
| Failed tasks | 3 (0.09%) |
| Trigger DAG duration | 31s |
| Shortest DAG run | 20m 25s |
| Longest DAG run | 42m 49s |
| Average DAG run | 32m 0s |

3 task failures out of 3315 (99.91% success rate). Failures were isolated to single tasks across different DAGs, not systemic worker crashes.

### Sustained Load — 3575 Concurrent Tasks (Failure Threshold)

| Metric | Value |
|--------|-------|
| Peak running tasks | ~3575 |
| Workers at peak | 44-50 |
| Tasks per worker | ~71-81 |
| Task failures | Multiple |
| Failure mode | Executor reported running tasks as failed |

Tasks were actively running on workers, then the Celery executor reported them as failed with `state=running, executor_state=failed`. Failures were staggered across multiple workers (different PIDs), indicating systemic pressure rather than isolated worker issues. Tasks started around T+21:11 and failures occurred between T+21:30 and T+21:39.

### Auto-Scaling Behavior

| Observation | Detail |
|-------------|--------|
| Initial capacity (20 workers) | ~1600 task slots |
| Scaling rate | ~200 slots every 4-5 min |
| Time to 44 workers | ~15 min |
| Time to 50 workers | ~20-25 min |

Auto-scaling adds workers gradually. Tasks exceeding available slots queue in SQS. The `task_queued_timeout=3600` prevents premature failures during scaling.

### DAG Parsing Performance

| Metric | Value |
|--------|-------|
| 65 DAGs (per-DAG YAML, ~11 KB each) | 6-9s parse time |
| dag-factory 1.0.0 | Compatible with Airflow 3.0.6 |
| Per-set loader approach | Avoids 30s default parse timeout |

dag-factory YAMLs with many tasks per DAG can be large. Splitting into one YAML per DAG (~11 KB) keeps parse time under 10s. Per-set loader files ensure each Python file only scans its own directory.

## Recommendations

For an MWAA environment supporting 500 DAGs and 2500 sustained concurrent tasks:

### Environment Sizing

| Setting | Recommended Value |
|---------|-------------------|
| Environment Class | mw1.2xlarge |
| Min Workers | 30 |
| Max Workers | 50 |
| Schedulers | 3 |

### Rationale

- At 80 tasks/worker (85% utilization target): `2500 / 68 ≈ 37` workers needed at peak
- `min_workers=30` pre-provisions capacity for ~2400 tasks, reducing auto-scaling lag
- `max_workers=50` (MWAA limit) provides headroom for burst traffic
- 3 schedulers handle 500 DAG parsing and scheduling throughput
- Stable concurrent task ceiling observed at ~2700 tasks on mw1.2xlarge with 44 workers

### Required Configuration Overrides

```python
airflow_configuration_options={
    "core.dagbag_import_timeout": "600",
    "core.default_pool_task_slot_count": "5000",
    "core.max_active_tasks_per_dag": "5000",
    "scheduler.task_queued_timeout": "3600",
    "core.lazy_load_plugins": "false",
    "core.load_default_connections": "false",
    "core.load_examples": "false",
}
```

| Override | Why |
|----------|-----|
| `dagbag_import_timeout=600` | 500 DAGs with dag-factory needs more than 30s default |
| `default_pool_task_slot_count=5000` | Default pool must accommodate 2500+ tasks |
| `max_active_tasks_per_dag=5000` | Prevent per-DAG task throttling |
| `task_queued_timeout=3600` | Workers take time to scale; tasks should not fail while queued |

### Capacity Planning

| Workers | Tasks/Worker (85%) | Sustained Capacity |
|---------|--------------------|--------------------|
| 30 | 68 | 2040 |
| 37 | 68 | 2516 |
| 44 | 68 | 2992 |
| 50 | 68 | 3400 |

### Key Observations

- MWAA auto-scaling adds ~200 task slots every 4-5 minutes
- Pre-provisioning with higher `min_workers` reduces time-to-capacity
- S3 bucket versioning is required for MWAA requirements.txt
- MWAA Celery broker uses KMS-encrypted SQS; the execution role needs KMS permissions for SQS even without KMS-encrypted S3
- dag-factory 1.0.0 is compatible with Airflow 3.0.6 but `dagrun_timeout` and `execution_timeout` must not use dict format (Airflow 3 requires `timedelta` objects)
