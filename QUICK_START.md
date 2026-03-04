# Quick Start - Blue-Green Deployment

## TL;DR

Your code is ready! Just choose your mode and deploy.

## Current Configuration

```json
// cdk.json
"enable_blue_green": false  // ← Change this to true for blue-green
"region": "us-east-2"       // ← Deployment region
```

## Quick Commands

### 1. Destroy Current Stack (us-east-1)

```bash
cd mwaa-openlineage-cdk
chmod +x cleanup_all.sh
./cleanup_all.sh
```

### 2. Choose Mode

**Standard Mode (Single MWAA):**
- Keep `"enable_blue_green": false` in cdk.json
- Cost: ~$350/month
- Deployment: ~30 min

**Blue-Green Mode (Dual MWAA):**
- Change to `"enable_blue_green": true` in cdk.json
- Cost: ~$700/month
- Deployment: ~60 min
- Zero-downtime switching

### 3. Deploy

```bash
# Bootstrap if needed
cdk bootstrap aws://$(aws sts get-caller-identity --query Account --output text)/us-east-2

# Deploy all stacks
cdk deploy --all
```

### 4. Test (Blue-Green Only)

```bash
# Upload zero-downtime DAG
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-blue-dev-${ACCOUNT}/dags/ --region us-east-2

aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-green-dev-${ACCOUNT}/dags/ --region us-east-2

# Test instant switching
python3 switch_zero_downtime.py --to green --region us-east-2
python3 switch_zero_downtime.py --to blue --region us-east-2
```

## What You Get

### Standard Mode
- ✅ 1 MWAA environment
- ✅ Marquez server
- ✅ OpenLineage integration
- ✅ Simple deployment

### Blue-Green Mode
- ✅ 2 MWAA environments (Blue + Green)
- ✅ Shared Marquez server
- ✅ OpenLineage integration
- ✅ Parameter Store switching
- ✅ Zero-downtime capability
- ✅ Instant failover

## How Zero-Downtime Works

1. **Parameter Store**: `/mwaa/blue-green/active-environment` = "blue" or "green"
2. **DAG Check**: Each DAG checks parameter at runtime
3. **Conditional Execution**: Active runs, standby skips
4. **Instant Switch**: Update parameter → takes effect immediately

## Switch Commands

```bash
# Switch to Green
python3 switch_zero_downtime.py --to green --region us-east-2

# Switch to Blue
python3 switch_zero_downtime.py --to blue --region us-east-2

# Check current active
aws ssm get-parameter \
  --name /mwaa/blue-green/active-environment \
  --region us-east-2 \
  --query 'Parameter.Value' \
  --output text
```

## Documentation

- `BLUE_GREEN_READY.md` - Complete status and instructions
- `ZERO_DOWNTIME_GUIDE.md` - Detailed blue-green guide
- `DEPLOYMENT_MODES.md` - Mode comparison
- `ACCESSING_MARQUEZ.md` - Marquez access via SSM

## Ready to Go!

Your code is clean and ready. Just:
1. Destroy current stack
2. Set `enable_blue_green` flag
3. Deploy
4. Test

That's it! 🚀
