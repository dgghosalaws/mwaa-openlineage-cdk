# MWAA DR - Quick Start Guide

Deploy multi-region MWAA infrastructure in ~50 minutes. This creates the
foundational two-region setup that the `metadb-backup-restore` example builds on.

## What You Get

- Two MWAA environments (primary in us-east-2, secondary in us-east-1)
- VPC, subnets, and security groups in both regions
- S3 buckets for MWAA assets (DAGs) in both regions

## Prerequisites

```bash
# Required
- AWS CLI configured with appropriate permissions
- Python 3.9+
- Node.js 18+
- AWS CDK v2: npm install -g aws-cdk

# Verify
aws sts get-caller-identity
python3 --version
node --version
cdk --version
```

## Deploy

### Step 1: Install Dependencies

```bash
cd examples/disaster-recovery
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Bootstrap CDK (if not already done)

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
npx cdk bootstrap aws://$ACCOUNT/us-east-2
npx cdk bootstrap aws://$ACCOUNT/us-east-1
```

### Step 3: Deploy All Stacks

```bash
npx cdk deploy --all -c account=$ACCOUNT --require-approval never
```

This deploys 6 stacks:
- `MwaaDRNetworkPrimary` / `MwaaDRNetworkSecondary` — VPC + networking (~5 min each)
- `MwaaDRS3Primary` / `MwaaDRS3Secondary` — S3 buckets (~2 min each)
- `MwaaDRMwaaPrimary` / `MwaaDRMwaaSecondary` — MWAA environments (~25 min each)

Total deployment time: ~40-50 minutes.

## Verify

### 1. Check MWAA Status

```bash
# Primary
aws mwaa get-environment \
  --name mwaa-openlineage-dr-primary-dev \
  --region us-east-2 \
  --query 'Environment.Status'

# Secondary
aws mwaa get-environment \
  --name mwaa-openlineage-dr-secondary-dev \
  --region us-east-1 \
  --query 'Environment.Status'
```

Both should return `"AVAILABLE"`.

### 2. Access Airflow UI

```bash
# Primary
aws mwaa create-web-login-token \
  --name mwaa-openlineage-dr-primary-dev \
  --region us-east-2

# Secondary
aws mwaa create-web-login-token \
  --name mwaa-openlineage-dr-secondary-dev \
  --region us-east-1
```

Open the returned URL in your browser to verify the environment is accessible.

## CDK Stacks

| Stack | Region | Description |
|-------|--------|-------------|
| `MwaaDRNetworkPrimary` | us-east-2 | VPC, subnets, security groups |
| `MwaaDRNetworkSecondary` | us-east-1 | VPC, subnets, security groups |
| `MwaaDRS3Primary` | us-east-2 | S3 bucket for MWAA assets |
| `MwaaDRS3Secondary` | us-east-1 | S3 bucket for MWAA assets |
| `MwaaDRMwaaPrimary` | us-east-2 | MWAA environment (Airflow 3.0.6) |
| `MwaaDRMwaaSecondary` | us-east-1 | MWAA environment (Airflow 3.0.6) |

## Cleanup

```bash
# Destroy all stacks (MWAA deletion takes ~20-30 minutes)
npx cdk destroy --all -c account=$ACCOUNT --require-approval never
```

If CDK destroy fails on S3 buckets (non-empty), empty them first:
```bash
aws s3 rm s3://$PRIMARY_BUCKET --recursive --region us-east-2
aws s3 rm s3://$SECONDARY_BUCKET --recursive --region us-east-1
```

## Cost Estimate

| Resource | Cost |
|----------|------|
| MWAA (2 x mw1.small) | ~$600/month |
| NAT Gateways (2 regions) | ~$64/month |
| S3 | < $5/month |
| VPC | Minimal |

Total: ~$670/month

Tip: reduce costs by using `mw1.micro` or stopping the secondary environment
when not actively testing DR.

## Next Steps

1. Deploy the [metadb-backup-restore](../metadb-backup-restore/) example for
   metadata backup/restore and automated failover orchestration
2. Add your own DAGs to both S3 buckets
3. Set up S3 cross-region replication for DAG synchronization
