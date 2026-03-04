# Full HA Deployment Guide

Complete high availability setup combining Blue-Green MWAA with HA Marquez.

## Overview

Full HA mode provides:
- **Zero-downtime MWAA**: Blue-Green deployment with instant switching
- **High availability lineage**: HA Marquez with ALB, ASG, and RDS
- **Complete redundancy**: No single point of failure
- **Production ready**: Enterprise-grade reliability

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         VPC (10.0.0.0/16)                   │
│                                                             │
│  ┌──────────────────┐              ┌──────────────────┐   │
│  │  Public Subnets  │              │ Private Subnets  │   │
│  │                  │              │                  │   │
│  │  ┌────────────┐  │              │  ┌────────────┐  │   │
│  │  │    ALB     │  │              │  │ Blue MWAA  │  │   │
│  │  │  (Marquez) │  │              │  │            │  │   │
│  │  └────────────┘  │              │  └────────────┘  │   │
│  │        │         │              │                  │   │
│  │        ▼         │              │  ┌────────────┐  │   │
│  │  ┌────────────┐  │              │  │ Green MWAA │  │   │
│  │  │    NAT     │  │              │  │            │  │   │
│  │  │  Gateway   │  │              │  └────────────┘  │   │
│  │  └────────────┘  │              │                  │   │
│  └──────────────────┘              │  ┌────────────┐  │   │
│                                    │  │  Marquez   │  │   │
│                                    │  │    ASG     │  │   │
│                                    │  │  (2+ EC2)  │  │   │
│                                    │  └────────────┘  │   │
│                                    │        │         │   │
│                                    │        ▼         │   │
│                                    │  ┌────────────┐  │   │
│                                    │  │ RDS Aurora │  │   │
│                                    │  │ PostgreSQL │  │   │
│                                    │  │ (Multi-AZ) │  │   │
│                                    │  └────────────┘  │   │
│                                    └──────────────────┘   │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │         Parameter Store                          │   │
│  │  /mwaa/blue-green/active-environment = "blue"    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Components

### MWAA (Blue-Green)
- **Blue Environment**: Primary MWAA cluster
- **Green Environment**: Secondary MWAA cluster
- **Parameter Store**: Controls active environment
- **Zero-downtime switching**: < 1 second failover

### Marquez (HA)
- **Application Load Balancer**: Distributes traffic
- **Auto Scaling Group**: 2+ EC2 instances
- **RDS Aurora PostgreSQL**: Multi-AZ database
- **Secrets Manager**: Database credentials
- **ECR**: Container registry for Marquez images

## Configuration

### Enable Full HA Mode

```json
// cdk.json
{
  "context": {
    "enable_blue_green": true,
    "enable_ha_marquez": true,
    "region": "us-east-2"
  }
}
```

## Deployment

### Prerequisites
1. AWS CLI configured
2. CDK installed (`npm install -g aws-cdk`)
3. Python 3.9+ with venv
4. (Optional) Docker + ECR setup for production (see ECR_SETUP_GUIDE.md)

**Note**: This deployment uses Docker Hub images by default. For production with many instances, consider mirroring to ECR to avoid rate limits (see ECR_SETUP_GUIDE.md).

### Step 1: Configure

```bash
cd mwaa-openlineage-cdk

# Edit cdk.json
{
  "context": {
    "enable_blue_green": true,
    "enable_ha_marquez": true,
    "region": "us-east-2"
  }
}
```

### Step 2: Deploy All Stacks

```bash
# Deploy everything
cdk deploy --all --require-approval never

# Or deploy individually
cdk deploy mwaa-openlineage-network-dev
cdk deploy mwaa-openlineage-marquez-ha-dev
cdk deploy mwaa-openlineage-mwaa-bluegreen-dev
```

### Step 3: Upload DAGs

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-2

# Upload to Blue environment
aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-blue-dev-${REGION}-${ACCOUNT}/dags/ \
  --region ${REGION}

# Upload to Green environment
aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-green-dev-${REGION}-${ACCOUNT}/dags/ \
  --region ${REGION}
```

## Deployment Time

| Component | Time | Notes |
|-----------|------|-------|
| Network Stack | ~2 min | VPC, subnets, security groups |
| HA Marquez Stack | ~15 min | ALB, ASG, RDS Aurora |
| Blue-Green MWAA | ~45 min | Parallel deployment |
| **Total** | **~60 min** | All components |

## Cost Estimate

### Monthly Costs (us-east-2)

| Component | Cost | Notes |
|-----------|------|-------|
| Blue MWAA (mw1.small) | ~$350 | 24/7 operation |
| Green MWAA (mw1.small) | ~$350 | 24/7 operation |
| ALB | ~$25 | Load balancer |
| EC2 (2x t3.medium) | ~$60 | Auto Scaling Group |
| RDS Aurora (db.t3.medium) | ~$120 | Multi-AZ |
| NAT Gateway | ~$45 | Data transfer |
| S3, CloudWatch, etc. | ~$50 | Storage and logs |
| **Total** | **~$1,000/month** | Full HA setup |

### Cost Optimization
- Use Savings Plans for EC2/RDS (30-40% savings)
- Scale down non-prod environments
- Use lifecycle policies for S3
- Adjust MWAA environment class based on workload

## Operations

### Check Deployment Status

```bash
# Check MWAA environments
aws mwaa get-environment --name mwaa-openlineage-blue-dev --region us-east-2
aws mwaa get-environment --name mwaa-openlineage-green-dev --region us-east-2

# Check ALB health
aws elbv2 describe-target-health \
  --target-group-arn $(aws elbv2 describe-target-groups \
    --names mwaa-openlineage-marquez-ha-dev-tg \
    --query 'TargetGroups[0].TargetGroupArn' --output text) \
  --region us-east-2

# Check RDS status
aws rds describe-db-clusters \
  --db-cluster-identifier mwaa-openlineage-marquez-ha-dev \
  --region us-east-2
```

### Switch MWAA Environments

⚠️ **Important: DAG Management Strategy**

The zero-downtime switching shown here is for illustrative purposes. For production deployments, consider:

1. **Disable DAGs in standby by default** - Keep DAGs paused in the standby environment and only enable them after switching
2. **Use Parameter Store checks** - Ensure all DAGs check the active environment parameter (as shown in example DAGs)
3. **Environment-specific DAG deployment** - Deploy different DAG sets to each environment based on operational needs

Choose the approach that fits your requirements. The Parameter Store pattern works for demonstration, but production may need more robust DAG lifecycle management.

```bash
# Switch to Green
python3 switch_zero_downtime.py --to green --region us-east-2

# Switch to Blue
python3 switch_zero_downtime.py --to blue --region us-east-2

# Check current active
aws ssm get-parameter \
  --name /mwaa/blue-green/active-environment \
  --region us-east-2 \
  --query 'Parameter.Value' --output text
```

### Access Marquez UI

```bash
# Get ALB DNS name
aws elbv2 describe-load-balancers \
  --names mwaa-openlineage-marquez-ha-dev-alb \
  --query 'LoadBalancers[0].DNSName' --output text \
  --region us-east-2

# Access via browser
# http://<ALB-DNS-NAME>:3000
```

## High Availability Features

### MWAA (Blue-Green)
- ✅ Zero-downtime switching (< 1 second)
- ✅ Instant failover capability
- ✅ Independent environment updates
- ✅ Safe Airflow version upgrades
- ✅ No MWAA downtime during switch

### Marquez (HA)
- ✅ Load balancer distributes traffic
- ✅ Auto Scaling (2+ instances)
- ✅ Multi-AZ RDS Aurora
- ✅ Automatic failover
- ✅ Health checks and auto-recovery

### Combined Benefits
- ✅ No single point of failure
- ✅ Complete redundancy
- ✅ Production-grade reliability
- ✅ Disaster recovery ready
- ✅ Maintenance without downtime

## Maintenance Workflows

### Update Airflow Version (Zero-Downtime)

1. **Update Green environment**
   ```bash
   # Green is standby, safe to update
   # Update Airflow version in Green MWAA
   # Test DAGs in Green
   ```

2. **Switch to Green**
   ```bash
   python3 switch_zero_downtime.py --to green --region us-east-2
   # Green is now active, Blue is standby
   ```

3. **Update Blue environment**
   ```bash
   # Blue is standby, safe to update
   # Update Airflow version in Blue MWAA
   # Test DAGs in Blue
   ```

4. **Switch back to Blue (optional)**
   ```bash
   python3 switch_zero_downtime.py --to blue --region us-east-2
   ```

### Update Marquez Version

1. **Build new Docker image**
   ```bash
   # Build and push to ECR
   # See ECR_SETUP_GUIDE.md
   ```

2. **Update ASG launch template**
   ```bash
   # ASG will gradually replace instances
   # ALB health checks ensure zero downtime
   ```

3. **Monitor rollout**
   ```bash
   # Watch ASG instance refresh
   # Verify Marquez UI accessibility
   ```

## Disaster Recovery

### MWAA Failure Scenarios

**Scenario 1: Blue environment fails**
```bash
# Immediately switch to Green
python3 switch_zero_downtime.py --to green --region us-east-2
# Recovery time: < 1 second
```

**Scenario 2: Green environment fails**
```bash
# Already on Blue, no action needed
# Fix Green environment while Blue runs
```

### Marquez Failure Scenarios

**Scenario 1: Single EC2 instance fails**
- ALB detects failure via health checks
- Traffic automatically routed to healthy instances
- ASG launches replacement instance
- Recovery time: ~5 minutes

**Scenario 2: RDS primary fails**
- Aurora automatically fails over to standby
- Recovery time: ~30 seconds
- No data loss (synchronous replication)

**Scenario 3: Entire AZ fails**
- Multi-AZ deployment continues in other AZ
- ALB routes to healthy AZ
- RDS fails over to standby in other AZ
- Recovery time: ~1 minute

## Monitoring

### CloudWatch Alarms (Recommended)

```bash
# MWAA alarms
- SchedulerHeartbeat
- QueuedTasks
- RunningTasks
- FailedTasks

# ALB alarms
- UnhealthyHostCount
- TargetResponseTime
- HTTPCode_Target_5XX_Count

# RDS alarms
- CPUUtilization
- DatabaseConnections
- FreeableMemory
- ReplicaLag
```

### Metrics to Monitor

1. **MWAA Metrics**
   - DAG execution success rate
   - Task duration
   - Scheduler lag
   - Worker utilization

2. **Marquez Metrics**
   - API response time
   - Request rate
   - Error rate
   - Database connections

3. **Infrastructure Metrics**
   - EC2 CPU/memory
   - RDS CPU/memory
   - ALB request count
   - Network throughput

## Troubleshooting

### MWAA Issues

**Problem**: DAGs not executing in active environment
```bash
# Check parameter value
aws ssm get-parameter --name /mwaa/blue-green/active-environment

# Check DAG code
# Verify parameter check logic in DAG
```

**Problem**: Switch not taking effect
```bash
# Verify parameter updated
aws ssm get-parameter --name /mwaa/blue-green/active-environment

# Check MWAA IAM permissions
# Ensure ssm:GetParameter permission exists
```

### Marquez Issues

**Problem**: ALB health checks failing
```bash
# Check target health
aws elbv2 describe-target-health --target-group-arn <TG-ARN>

# Check EC2 instance logs
# SSH to instance and check Docker logs
```

**Problem**: Database connection errors
```bash
# Check RDS status
aws rds describe-db-clusters --db-cluster-identifier <CLUSTER-ID>

# Check security group rules
# Verify EC2 can reach RDS on port 5432
```

## Cleanup

### Destroy All Stacks

```bash
# Use cleanup script
./cleanup_all.sh

# Or manually
cdk destroy mwaa-openlineage-mwaa-bluegreen-dev
cdk destroy mwaa-openlineage-marquez-ha-dev
cdk destroy mwaa-openlineage-network-dev
```

### Cost Savings During Cleanup
- Delete S3 buckets manually if needed
- Remove ECR images
- Delete CloudWatch log groups
- Remove Parameter Store parameters

## Best Practices

### Security
1. Use VPC endpoints for AWS services
2. Enable encryption at rest (S3, RDS, EBS)
3. Rotate database credentials regularly
4. Use IAM roles, not access keys
5. Enable CloudTrail for audit logging

### Reliability
1. Test failover procedures regularly
2. Monitor all components continuously
3. Set up automated backups
4. Document runbooks for common issues
5. Practice disaster recovery scenarios

### Cost Optimization
1. Right-size MWAA environment class
2. Use Savings Plans for EC2/RDS
3. Enable S3 lifecycle policies
4. Review CloudWatch log retention
5. Scale down non-production environments

## Comparison with Other Modes

| Feature | Standard | Blue-Green | HA Marquez | Full HA |
|---------|----------|------------|------------|---------|
| MWAA Environments | 1 | 2 | 1 | 2 |
| MWAA Zero-Downtime | ❌ | ✅ | ❌ | ✅ |
| Marquez HA | ❌ | ❌ | ✅ | ✅ |
| Cost/Month | ~$350 | ~$700 | ~$650 | ~$1,000 |
| Deployment Time | ~30 min | ~45 min | ~35 min | ~60 min |
| Production Ready | ⚠️ | ✅ | ✅ | ✅✅ |

## Summary

Full HA mode provides:
- **Complete redundancy**: No single point of failure
- **Zero-downtime operations**: For both MWAA and Marquez
- **Enterprise-grade**: Production-ready reliability
- **Disaster recovery**: Automatic failover capabilities

**Use Full HA when:**
- Running mission-critical workloads
- Requiring 99.9%+ uptime
- Need zero-downtime maintenance
- Compliance requires high availability
- Budget allows for premium reliability

---

**Next Steps:**
1. Review [BLUE_GREEN_DEPLOYMENT.md](BLUE_GREEN_DEPLOYMENT.md) for MWAA details
2. Review [ALB_ACCESS_GUIDE.md](ALB_ACCESS_GUIDE.md) for Marquez HA details
3. Configure ECR following [ECR_SETUP_GUIDE.md](ECR_SETUP_GUIDE.md)
4. Deploy and test in non-production first
5. Set up monitoring and alarms
6. Document your runbooks
