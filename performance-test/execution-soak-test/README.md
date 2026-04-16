# Execution Soak Test — Sustained Load with DAG Factory

Generates and runs sustained load tests on MWAA using [dag-factory](https://astronomer.github.io/dag-factory/latest/). Each test set creates 65 DAGs with configurable parallel tasks. Multiple sets can run simultaneously to scale concurrent task count.

## Prerequisites

- MWAA environment running Airflow 3.0+
- `dag-factory==1.0.0` in your MWAA `requirements.txt`
- S3 bucket versioning enabled (required for MWAA requirements)

## Files

| File | Description |
|------|-------------|
| `generate_dag_factory_sustained.py` | Generator — produces per-DAG YAML configs, per-set loaders, and trigger DAGs |
| `performance_test_tasks_real.py` | Task implementations (`wave_delay_task`, `real_load_task`) |
| `soak_test_report_dag.py` | Report DAG — trigger after test for execution summary |
| `upload_sustained_test.sh` | Uploads all generated files to your MWAA S3 bucket |

## Generated Files (not checked in)

```
configs/
  set_01/                          # Per-DAG YAML configs (~11 KB each)
    factory_sustained_set_01_dag_000.yaml
    ...
    factory_sustained_set_01_dag_064.yaml
dag_factory_sustained_set_01.py    # Per-set DAG loader
trigger_dag_factory_sustained_set_01.py  # Master trigger DAG per set
```

## How It Works

Each task internally loops: sleeps for `--task-duration` seconds (default 120s), wakes up, and repeats until the wave duration is reached. This keeps YAML configs small (~11 KB per DAG) while sustaining load for the full wave duration.

Concurrent task count across all sets:

```
concurrent tasks = (peak_tasks // 65) × 65 × num_sets
```

### Wave Pattern

The test has 3 phases: ramp-up (5 min fixed), sustained peak (`--peak-duration`), and ramp-down (remainder of `--total-duration`). Wave task durations scale automatically based on total duration.

```
Time              Load
0 to 5m           Ramp up (500 → peak)
5m to 5+peak      Sustained peak
5+peak to total   Ramp down (peak → 0)
```

## Quick Start

### 1. Generate configs

```bash
cd performance-test/execution-soak-test

# 3200 peak tasks, 20-min DAG runs, 15-min sleep cycles, 36-min total
python generate_dag_factory_sustained.py --sets 1 --peak-tasks 3200 --peak-duration 20 --total-duration 36 --task-duration 900 --dag-duration 20

# 3600 peak tasks, 20-min peak, 30-min total (wave-calculated DAG durations)
python generate_dag_factory_sustained.py --sets 1 --peak-tasks 3600 --peak-duration 20 --total-duration 30

# Default: 40-min test, 2000 peak tasks, 20-min peak
python generate_dag_factory_sustained.py

# 2 sets for ~3900 concurrent tasks
python generate_dag_factory_sustained.py --sets 2

# 60-min test with 30-min peak
python generate_dag_factory_sustained.py --total-duration 60 --peak-duration 30

# Custom task sleep cycle (60s instead of 120s)
python generate_dag_factory_sustained.py --sets 2 --task-duration 60
```

### 2. Upload to S3

```bash
./upload_sustained_test.sh <your-mwaa-bucket> [region]

# Example
./upload_sustained_test.sh perf-test-834811675783 us-east-2
```

### 3. Run the test

1. Wait 2-5 minutes for MWAA to parse the DAGs
2. In the Airflow UI, find the master trigger DAG (tag: `master-trigger`)
3. Trigger it to start all 65 DAGs
4. Monitor CloudWatch dashboard

### 4. Report

After the test completes, trigger `soak_test_report` with config:

```json
{"num_dags": 80}
```

Check the task log for DAG run states, failed tasks, and duration stats.

## CLI Reference

```
python generate_dag_factory_sustained.py [OPTIONS]

Options:
  --peak-tasks INT       Peak concurrent tasks per set (default: 2000)
  --peak-duration INT    Minutes to sustain peak load (default: 20)
  --total-duration INT   Total test duration in minutes (default: 40)
  --sets INT             Number of sets of 65 DAGs (default: 1)
  --task-duration INT    Sleep cycle per task in seconds (default: 120)
  --dag-duration INT     Fixed DAG run duration in minutes, overrides wave
                         durations (default: 0 = use wave-calculated durations)
```

## Scaling Examples

| Sets | Peak Tasks/Set | Tasks/DAG | Concurrent Tasks | Total Duration | DAG Duration |
|------|----------------|-----------|------------------|----------------|--------------|
| 1    | 3200           | 49        | ~3185            | 36 min         | 20 min fixed |
| 1    | 3600           | 55        | ~3575            | 30 min         | wave-calc    |
| 1    | 2000           | 30        | ~1950            | 40 min         | wave-calc    |
| 2    | 2000           | 30        | ~3900            | 40 min         | wave-calc    |
| 2    | 2080           | 32        | ~4160            | 40 min         | wave-calc    |
