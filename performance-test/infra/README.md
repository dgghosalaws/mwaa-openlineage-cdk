# Performance Test Infrastructure

Standalone CDK app that deploys a VPC + MWAA environment for performance testing. No Marquez or OpenLineage — just the cluster.

## What It Creates

- VPC with 2 AZs, public/private subnets, NAT gateway
- KMS-encrypted S3 bucket for DAGs and requirements
- MWAA environment (Airflow 3.0.6) with performance-tuned config

## Default Configuration

| Setting | Value |
|---------|-------|
| Environment class | mw1.2xlarge |
| Schedulers | 3 |
| Min workers | 20 |
| Max workers | 50 |
| DAG import timeout | 600s |
| Default pool slots | 5000 |
| Max active tasks/DAG | 5000 |
| Task queued timeout | 1800s |

## Deploy

```bash
cd performance-test/infra
cdk deploy --all
```

## Customize

Override via context:

```bash
cdk deploy --all \
  -c env_name=my-perf-test \
  -c region=us-west-2 \
  -c environment_class=mw1.xlarge \
  -c min_workers=10 \
  -c max_workers=25
```

## Destroy

```bash
cdk destroy --all
```
