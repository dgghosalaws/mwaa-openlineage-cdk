# MWAA OpenLineage Deployment Modes

This CDK project supports four deployment modes to match your requirements and budget.

## Quick Comparison

| Mode | MWAA | Marquez | Cost/Month | Deployment Time | Use Case |
|------|------|---------|------------|-----------------|----------|
| **Standard** | 1 | EC2 | ~$350 | ~30 min | Dev/Test |
| **Blue-Green** | 2 | EC2 | ~$700 | ~45 min | Zero-downtime MWAA |
| **HA Marquez** | 1 | ALB+ASG+RDS | ~$650 | ~35 min | HA lineage tracking |
| **Full HA** | 2 | ALB+ASG+RDS | ~$1,000 | ~60 min | Complete HA |

## 1. Standard Mode

**Use when:**
- Development/testing environments
- Cost optimization is priority
- High availability not required
- Simple deployment preferred

**Configuration:**
```json
// cdk.json
{
  "context": {
    "enable_blue_green": false,
    "enable_ha_marquez": false
  }
}
```

**What gets deployed:**
- 1 VPC with public/private subnets
- 1 Marquez server (EC2 with Docker)
- 1 MWAA environment

**Cost:** ~$350/month (1 MWAA mw1.small)

**Pros:**
- ✅ Lowest cost
- ✅ Fastest deployment
- ✅ Simple architecture
- ✅ Easy to understand

**Cons:**
- ❌ No high availability
- ❌ Downtime during maintenance
- ❌ Single point of failure

## 2. Blue-Green Mode

**Use when:**
- Production environments
- Zero-downtime MWAA maintenance required
- Instant MWAA failover needed
- Safe Airflow version upgrades desired

**Configuration:**
```json
// cdk.json
{
  "context": {
    "enable_blue_green": true,
    "enable_ha_marquez": false
  }
}
```

**What gets deployed:**
- 1 VPC with public/private subnets
- 1 Marquez server (EC2 with Docker) - shared
- 2 MWAA environments (Blue + Green)
- Parameter Store for switching

**Cost:** ~$700/month (2 MWAA mw1.small)

**Pros:**
- ✅ Zero-downtime MWAA switching (< 1 second)
- ✅ Instant MWAA failover
- ✅ Safe Airflow upgrades
- ✅ Independent environment testing

**Cons:**
- ❌ Marquez is single point of failure
- ❌ Higher cost than standard
- ❌ More complex than standard

**See:** [BLUE_GREEN_DEPLOYMENT.md](BLUE_GREEN_DEPLOYMENT.md)

## 3. HA Marquez Mode

**Use when:**
- High availability lineage tracking required
- Single MWAA environment sufficient
- Marquez must be highly available
- Load balancing needed for Marquez

**Configuration:**
```json
// cdk.json
{
  "context": {
    "enable_blue_green": false,
    "enable_ha_marquez": true
  }
}
```

**What gets deployed:**
- 1 VPC with public/private subnets
- HA Marquez (ALB + ASG + RDS Aurora)
- 1 MWAA environment

**Cost:** ~$650/month (1 MWAA + HA Marquez)

**Pros:**
- ✅ Marquez high availability
- ✅ Auto-scaling Marquez
- ✅ Multi-AZ RDS
- ✅ Load balanced

**Cons:**
- ❌ MWAA downtime during maintenance
- ❌ No MWAA failover
- ❌ More expensive than standard

**See:** [ALB_ACCESS_GUIDE.md](ALB_ACCESS_GUIDE.md)

## 4. Full HA Mode (NEW!)

**Use when:**
- Mission-critical production workloads
- Complete high availability required
- Zero-downtime for everything
- Budget allows premium reliability
- Compliance requires HA

**Configuration:**
```json
// cdk.json
{
  "context": {
    "enable_blue_green": true,
    "enable_ha_marquez": true
  }
}
```

**What gets deployed:**
- 1 VPC with public/private subnets
- HA Marquez (ALB + ASG + RDS Aurora)
- 2 MWAA environments (Blue + Green)
- Parameter Store for switching

**Cost:** ~$1,000/month (2 MWAA + HA Marquez)

**Pros:**
- ✅ Complete high availability
- ✅ Zero-downtime MWAA switching
- ✅ HA lineage tracking
- ✅ No single point of failure
- ✅ Disaster recovery ready
- ✅ Production-grade reliability

**Cons:**
- ❌ Highest cost
- ❌ Most complex architecture
- ❌ Longest deployment time

**See:** [FULL_HA_GUIDE.md](FULL_HA_GUIDE.md)
- 2 MWAA environments (Blue + Green)
- Parameter Store for switching
- IAM permissions for SSM access

**Cost:** ~$700/month (2 MWAA mw1.small)

**Features:**
- ✅ Zero-downtime switching (instant)
- ✅ Both environments always available
- ✅ Separate S3 buckets per environment
- ✅ Shared Marquez with separate namespaces
- ✅ Parameter Store control

## Switching Between Modes

### From Standard to Blue-Green

1. Update cdk.json:
   ```json
   "enable_blue_green": true
   ```

2. Deploy:
   ```bash
   cdk deploy --all
   ```

3. Upload zero-downtime DAG:
   ```bash
   aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
     s3://mwaa-openlineage-mwaa-blue-dev-$(aws sts get-caller-identity --query Account --output text)/dags/
   
   aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
     s3://mwaa-openlineage-mwaa-green-dev-$(aws sts get-caller-identity --query Account --output text)/dags/
   ```

### From Blue-Green to Standard

1. Destroy blue-green stack:
   ```bash
   cdk destroy mwaa-openlineage-mwaa-bluegreen-dev
   ```

2. Update cdk.json:
   ```json
   "enable_blue_green": false
   ```

3. Deploy standard:
   ```bash
   cdk deploy --all
   ```

## Deployment Commands

### Standard Mode

```bash
# Set configuration
# Edit cdk.json: "enable_blue_green": false

# Deploy all stacks
cdk deploy --all

# Or deploy individually
cdk deploy mwaa-openlineage-network-dev
cdk deploy mwaa-openlineage-marquez-dev
cdk deploy mwaa-openlineage-mwaa-dev
```

### Blue-Green Mode

```bash
# Set configuration
# Edit cdk.json: "enable_blue_green": true

# Deploy all stacks
cdk deploy --all

# Or deploy individually
cdk deploy mwaa-openlineage-network-dev
cdk deploy mwaa-openlineage-marquez-dev
cdk deploy mwaa-openlineage-mwaa-bluegreen-dev

# Switch environments (instant!)
python3 switch_zero_downtime.py --to green
python3 switch_zero_downtime.py --to blue
```

## Cleanup

### Standard Mode

```bash
cdk destroy --all
```

### Blue-Green Mode

```bash
cdk destroy --all
```

Or use the cleanup script:
```bash
./cleanup_all.sh
```

## Comparison

| Feature | Standard | Blue-Green |
|---------|----------|------------|
| MWAA Environments | 1 | 2 |
| Monthly Cost | ~$350 | ~$700 |
| Deployment Time | ~30 min | ~45 min (parallel) |
| Switch Time | N/A | Instant |
| Downtime for Maintenance | Yes | No |
| High Availability | No | Yes |
| Complexity | Low | Medium |
| Best For | Dev/Test | Production |

## Recommendations

- **Development**: Use Standard mode
- **Staging**: Use Standard mode
- **Production**: Use Blue-Green mode
- **Cost-sensitive**: Use Standard mode
- **Mission-critical**: Use Blue-Green mode

## Next Steps

1. Choose your deployment mode
2. Update `cdk.json` with `enable_blue_green` setting
3. Run `cdk deploy --all`
4. If Blue-Green, upload zero-downtime DAGs
5. Test the deployment
6. (Blue-Green only) Test environment switching
