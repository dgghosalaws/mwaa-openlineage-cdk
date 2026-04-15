# Scheduler Capacity Test — 4000 DAGs with DAG Factory

Tests MWAA scheduler parsing and scheduling capacity by generating a large number of minimal DAGs.

## What It Does

Generates N DAGs (default 4000), each with 2 chained dummy tasks (`task_a → task_b`). Tasks sleep for a configurable duration (default 30s). DAGs are split across multiple loader files (400 DAGs per loader) to stay under Airflow's DAG parse timeout.

## Prerequisites

- MWAA environment running Airflow 3.0+
- `dag-factory==1.0.0` in your MWAA `requirements.txt`

## Quick Start

### 1. Generate

```bash
cd performance-test/throughput-test

# Default: 4000 DAGs, 30s task duration
python generate_dag_factory_throughput.py

# Custom count
python generate_dag_factory_throughput.py --dags 2000

# Custom task duration
python generate_dag_factory_throughput.py --dags 4000 --task-duration 60
```

Generated files:
- `throughput_configs/loader_NN/` — per-DAG YAML configs (~900 bytes each)
- `throughput_loader_NN.py` — per-loader DAG factory files
- `throughput_tasks.py` — dummy task function
- `trigger_throughput_test.py` — master trigger DAG

### 2. Upload

```bash
./upload_throughput_test.sh <your-mwaa-bucket> [region]
```

### 3. Run

1. Wait 2-5 minutes for MWAA to parse
2. Find `trigger_throughput_test` in Airflow UI (tag: `master-trigger`)
3. Trigger it — all 4000 DAGs fire simultaneously

## CLI Reference

```
python generate_dag_factory_throughput.py [OPTIONS]

Options:
  --dags INT            Total number of DAGs (default: 4000)
  --task-duration INT   Sleep duration per task in seconds (default: 30)
```

## Files

| File | Description |
|------|-------------|
| `generate_dag_factory_throughput.py` | Generator |
| `upload_throughput_test.sh` | S3 upload script |
| `requirements.txt` | Shared with sustained test (dag-factory, pyyaml) |
