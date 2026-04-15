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

The test follows a 40-minute wave pattern per set:

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

# 2 sets (130 DAGs, 2000 peak tasks per set, 4000 total)
python generate_dag_factory_sustained.py --sets 2

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
  --peak-tasks INT     Peak concurrent tasks per set (default: 2000)
  --peak-duration INT  Minutes to sustain peak load (default: 20)
  --sets INT           Number of sets of 65 DAGs (default: 1)
```

## Scaling Examples

| Sets | DAGs | Peak Tasks/Set | Total Peak Tasks |
|------|------|----------------|------------------|
| 1    | 65   | 2000           | 2000             |
| 2    | 130  | 2000           | 4000             |
| 3    | 195  | 4000           | 12000            |
| 5    | 325  | 2000           | 10000            |
