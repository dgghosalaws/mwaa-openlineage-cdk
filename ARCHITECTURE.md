# Architecture Overview

## High-Level Architecture

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

### 3. MWAA Environment

**Purpose**: Managed Apache Airflow for workflow orchestration

**Components**:
- Airflow 3.0.6
- Environment class: mw1.small
- Workers in private subnets
- Webserver with public access
- Scheduler and workers

**Storage**:
- S3 bucket for DAGs, plugins, requirements
- Versioning enabled
- Automatic deployment via CDK

**Configuration**:
- Secrets Manager integration
- OpenLineage plugins pre-installed
- CloudWatch logging enabled
- IAM role with necessary permissions

### 4. OpenLineage Integration (Airflow 3.0)

**How It Works**:

1. **Plugin Loading**:
   - env_var_plugin loads on Airflow startup
   - Fetches OPENLINEAGE_URL and OPENLINEAGE_NAMESPACE from Secrets Manager
   - Sets environment variables
   - Configures HTTP transport with lowercase values ("false" not "False")

2. **Listener Registration** (Airflow 3.0 Approach):
   - openlineage_listener_plugin registers OpenLineage listener
   - Listener hooks into Airflow lifecycle events
   - Captures DAG run, task execution, and dataset information
   - **Note**: Airflow 3.0 uses listener approach, NOT `lineage.backend` configuration

3. **Lineage Capture**:
   - On task start: Sends START event to Marquez
   - On task complete: Sends COMPLETE event with inputs/outputs
   - On task fail: Sends FAIL event
   - Automatic extraction of dataset information from operators

4. **Data Flow**:
   ```
   DAG Task → OpenLineage Listener → HTTP Transport → Marquez API → PostgreSQL
   ```

### 5. Data Flow

**DAG Deployment**:
```
Developer → S3 Bucket → MWAA → Airflow Scheduler → Workers
```

**Lineage Capture**:
```
Task Execution → OpenLineage Listener → Marquez API → Database → Marquez UI
```

**Configuration**:
```
Secrets Manager → MWAA → env_var_plugin → Environment Variables → OpenLineage
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
   - Secrets Manager read for variables
   - CloudWatch Logs write
   - SQS for Celery
   - KMS for encryption

2. **Marquez Instance Role**:
   - CloudWatch agent
   - SSM Session Manager

### Data Security

1. **Encryption**:
   - S3 bucket: Server-side encryption
   - Secrets Manager: Encrypted at rest
   - MWAA: Encrypted environment

2. **Access Control**:
   - IAM roles for service access
   - Security groups for network access
   - Secrets Manager for sensitive data

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

- Single instance (can be enhanced)
- Systemd auto-restart on failure
- Can add:
  - Auto Scaling Group
  - Application Load Balancer
  - RDS Multi-AZ for database

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

### Current Setup

- MWAA mw1.small: ~$300/month
- EC2 t3.medium: ~$30/month
- NAT Gateway: ~$32/month
- S3: ~$1/month

### Optimization Options

1. **MWAA**:
   - Use smaller environment class if possible
   - Optimize DAG schedules
   - Use spot instances for workers (if supported)

2. **Marquez**:
   - Use t3.small if load is low
   - Use Spot instance (with proper backup)
   - Schedule shutdown during off-hours

3. **Network**:
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
   - Move Marquez to private subnet
   - Add VPN or bastion host
   - Enable MWAA private webserver
   - Add WAF for public endpoints

2. **Scalability**:
   - Move Marquez DB to RDS
   - Add Auto Scaling for Marquez
   - Add Application Load Balancer

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

## Troubleshooting Guide

### Common Issues

1. **MWAA won't start**:
   - Check VPC has internet access
   - Verify IAM role permissions
   - Check S3 bucket accessibility
   - Review CloudWatch logs

2. **No lineage appearing**:
   - Verify plugins loaded (scheduler logs)
   - Check Secrets Manager variables
   - Test Marquez connectivity
   - Review task logs
   - **Airflow 3.0**: Ensure listener approach is used (not lineage.backend)
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
