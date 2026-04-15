# Performance Test — Sustained Load with DAG Factory

Generate and run sustained load tests on MWAA using [dag-factory](https://astronomer.github.io/dag-factory/latest/). Each test set creates 65 DAGs with configurable parallel tasks. Multiple sets can run simultaneously to scale concurrent task count.

See also: [Scheduler Capacity Test](scheduler-capacity-test/) — 4000 DAGs with 2 dummy tasks each for scheduler parsing/scheduling capacity testing.

## Prerequisites

- MWAA environment running Airflow 3.0+
- `dag-factory==1.0.0` in your MWAA `requirements.txt`
- S3 bucket versioning enabled (required for MWAA requirements)

## Files

| File | Description |
|------|-------------|
| `generate_dag_factory_sustained.py` | Generator — produces per-DAG YAML configs, per-set loaders, and trigger DAGs |
| `performance_test_tasks_real.py` | Task implementations (`wave_delay_task`, `real_load_task`) |
| `requirements.txt` | Python dependencies for MWAA (`dag-factory`, `pyyaml`) |
| `upload_sustained_test.sh` | Uploads all generated files to your MWAA S3 bucket |

## Generated Files (not checked in)

Running the generator creates these files:

```
configs/
  set_01/                          # Per-DAG YAML configs (~11 KB each)
    factory_sustained_set_01_dag_000.yaml
    ...
    factory_sustained_set_01_dag_064.yaml
  set_02/
    ...
dag_factory_sustained_set_01.py    # Per-set DAG loader (Airflow parses this)
dag_factory_sustained_set_02.py
trigger_dag_factory_sustained_set_01.py  # Master trigger DAG per set
trigger_dag_factory_sustained_set_02.py
```

## How It Works

Each task internally loops: sleeps for `--task-duration` seconds (default 120s), wakes up, and repeats until the wave duration is reached. This keeps YAML configs small (~11 KB per DAG) while sustaining load for the full wave duration.

At any point during the test, each DAG has `tasks_per_dag` parallel tasks running (default: `peak_tasks // 65`). The concurrent task count across all sets:

```
concurrent tasks = (peak_tasks // 65) × 65 × num_sets
```

### Wave Pattern (40 minutes per set)

| Wave | Delay | Task Duration | Description |
|------|-------|---------------|-------------|
| 1 | 0 min | 25 min | Baseline ramp |
| 2 | 2 min | 28 min | 50% ramp |
| 3 | 4 min | 31 min | 75% ramp |
| 4-7 | 5-20 min | 35 min | Sustained peak |

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

# Single set (65 DAGs, 2000 peak tasks)
python generate_dag_factory_sustained.py

# 2 sets for ~3900 concurrent tasks
python generate_dag_factory_sustained.py --sets 2

# 2 sets with 4000+ concurrent (32 tasks/DAG × 65 DAGs × 2 sets = 4160)
python generate_dag_factory_sustained.py --sets 2 --peak-tasks 2080

# Custom task sleep cycle (60s instead of 120s)
python generate_dag_factory_sustained.py --sets 2 --task-duration 60

# Custom peak duration (30 min sustained instead of 20)
python generate_dag_factory_sustained.py --peak-tasks 3000 --peak-duration 30 --sets 2
```

### 2. Upload to S3

```bash
./upload_sustained_test.sh <your-mwaa-bucket> [region]

# Example
./upload_sustained_test.sh my-mwaa-bucket us-east-2
```

This uploads:
- `performance_test_tasks_real.py` — task functions
- `dag_factory_sustained_set_*.py` — per-set DAG loaders
- `configs/` — per-DAG YAML configs
- `trigger_dag_factory_sustained_set_*.py` — master trigger DAGs

### 3. Run the test

1. Wait 2-5 minutes for MWAA to parse the DAGs
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
  --task-duration INT   Sleep cycle per task in seconds (default: 120)
```

## Scaling Examples

| Sets | Peak Tasks/Set | Tasks/DAG | Concurrent Tasks |
|------|----------------|-----------|------------------|
| 1    | 2000           | 30        | ~1950            |
| 2    | 2000           | 30        | ~3900            |
| 2    | 2080           | 32        | ~4160            |
| 3    | 4000           | 61        | ~11895           |
| 5    | 2000           | 30        | ~9750            |
