# MWAA Disaster Recovery Example

Deploys a multi-region MWAA setup across two AWS regions. This is the foundational
infrastructure for disaster recovery — deploy this first, then layer on the
[metadb-backup-restore](../metadb-backup-restore/) example for metadata backup/restore
and automated failover orchestration.

## What This Example Provides

- VPC, subnets, and security groups in both regions
- S3 buckets for MWAA assets (DAGs) in both regions
- Two MWAA environments (primary + secondary) running Airflow 3.0.6

## Architecture

```
┌──────────────────────────────┐     ┌──────────────────────────────┐
│    Primary Region (us-east-2) │     │  Secondary Region (us-east-1) │
│                              │     │                              │
│  ┌────────────────────────┐  │     │  ┌────────────────────────┐  │
│  │ VPC                    │  │     │  │ VPC                    │  │
│  │  Private Subnets       │  │     │  │  Private Subnets       │  │
│  │  Security Groups       │  │     │  │  Security Groups       │  │
│  └────────────────────────┘  │     │  └────────────────────────┘  │
│                              │     │                              │
│  ┌────────────────────────┐  │     │  ┌────────────────────────┐  │
│  │ S3 Bucket              │  │     │  │ S3 Bucket              │  │
│  │  dags/                 │  │     │  │  dags/                 │  │
│  └────────────────────────┘  │     │  └────────────────────────┘  │
│                              │     │                              │
│  ┌────────────────────────┐  │     │  ┌────────────────────────┐  │
│  │ MWAA Environment       │  │     │  │ MWAA Environment       │  │
│  │  mw1.small, 1-2 workers│  │     │  │  mw1.small, 1-2 workers│  │
│  │  Airflow 3.0.6         │  │     │  │  Airflow 3.0.6         │  │
│  └────────────────────────┘  │     │  └────────────────────────┘  │
└──────────────────────────────┘     └──────────────────────────────┘
```

## Components

### CDK Stacks

| Stack | Region | Description |
|-------|--------|-------------|
| `MwaaDRNetworkPrimary` | us-east-2 | VPC, subnets, security groups |
| `MwaaDRNetworkSecondary` | us-east-1 | VPC, subnets, security groups |
| `MwaaDRS3Primary` | us-east-2 | S3 bucket for MWAA assets |
| `MwaaDRS3Secondary` | us-east-1 | S3 bucket for MWAA assets |
| `MwaaDRMwaaPrimary` | us-east-2 | MWAA environment |
| `MwaaDRMwaaSecondary` | us-east-1 | MWAA environment |

### MWAA Environments

| Environment | Region | Size |
|-------------|--------|------|
| `mwaa-openlineage-dr-primary-dev` | us-east-2 | mw1.small (1-2 workers) |
| `mwaa-openlineage-dr-secondary-dev` | us-east-1 | mw1.small (1-2 workers) |

## Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.9+
- Node.js 18+
- AWS CDK v2 (`npm install -g aws-cdk`)
- CDK bootstrapped in both regions

## Deployment

See [QUICK_START.md](QUICK_START.md) for step-by-step deployment instructions.

Quick version:

```bash
cd examples/disaster-recovery
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
npx cdk deploy --all -c account=$ACCOUNT --require-approval never
```

After CDK deploys, verify both MWAA environments show `AVAILABLE` status.
See QUICK_START.md for details.

## Verification

```bash
# Check both environments are AVAILABLE
aws mwaa get-environment --name mwaa-openlineage-dr-primary-dev \
  --region us-east-2 --query 'Environment.Status'

aws mwaa get-environment --name mwaa-openlineage-dr-secondary-dev \
  --region us-east-1 --query 'Environment.Status'
```

Open the Airflow UI to verify the environment is accessible.

## Cleanup

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
npx cdk destroy --all -c account=$ACCOUNT --require-approval never
```

MWAA deletion takes ~20-30 minutes. If S3 bucket deletion fails, empty the
buckets first with `aws s3 rm s3://<bucket> --recursive`.

## Cost Estimate

| Resource | Cost |
|----------|------|
| MWAA (2 x mw1.small) | ~$600/month |
| NAT Gateways (2 regions) | ~$64/month |
| S3 | < $5/month |

Total: ~$670/month

## Next Steps

1. Deploy [metadb-backup-restore](../metadb-backup-restore/) for:
   - Metadata database backup/restore via Glue
   - Automated failover orchestration (Step Functions)
   - Health check monitoring with EventBridge
   - SNS notifications
2. Add your own DAGs to both S3 buckets
3. Set up S3 cross-region replication for DAG synchronization

## Related Documentation

- [Quick Start Guide](QUICK_START.md)
- [MetaDB Backup/Restore Example](../metadb-backup-restore/README.md)
