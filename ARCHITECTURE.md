# Architecture Overview

This project supports two deployment architectures:
1. **Standard Deployment** - Single Marquez instance with containerized PostgreSQL
2. **High Availability (HA) Deployment** - Multi-AZ with RDS, ALB, and Auto Scaling

## Standard Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    VPC (10.0.0.0/16)                       │ │
│  │                                                             │ │
│  │  ┌──────────────────┐         ┌──────────────────┐        │ │
│  │  │  Public Subnet   │         │  Public Subnet   │        │ │
│  │  │   (AZ-1)         │         │   (AZ-2)         │        │ │
│  │  │                  │         │                  │        │ │
│  │  │  ┌────────────┐  │         │                  │        │ │
│  │  │  │  Marquez   │  │         │                  │        │ │
│  │  │  │  EC2       │  │         │                  │        │ │
│  │  │  │  (Docker)  │  │         │                  │        │ │
│  │  │  │  :5000     │  │         │                  │        │ │
│  │  │  │  :3000     │  │         │                  │        │ │
│  │  │  └────────────┘  │         │                  │        │ │
│  │  │                  │         │                  │        │ │
│  │  │  ┌────────────┐  │         │  ┌────────────┐  │        │ │
│  │  │  │ NAT        │  │         │  │ NAT        │  │        │ │
│  │  │  │ Gateway    │  │         │  │ Gateway    │  │        │ │
│  │  │  └────────────┘  │         │  └────────────┘  │        │ │
│  │  └──────────────────┘         └──────────────────┘        │ │
│  │           │                             │                  │ │
│  │  ┌────────▼─────────┐         ┌────────▼─────────┐        │ │
│  │  │  Private Subnet  │         │  Private Subnet  │        │ │
│  │  │   (AZ-1)         │         │   (AZ-2)         │        │ │
│  │  │                  │         │                  │        │ │
│  │  │  ┌────────────┐  │         │  ┌────────────┐  │        │ │
│  │  │  │   MWAA     │  │         │  │   MWAA     │  │        │ │
│  │  │  │  Workers   │  │         │  │  Workers   │  │        │ │
│  │  │  └────────────┘  │         │  └────────────┘  │        │ │
│  │  │                  │         │                  │        │ │
│  │  └──────────────────┘         └──────────────────┘        │ │
│  │                                                             │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │  S3 Bucket  │  │   Secrets    │  │   CloudWatch     │       │
│  │  (DAGs,     │  │   Manager    │  │   Logs           │       │
│  │   Plugins)  │  │              │  │                  │       │
│  └─────────────┘  └──────────────┘  └──────────────────┘       │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

## High Availability (HA) Deployment Architecture

For production workloads requiring high availability, use the HA deployment:

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    VPC (10.0.0.0/16)                       │ │
│  │                                                             │ │
│  │  ┌──────────────────┐         ┌──────────────────┐        │ │
│  │  │  Public Subnet   │         │  Public Subnet   │        │ │
│  │  │   (AZ-1)         │         │   (AZ-2)         │        │ │
│  │  │                  │         │                  │        │ │
│  │  │  ┌────────────┐  │         │  ┌────────────┐  │        │ │
│  │  │  │ NAT        │  │         │  │ NAT        │  │        │ │
│  │  │  │ Gateway    │  │         │  │ Gateway    │  │        │ │
│  │  │  └────────────┘  │         │  └────────────┘  │        │ │
│  │  └──────────────────┘         └──────────────────┘        │ │
│  │           │                             │                  │ │
│  │  ┌────────▼─────────┐         ┌────────▼─────────┐        │ │
│  │  │  Private Subnet  │         │  Private Subnet  │        │ │
│  │  │   (AZ-1)         │         │   (AZ-2)         │        │ │
│  │  │                  │         │                  │        │ │
│  │  │  ┌────────────┐  │         │  ┌────────────┐  │        │ │
│  │  │  │ Internal   │  │         │  │            │  │        │ │
│  │  │  │ ALB        │◄─┼─────────┼──┤ RDS Multi- │  │        │ │
│  │  │  │ :5000,:3000│  │         │  │ AZ (SSL)   │  │        │ │
│  │  │  └──────┬─────┘  │         │  └────────────┘  │        │ │
│  │  │         │        │         │                  │        │ │
│  │  │  ┌──────▼─────┐  │         │  ┌────────────┐  │        │ │
│  │  │  │ Marquez    │  │         │  │ Marquez    │  │        │ │
│  │  │  │ Instance 1 │  │         │  │ Instance 2 │  │        │ │
│  │  │  │ (ASG)      │  │         │  │ (ASG)      │  │        │ │
│  │  │  └────────────┘  │         │  └────────────┘  │        │ │
│  │  │                  │         │                  │        │ │
│  │  │  ┌────────────┐  │         │  ┌────────────┐  │        │ │
│  │  │  │   MWAA     │  │         │  │   MWAA     │  │        │ │
│  │  │  │  Workers   │  │         │  │  Workers   │  │        │ │
│  │  │  └────────────┘  │         │  └────────────┘  │        │ │
│  │  │                  │         │                  │        │ │
│  │  └──────────────────┘         └──────────────────┘        │ │
│  │                                                             │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │  S3 Bucket  │  │   Secrets    │  │   CloudWatch     │       │
│  │  (DAGs,     │  │   Manager    │  │   Logs           │       │
│  │   Plugins)  │  │  (RDS Creds) │  │                  │       │
│  └─────────────┘  └──────────────┘  └──────────────────┘       │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### HA Deployment Features

**High Availability**:
- Internal Application Load Balancer (ALB) in private subnets
- Auto Scaling Group (2-4 instances) across multiple AZs
- RDS PostgreSQL Multi-AZ with automatic failover
- Health checks and automatic instance replacement

**Security**:
- Internal ALB (not internet-facing) - only accessible from VPC
- All compute resources in private subnets
- SSL/TLS required for RDS connections
- Secrets Manager for database credentials
- Security groups with least privilege

**Scalability**:
- Auto Scaling based on CPU utilization (70% threshold)
- RDS storage autoscaling (20GB-100GB)
- Multiple Marquez instances for load distribution

**Endpoints**:
- API: http://internal-alb-dns:5000 (via ALB)
- UI: http://internal-alb-dns:3000 (via ALB)
- Access: SSM Session Manager, Bastion Host, or Client VPN

**Deployment**:
```bash
cdk deploy mwaa-openlineage-network-ha mwaa-openlineage-marquez-ha \
  --app "python3 app_ha.py" \
  --region us-east-2
```

See [FULL_HA_GUIDE.md](FULL_HA_GUIDE.md) for complete HA deployment guide.

---

## Component Details

### 1. Network Layer (VPC)

**Purpose**: Provides network isolation and security

**Components**:
- VPC with CIDR 10.0.0.0/16
- 2 Public Subnets (one per AZ)
- 2 Private Subnets (one per AZ)
- Internet Gateway for public subnet access
- NAT Gateways for private subnet internet access
- Route tables for traffic routing

**Security Groups**:
- Marquez SG: Allows ports 5000 (API), 3000 (UI), 22 (SSH)
- MWAA SG: Self-referencing for internal communication

### 2. Marquez Server

**Purpose**: Lineage tracking and visualization

#### Standard Deployment

**Components**:
- EC2 Instance (t3.medium, Amazon Linux 2023)
- Docker + Docker Compose
- Marquez containers:
  - marquez-api (port 5000)
  - marquez-web (port 3000)
  - marquez-db (PostgreSQL)

**Features**:
- Automatic installation via UserData
- Systemd service for auto-restart
- SSM Session Manager for secure access
- CloudWatch monitoring

**Endpoints**:
- API: http://<private-ip>:5000
- UI: http://<public-ip>:3000

#### High Availability Deployment

**Components**:
- Internal Application Load Balancer (ALB)
- Auto Scaling Group (2-4 EC2 instances, t3.medium)
- RDS PostgreSQL Multi-AZ (db.t3.small)
- Secrets Manager for database credentials

**Features**:
- Multi-AZ deployment for high availability
- Automatic scaling based on CPU utilization
- Health checks on both API and UI endpoints
- SSL/TLS for database connections
- Internal ALB (not internet-facing)
- Automatic instance replacement on failure

**Endpoints**:
- API: http://internal-alb-dns:5000 (via ALB)
- UI: http://internal-alb-dns:3000 (via ALB)
- Access: SSM Session Manager, Bastion, or Client VPN

**Database**:
- RDS PostgreSQL 15 Multi-AZ
- Automated backups (7 days retention)
- Storage autoscaling (20GB-100GB)
- SSL required for all connections

**Deployment Files**:
- `app_ha.py` - HA CDK application
- `stacks/marquez_ha_stack.py` - HA stack implementation
- `deploy_ha.sh` - Deployment script

### 3. MWAA Environment

**Purpose**: Managed Apache Airflow for workflow orchestration

**Components**:
- Airflow 3.0.6
- Environment class: mw1.small
- Workers in private subnets
- Webserver with public access
- Scheduler and workers

**Storage**:
- S3 bucket for DAGs and requirements.txt
- Versioning enabled
- Automatic deployment via CDK
- Structure: requirements.txt at bucket root, DAGs in dags/ folder

**Configuration**:
- OpenLineage native provider (apache-airflow-providers-openlineage)
- Configuration via Airflow configuration options
- CloudWatch logging enabled
- IAM role with necessary permissions

### 4. OpenLineage Integration (Airflow 3.0)

**How It Works**:

1. **Native Provider Configuration**:
   - Uses `apache-airflow-providers-openlineage>=2.2.0` (native provider)
   - No custom plugins required
   - Configuration via Airflow configuration options in MWAA stack
   - Transport configured as JSON: `{"type": "http", "url": "<marquez-url>", "endpoint": "api/v1/lineage"}`
   - Namespace set to: `{project_name}-{environment}` (e.g., "mwaa-openlineage-dev")

2. **Automatic Lineage Capture**:
   - Provider automatically hooks into Airflow lifecycle events
   - Captures DAG run, task execution, and dataset information
   - No manual listener registration needed
   - Works out-of-the-box with Airflow 3.0

3. **Lineage Events**:
   - On task start: Sends START event to Marquez
   - On task complete: Sends COMPLETE event with inputs/outputs
   - On task fail: Sends FAIL event
   - Automatic extraction of dataset information from operators

4. **Data Flow**:
   ```
   DAG Task → Native OpenLineage Provider → HTTP Transport → Marquez API → PostgreSQL
   ```

**Important Notes**:
- Airflow 3.0 requires lowercase string values in config ("false" not "False")
- No Secrets Manager needed - configuration is in MWAA stack
- No custom plugins required - provider handles everything

### 5. Data Flow

**DAG Deployment**:
```
Developer → S3 Bucket → MWAA → Airflow Scheduler → Workers
```

**Lineage Capture**:
```
Task Execution → Native OpenLineage Provider → Marquez API → Database → Marquez UI
```

**Configuration**:
```
MWAA Stack → Airflow Configuration Options → Native OpenLineage Provider
```

## Security Architecture

### Network Security

1. **Public Subnets**:
   - Marquez EC2 (for UI access)
   - NAT Gateways

2. **Private Subnets**:
   - MWAA workers (no direct internet access)
   - Access via NAT Gateway

3. **Security Groups**:
   - Marquez: Restricted to VPC + SSH from anywhere (can be tightened)
   - MWAA: Self-referencing only
   - MWAA → Marquez: Allowed on port 5000

### IAM Security

1. **MWAA Execution Role**:
   - S3 read/write for DAGs bucket
   - CloudWatch Logs write
   - SQS for Celery
   - KMS for encryption
   - Airflow metrics publishing

2. **Marquez Instance Role**:
   - CloudWatch agent
   - SSM Session Manager

### Data Security

1. **Encryption**:
   - S3 bucket: Server-side encryption
   - MWAA: Encrypted environment

2. **Access Control**:
   - IAM roles for service access
   - Security groups for network access

## Scalability

### MWAA Scaling

- **Horizontal**: Auto-scales workers based on load
- **Vertical**: Can upgrade environment class (small → medium → large)
- **Configuration**: Adjustable min/max workers

### Marquez Scaling

- **Vertical**: Upgrade EC2 instance type
- **Horizontal**: Can deploy multiple Marquez instances with load balancer
- **Database**: PostgreSQL can be moved to RDS for better scalability

## High Availability

### MWAA

- Multi-AZ deployment by default
- Automatic failover
- Managed by AWS

### Marquez

#### Standard Deployment
- Single instance (basic setup)
- Systemd auto-restart on failure
- Manual scaling required

#### HA Deployment (Recommended for Production)
- **Multi-AZ**: Instances across multiple availability zones
- **Auto Scaling**: 2-4 instances based on CPU utilization
- **Load Balancing**: Internal ALB distributes traffic
- **Database**: RDS Multi-AZ with automatic failover
- **Health Checks**: Automatic instance replacement
- **Backup**: Automated RDS backups (7 days retention)
- **Recovery Time**: ~5 minutes for instance replacement
- **Availability**: 99.9% uptime target

**HA Features**:
- Automatic failover for database
- Zero-downtime deployments with rolling updates
- Health checks on API and UI endpoints
- Automatic instance recovery
- SSL/TLS for all database connections

## Monitoring

### CloudWatch Metrics

- MWAA: DAG runs, task duration, worker CPU/memory
- EC2: CPU, network, disk
- Custom: OpenLineage event counts

### CloudWatch Logs

- MWAA: Scheduler, worker, webserver, DAG processing
- Marquez: Via CloudWatch agent (optional)

### Alarms (Recommended)

- MWAA environment health
- Task failure rate
- Marquez instance health
- API response time

## Cost Optimization

### Standard Deployment

- MWAA mw1.small: ~$300/month
- EC2 t3.medium: ~$30/month
- NAT Gateway: ~$32/month
- S3: ~$1/month
- **Total**: ~$363/month

### HA Deployment

- MWAA mw1.small: ~$300/month
- RDS db.t3.small Multi-AZ: ~$60/month
- 2x EC2 t3.medium: ~$60/month
- Internal ALB: ~$20/month
- NAT Gateway: ~$32/month
- S3: ~$1/month
- **Total**: ~$473/month

### Optimization Options

1. **MWAA**:
   - Use smaller environment class if possible
   - Optimize DAG schedules
   - Use spot instances for workers (if supported)

2. **Marquez (Standard)**:
   - Use t3.small if load is low
   - Use Spot instance (with proper backup)
   - Schedule shutdown during off-hours

3. **Marquez (HA)**:
   - Use Reserved Instances for predictable workloads
   - Adjust Auto Scaling min/max based on actual load
   - Use RDS Reserved Instances
   - Enable RDS storage autoscaling

4. **Network**:
   - Single NAT Gateway instead of per-AZ
   - VPC endpoints for AWS services

## Disaster Recovery

### Backup Strategy

1. **MWAA**:
   - S3 bucket versioning (enabled)
   - DAGs in source control
   - Configuration as code (CDK)

2. **Marquez**:
   - Database backups (manual or automated)
   - EBS snapshots
   - Configuration in CDK

### Recovery Procedures

1. **MWAA Failure**:
   - Redeploy stack with CDK
   - S3 versioning preserves DAGs
   - ~30 minutes to restore

2. **Marquez Failure**:
   - Redeploy stack with CDK
   - Restore database from backup
   - ~10 minutes to restore

## Future Enhancements

### Recommended Improvements

1. **Security**:
   - ✅ Move Marquez to private subnet (HA deployment)
   - Add VPN or bastion host for HA ALB access
   - Enable MWAA private webserver
   - Add WAF for public endpoints

2. **Scalability**:
   - ✅ Move Marquez DB to RDS (HA deployment)
   - ✅ Add Auto Scaling for Marquez (HA deployment)
   - ✅ Add Application Load Balancer (HA deployment)
   - Add read replicas for RDS

3. **Monitoring**:
   - Add CloudWatch dashboards
   - Set up alarms
   - Enable X-Ray tracing
   - Add custom metrics

4. **Compliance**:
   - Enable CloudTrail
   - Add Config rules
   - Enable GuardDuty
   - Add Security Hub

5. **Cost**:
   - Add cost allocation tags
   - Set up budgets and alerts
   - Use Savings Plans
   - Optimize instance types

### Already Implemented (HA Deployment)

- ✅ Internal ALB in private subnets
- ✅ RDS Multi-AZ for database
- ✅ Auto Scaling Group for Marquez
- ✅ SSL/TLS for database connections
- ✅ Secrets Manager for credentials
- ✅ Health checks and automatic recovery

## Troubleshooting Guide

### Common Issues

1. **MWAA won't start**:
   - Check VPC has internet access
   - Verify IAM role permissions
   - Check S3 bucket accessibility
   - Review CloudWatch logs

2. **No lineage appearing**:
   - Verify native provider installed (check requirements.txt)
   - Check MWAA Airflow configuration options
   - Test Marquez connectivity from MWAA VPC
   - Review task logs in CloudWatch
   - **Airflow 3.0**: Uses native provider (apache-airflow-providers-openlineage)
   - **Airflow 3.0**: Configuration via airflow_configuration_options (not plugins)
   - **Airflow 3.0**: Verify lowercase config values ("false" not "False")

3. **Marquez not responding**:
   - Check EC2 instance status
   - Verify Docker containers running
   - Check security group rules
   - Review system logs

### Debug Commands

```bash
# Check MWAA status
aws mwaa get-environment --name mwaa-openlineage-dev

# Check Marquez containers
aws ssm send-command --instance-ids <id> \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker ps"]'

# Test Marquez API
curl http://<marquez-ip>:5000/api/v1/namespaces

# View MWAA logs
# Go to MWAA Console > Environment > Monitoring > View Logs
```


## Deployment Comparison

### When to Use Standard Deployment

**Best for**:
- Development and testing environments
- Proof of concept projects
- Low-traffic workloads
- Cost-sensitive projects
- Learning and experimentation

**Characteristics**:
- Single Marquez instance
- Containerized PostgreSQL
- Public subnet deployment
- Lower cost (~$363/month)
- Simpler architecture
- Manual scaling

**Deployment**:
```bash
cdk deploy --all
```

### When to Use HA Deployment

**Best for**:
- Production environments
- Business-critical workloads
- High-traffic applications
- Compliance requirements
- 24/7 availability needs

**Characteristics**:
- Multiple Marquez instances (2-4)
- RDS Multi-AZ PostgreSQL
- Internal ALB in private subnets
- Higher cost (~$473/month)
- Auto Scaling and failover
- Enhanced security

**Deployment**:
```bash
cdk deploy mwaa-openlineage-network-ha mwaa-openlineage-marquez-ha \
  --app "python3 app_ha.py" \
  --region us-east-2
```

### Feature Comparison

| Feature | Standard | HA |
|---------|----------|-----|
| Availability | Single instance | Multi-AZ |
| Database | Containerized PostgreSQL | RDS Multi-AZ |
| Load Balancing | None | Internal ALB |
| Auto Scaling | No | Yes (2-4 instances) |
| Failover | Manual | Automatic |
| SSL/TLS | Optional | Required |
| Network | Public subnet | Private subnet |
| Access | Direct IP | Via ALB |
| Backup | Manual | Automated (7 days) |
| Cost | ~$363/month | ~$473/month |
| Setup Time | ~40 minutes | ~25 minutes |
| Recovery Time | Manual | ~5 minutes |

### Migration Path

To migrate from Standard to HA:

1. **Export lineage data** from standard Marquez
2. **Deploy HA infrastructure** using `app_ha.py`
3. **Import lineage data** to HA Marquez
4. **Update MWAA configuration** to point to HA ALB
5. **Destroy standard deployment**

See [FULL_HA_GUIDE.md](FULL_HA_GUIDE.md) for detailed HA deployment instructions.

