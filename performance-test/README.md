# Performance Test — Sustained Load with DAG Factory

Generate and run sustained load tests on MWAA using [dag-factory](https://github.com/ajbosco/dag-factory). Each test set creates 65 DAGs with configurable tasks per DAG. Multiple sets can run in parallel to scale concurrent task count.

## Files

| File | Description |
|------|-------------|
| `generate_dag_factory_sustained.py` | Generator — produces YAML configs and master trigger DAGs |
| `dag_factory_sustained.py` | YAML loader — Airflow picks this up and creates DAGs from all set configs |
| `performance_test_tasks_real.py` | Task implementations (`wave_delay_task`, `real_load_task`) |
| `upload_sustained_test.sh` | Uploads generated files to your MWAA S3 bucket |

## How It Works

Each set generates:
- 65 DAGs (`factory_sustained_set_NN_dag_000` through `_064`)
- 1 master trigger DAG (`trigger_dag_factory_sustained_test_set_NN`)
- 1 YAML config file (`dag_factory_config_sustained_set_NN.yaml`)

### Batched Task Execution

Instead of long-running tasks that sleep for the entire wave duration, each DAG uses sequential batches of short-lived parallel tasks to sustain load.

```
wave_delay → [batch 0: 30 tasks @ 120s] → sync → [batch 1: 30 tasks @ 120s] → sync → ...
```

- Each batch runs `tasks_per_dag` tasks in parallel (default: `peak_tasks // 65`)
- Each task sleeps for `--task-duration` seconds (default: 120s)
- Batches are chained sequentially via sync tasks
- Number of batches = `wave_duration / task_duration` (auto-calculated per wave)

This means at any point in time, each DAG has one active batch of parallel tasks. The concurrent task count across all DAGs and sets is:

```
concurrent tasks = (peak_tasks // 65) × 65 × num_sets
```

### Wave Pattern

The test follows a 40-minute wave pattern per set:

| Wave | Delay | Duration | Batches (@ 120s) | Description |
|------|-------|----------|-------------------|-------------|
| 1 | 0 min | 25 min | 13 | Baseline ramp |
| 2 | 2 min | 28 min | 14 | 50% ramp |
| 3 | 4 min | 31 min | 16 | 75% ramp |
| 4-7 | 5-20 min | 35 min | 18 | Sustained peak |

```
Time     Load
0-5m     Ramp up (500 → peak)
5-25m    Sustained peak
25-40m   Ramp down (peak → 0)
```

## Quick Start

### 1. Generate configs

```bash
cd performance-test

# Single set (65 DAGs, 2000 peak tasks, 120s task duration)
python generate_dag_factory_sustained.py

# 2 sets for ~4000 concurrent tasks
python generate_dag_factory_sustained.py --sets 2 --peak-tasks 2000

# 2 sets with exact 4000+ concurrent (32 tasks/batch × 65 DAGs × 2 sets = 4160)
python generate_dag_factory_sustained.py --sets 2 --peak-tasks 2080

# Custom task duration (60s instead of 120s)
python generate_dag_factory_sustained.py --sets 2 --task-duration 60

# 3 sets with 4000 peak tasks each
python generate_dag_factory_sustained.py --peak-tasks 4000 --sets 3

# Custom peak duration (30 min instead of default 20)
python generate_dag_factory_sustained.py --peak-tasks 3000 --peak-duration 30 --sets 2
```

This creates per-set files:
- `dag_factory_config_sustained_set_01.yaml`, `..._set_02.yaml`, etc.
- `trigger_dag_factory_sustained_set_01.py`, `..._set_02.py`, etc.

### 2. Upload to S3

```bash
./upload_sustained_test.sh <your-mwaa-bucket> [region]

# Example
./upload_sustained_test.sh my-mwaa-bucket us-east-2
```

### 3. Run the test

1. Wait 2–5 minutes for MWAA to parse the DAGs
2. In the Airflow UI, find the master trigger DAGs (tag: `master-trigger`)
3. Trigger all sets simultaneously for maximum parallel load
4. Monitor CloudWatch for ~40 minutes

## CLI Reference

```
python generate_dag_factory_sustained.py [OPTIONS]

Options:
  --peak-tasks INT      Peak concurrent tasks per set (default: 2000)
  --peak-duration INT   Minutes to sustain peak load (default: 20)
  --sets INT            Number of sets of 65 DAGs (default: 1)
  --task-duration INT   Duration of each task in seconds (default: 120)
```

## Scaling Examples

| Sets | Peak Tasks/Set | Tasks/Batch | Concurrent Tasks | Task Duration |
|------|----------------|-------------|------------------|---------------|
| 1    | 2000           | 30          | ~1950            | 120s          |
| 2    | 2000           | 30          | ~3900            | 120s          |
| 2    | 2080           | 32          | ~4160            | 120s          |
| 3    | 4000           | 61          | ~11895           | 120s          |
| 5    | 2000           | 30          | ~9750            | 120s          |
