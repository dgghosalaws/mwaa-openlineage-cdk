# Scheduler Capacity Test — 4000 DAGs with DAG Factory

Tests MWAA scheduler parsing capacity by loading a large number of DAGs and verifying they appear in the Airflow UI. The goal is to confirm the scheduler can parse and register N DAGs without errors or timeouts.

## What It Does

Generates N DAGs (default 4000), each with 2 chained dummy tasks (`task_a → task_b`). DAGs are split across multiple loader files (400 DAGs per loader) to stay under Airflow's DAG parse timeout. Each per-DAG YAML is ~900 bytes.

## Prerequisites

- MWAA environment running Airflow 3.0+
- `dag-factory==1.0.0` in your MWAA `requirements.txt`

## Quick Start

### 1. Generate

```bash
cd performance-test/scheduler-capacity-test

# Default: 4000 DAGs
python generate_dag_factory_throughput.py

# Custom count
python generate_dag_factory_throughput.py --dags 2000
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

### 3. Verify

1. Wait 2-5 minutes for MWAA to parse
2. Check Airflow UI for 4000 DAGs (tag: `throughput-test`)
3. All DAGs should appear without import errors

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
