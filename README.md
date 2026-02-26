# MWAA with OpenLineage - CDK Project

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AWS CDK](https://img.shields.io/badge/AWS%20CDK-2.x-orange)](https://aws.amazon.com/cdk/)
[![Airflow](https://img.shields.io/badge/Airflow-3.0.6-blue)](https://airflow.apache.org/)
[![OpenLineage](https://img.shields.io/badge/OpenLineage-Native%20Provider-green)](https://openlineage.io/)

This CDK project creates a complete, production-ready MWAA environment with OpenLineage integration for automatic data lineage tracking using **Apache Airflow 3.0.6**.

## 🌟 Features

- ✅ **Airflow 3.0.6** with native OpenLineage provider
- ✅ **Automated deployment** with AWS CDK
- ✅ **Marquez** for lineage visualization
- ✅ **Four deployment modes**: Standard, Blue-Green MWAA, HA Marquez, Full HA
- ✅ **Disaster Recovery** with automated failover and fallback
- ✅ **Production-ready** with security best practices
- ✅ **Zero-downtime switching** for Blue-Green deployments
- ✅ **Comprehensive documentation** with troubleshooting guides
- ✅ **Sample DAGs** demonstrating lineage capture
- ✅ **Performance testing suite** for capacity validation
- ✅ **No custom plugins needed** - uses native provider

## 📋 Deployment Modes

This project supports **four deployment modes**. Choose based on your requirements:

| Mode | MWAA | Marquez | Cost/Month | Use Case |
|------|------|---------|------------|----------|
| **Standard** | Single | Single EC2 | ~$350 | Development, testing |
| **Blue-Green MWAA** | Dual (Blue+Green) | Single EC2 | ~$700 | Zero-downtime MWAA updates |
| **HA Marquez** | Single | ALB+ASG+RDS | ~$650 | High availability lineage |
| **Full HA** | Dual (Blue+Green) | ALB+ASG+RDS | ~$1,000 | Production, mission-critical |

See **[DEPLOYMENT_MODES.md](DEPLOYMENT_MODES.md)** for detailed comparison and switching instructions.

## 📚 Advanced Examples

Looking for advanced deployment patterns? Check out the **[examples/](examples/)** directory:

### Disaster Recovery (DR)
Deploy MWAA across two AWS regions with automatic DAG control based on active region.

- **Features**: DynamoDB state management, automatic DAG pause/unpause, manual failover scripts
- **Cost**: ~$716/month (dual-region MWAA + minimal DynamoDB)
- **Use case**: Production environments requiring cross-region disaster recovery
- **Note**: Metadata backup/restore not included (Airflow 3.0 limitation - use AWS Backup instead)

See **[examples/disaster-recovery/README.md](examples/disaster-recovery/README.md)** for complete documentation and deployment instructions.

## 🚀 Quick Start

Choose your deployment mode based on requirements. All modes use the same codebase with different configuration flags in `cdk.json`.

### Mode 1: Standard Deployment (Default)

**Best for**: Development, testing, proof of concept  
**Cost**: ~$350/month  
**Setup time**: ~30 minutes  
**Configuration**: `enable_blue_green: false`, `enable_ha_marquez: false`

**Prerequisites**:
1. AWS CLI configured
2. AWS CDK installed (`npm install -g aws-cdk`)
3. Python 3.9+ with pip
4. Virtual environment activated

```bash
# 1. Clone the repository
git clone https://github.com/dgghosalaws/mwaa-openlineage-cdk.git
cd mwaa-openlineage-cdk

# 2. Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Bootstrap CDK (first time only)
cdk bootstrap

# 5. Deploy all stacks (uses app.py by default)
cdk deploy --all

# Or deploy individually:
# cdk deploy mwaa-openlineage-network-dev
# cdk deploy mwaa-openlineage-marquez-dev
# cdk deploy mwaa-openlineage-mwaa-dev
```

**What gets deployed**:
- Single Marquez EC2 instance (t3.medium)
- Containerized PostgreSQL database
- MWAA environment (mw1.small)
- VPC with public/private subnets

**Stacks created**:
- `mwaa-openlineage-network-dev`
- `mwaa-openlineage-marquez-dev`
- `mwaa-openlineage-mwaa-dev`

---

### Mode 2: Blue-Green MWAA

**Best for**: Zero-downtime Airflow version upgrades  
**Cost**: ~$700/month  
**Setup time**: ~45 minutes  
**Configuration**: `enable_blue_green: true`, `enable_ha_marquez: false`

```bash
# 1. Edit cdk.json
{
  "context": {
    "enable_blue_green": true,
    "enable_ha_marquez": false
  }
}

# 2. Deploy all stacks
cdk deploy --all

# 3. Upload zero-downtime DAG to both environments
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region)

aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-blue-dev-${REGION}-${ACCOUNT}/dags/

aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-green-dev-${REGION}-${ACCOUNT}/dags/

# 4. Test instant switching
python3 switch_zero_downtime.py --to green
python3 switch_zero_downtime.py --to blue
```

**What gets deployed**:
- Two MWAA environments (Blue and Green)
- Single Marquez EC2 instance (shared)
- Parameter Store for active environment tracking
- Zero-downtime switching capability

**Blue-Green Features**:
- ✅ Zero-downtime switching (< 1 second)
- ✅ Both environments always AVAILABLE
- ✅ Instant failover capability
- ✅ Safe testing of Airflow upgrades
- ✅ Quick rollback via Parameter Store

⚠️ **Note**: The Parameter Store switching pattern is for demonstration. For production, consider disabling DAGs by default in the standby environment or using environment-specific DAG deployment strategies based on your operational requirements.

**Stacks created**:
- `mwaa-openlineage-network-dev`
- `mwaa-openlineage-marquez-dev`
- `mwaa-openlineage-mwaa-bluegreen-dev`

See **[BLUE_GREEN_DEPLOYMENT.md](BLUE_GREEN_DEPLOYMENT.md)** for complete guide.

---

### Mode 3: HA Marquez

**Best for**: High availability lineage tracking  
**Cost**: ~$650/month  
**Setup time**: ~35 minutes  
**Configuration**: `enable_blue_green: false`, `enable_ha_marquez: true`

```bash
# Edit cdk.json
{
  "context": {
    "enable_blue_green": false,
    "enable_ha_marquez": true
  }
}

# Deploy
cdk deploy --all
```

**What gets deployed**:
- Single MWAA environment
- Internal Application Load Balancer (ALB)
- Auto Scaling Group (2-4 EC2 instances)
- RDS PostgreSQL Multi-AZ
- Enhanced security and automatic failover

**Stacks created**:
- `mwaa-openlineage-network-dev`
- `mwaa-openlineage-marquez-ha-dev`
- `mwaa-openlineage-mwaa-dev`

See **[ALB_ACCESS_GUIDE.md](ALB_ACCESS_GUIDE.md)** for HA Marquez details.

---

### Mode 4: Full HA (Blue-Green MWAA + HA Marquez)

**Best for**: Production, mission-critical workloads  
**Cost**: ~$1,000/month  
**Setup time**: ~60 minutes  
**Configuration**: `enable_blue_green: true`, `enable_ha_marquez: true`

```bash
# 1. Edit cdk.json
{
  "context": {
    "enable_blue_green": true,
    "enable_ha_marquez": true,
    "region": "us-east-1"
  }
}

# 2. Deploy all stacks
cdk deploy --all

# 3. Upload zero-downtime DAG to both environments
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region)

aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-blue-dev-${REGION}-${ACCOUNT}/dags/

aws s3 cp assets/dags/example_blue_green_zero_downtime.py \
  s3://mwaa-openlineage-mwaa-green-dev-${REGION}-${ACCOUNT}/dags/

# 4. Test instant switching
python3 switch_zero_downtime.py --to green --region ${REGION}
python3 switch_zero_downtime.py --to blue --region ${REGION}
```

**What gets deployed**:
- Two MWAA environments (Blue and Green) with zero-downtime switching
- Internal ALB with Auto Scaling (2-4 instances)
- RDS PostgreSQL Multi-AZ
- Complete redundancy - no single point of failure

**Full HA Features**:
- ✅ Zero-downtime MWAA switching (< 1 second)
- ✅ High availability Marquez (ALB + ASG + RDS)
- ✅ No single point of failure
- ✅ Production-grade reliability

⚠️ **Note**: The Parameter Store switching pattern is for demonstration. For production, consider disabling DAGs by default in the standby environment or using environment-specific DAG deployment strategies based on your operational requirements.

**Stacks created**:
- `mwaa-openlineage-network-dev`
- `mwaa-openlineage-marquez-ha-dev`
- `mwaa-openlineage-mwaa-bluegreen-dev`

See **[FULL_HA_GUIDE.md](FULL_HA_GUIDE.md)** for complete HA deployment guide.

---

### Choosing Between Deployment Modes

| Criteria | Standard | Blue-Green | HA Marquez | Full HA |
|----------|----------|------------|------------|---------|
| **Use Case** | Dev/Test/POC | Zero-Downtime MWAA | HA Lineage | Mission-Critical |
| **MWAA Environments** | 1 | 2 | 1 | 2 |
| **Marquez** | Single EC2 | Single EC2 | ALB + ASG + RDS | ALB + ASG + RDS |
| **Availability** | Single instance | Dual MWAA | Multi-AZ Marquez | Complete HA |
| **Failover** | Manual | Instant (MWAA) | Automatic (Marquez) | Both |
| **Switch Time** | N/A | < 1 second | N/A | < 1 second |
| **Cost** | ~$350/month | ~$700/month | ~$650/month | ~$1,000/month |
| **Setup Time** | ~30 minutes | ~45 minutes | ~35 minutes | ~60 minutes |
| **Best For** | Development | Zero-Downtime Ops | HA Lineage | Production |

**Note**: All deployments can coexist in the same AWS account/region as they use different stack names.

---

## 🔄 Disaster Recovery (Optional)

This project includes comprehensive disaster recovery capabilities with automated failover and fallback between two AWS regions.

### DR Features

- ✅ **Bidirectional Failover**: Automatic failover when primary region fails
- ✅ **Automated Fallback**: Automatic fallback when primary region recovers
- ✅ **State Management**: DynamoDB Global Table tracks active region
- ✅ **Metadata Sync**: Continuous backup with 5-minute RPO
- ✅ **Health Monitoring**: Continuous health checks of both regions
- ✅ **Zero Data Loss**: For committed DAG runs

### DR Configuration

Enable DR in `cdk.json`:

```json
{
  "context": {
    "enable_dr": true,
    "dr_config": {
      "primary_region": "us-east-1",
      "secondary_region": "us-west-2",
      "backup_schedule": "rate(5 minutes)",
      "health_check_interval": "rate(1 minute)",
      "health_check_threshold": 3,
      "fallback_cooldown_minutes": 30,
      "notification_emails": ["ops-team@example.com"]
    }
  }
}
```

### Deploy DR Infrastructure

```bash
# Deploy DR to both regions
./deploy_dr.sh

# Test failover
./test_dr_failover.sh
```

### DR Metrics

- **RPO (Recovery Point Objective)**: < 5 minutes
- **RTO (Recovery Time Objective)**: < 10 minutes
- **Failover Time**: 5-8 minutes
- **Fallback Time**: 5-8 minutes

See **[DR_WITH_FALLBACK.md](DR_WITH_FALLBACK.md)** for complete DR guide including architecture, testing, and troubleshooting.

---

## 📚 Documentation

### Getting Started
- **[README.md](README.md)** - This file (standard deployment)
- **[BLUE_GREEN_DEPLOYMENT.md](BLUE_GREEN_DEPLOYMENT.md)** - Blue-Green deployment with zero-downtime switching
- **[QUICK_START.md](QUICK_START.md)** - Quick reference guide
- **[DEPLOYMENT_MODES.md](DEPLOYMENT_MODES.md)** - Comparison of all deployment modes

### Architecture & Design
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Detailed architecture overview
- **[ZERO_DOWNTIME_GUIDE.md](ZERO_DOWNTIME_GUIDE.md)** - Zero-downtime switching implementation
- **[ACCESSING_MARQUEZ.md](ACCESSING_MARQUEZ.md)** - Accessing Marquez in private subnet
- **[MONITORING.md](MONITORING.md)** - CloudWatch monitoring and metrics
- **[PERFORMANCE_TESTING.md](PERFORMANCE_TESTING.md)** - Capacity testing and validation
- **[DR_WITH_FALLBACK.md](DR_WITH_FALLBACK.md)** - Disaster recovery with automated failover and fallback

### Policies & Guidelines
- **[SECURITY.md](SECURITY.md)** - Security policy and best practices
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - How to contribute
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** - Community guidelines

## ⚠️ Airflow 3.0 Important Notes

This project is specifically configured for **Airflow 3.0.6** using the **native OpenLineage provider**:

1. **Uses apache-airflow-providers-openlineage** (NOT deprecated openlineage-airflow package)
2. **No custom plugins needed** - provider handles everything automatically
3. **Configuration via Airflow config options** (NOT Secrets Manager or plugins)
4. **Configuration values must be lowercase** ("false" not "False")

For complete details on Airflow 3.0 configuration, see the troubleshooting section below.

## Architecture

The project supports two deployment architectures:

### Standard Deployment (Development/Testing)

Three main stacks:

1. **Network Stack** - VPC with public and private subnets across 2 AZs
2. **Marquez Stack** - Single EC2 instance running Marquez in Docker
3. **MWAA Stack** - Managed Airflow 3.0.6 environment

**Best for**: Development, testing, proof of concept, cost-sensitive projects

### High Availability Deployment (Production)

Three main stacks with enhanced Marquez backend:

1. **Network Stack** - VPC with enhanced security
2. **Marquez HA Stack** - Internal ALB, Auto Scaling Group (2-4 instances), RDS Multi-AZ
3. **MWAA Stack** - Managed Airflow 3.0.6 environment

**Best for**: Production, business-critical workloads, 24/7 availability

**Note**: The HA deployment enhances the Marquez lineage backend with load balancing, auto scaling, and database redundancy. MWAA is a fully managed AWS service with built-in high availability in both deployment options.

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for detailed architecture diagrams and comparison.

## What Gets Deployed

### Infrastructure
- ✅ VPC with public/private subnets
- ✅ Marquez server (EC2 + Docker)
- ✅ MWAA environment (mw1.small)
- ✅ S3 bucket for MWAA assets
- ✅ IAM roles and security groups

### Monitoring Stack (Deployed by Default)
- ✅ CloudWatch dashboard with comprehensive MWAA metrics
- ✅ Real-time monitoring of workers, tasks, and resource utilization
- ✅ Automatic deployment with MWAA stack
- ✅ Can be disabled via `cdk.json` (`enable_monitoring: false`)

**Monitoring Metrics Include:**
- Worker count and auto-scaling behavior
- Running and queued tasks
- CPU and memory utilization
- Database connections
- Scheduler performance

See **[MONITORING.md](MONITORING.md)** for detailed metrics and dashboard usage.

### OpenLineage Integration (Airflow 3.0)
- ✅ apache-airflow-providers-openlineage (native provider)
- ✅ Automatic HTTP transport configuration
- ✅ Configuration via Airflow config options
- ✅ No custom plugins needed
- ✅ Lowercase configuration values for Airflow 3.0

### Sample DAG
- ✅ openlineage_demo DAG
- ✅ Configuration verification
- ✅ Connectivity testing
- ✅ Sample data processing
- ✅ Lineage generation

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **AWS CDK** installed:
   ```bash
   npm install -g aws-cdk
   ```
3. **Python 3.9+** installed
4. **AWS Account** with permissions to create:
   - VPC, EC2, MWAA, S3, Secrets Manager, IAM

## Installation

### Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **AWS CDK** installed:
   ```bash
   npm install -g aws-cdk
   ```
3. **Python 3.9+** installed
4. **AWS Account** with permissions to create:
   - VPC, EC2, MWAA, S3, IAM
   - For HA: RDS, ALB, Auto Scaling Groups

### Setup Steps

#### 1. Clone and Setup Environment

```bash
# Navigate to the project directory
cd mwaa-openlineage-cdk

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### 2. Bootstrap CDK (First Time Only)

```bash
cdk bootstrap
```

#### 3. Choose Your Deployment

**For Standard Deployment (Development/Testing)**:
```bash
# Review what will be deployed
cdk list
# Output: 
#   mwaa-openlineage-network-dev
#   mwaa-openlineage-marquez-dev
#   mwaa-openlineage-mwaa-dev
#   mwaa-openlineage-monitoring-dev (deployed automatically with MWAA)

# Deploy all stacks
cdk deploy --all
```

**Note:** The monitoring stack is automatically deployed when you deploy the MWAA stack. To disable it, set `enable_monitoring: false` in `cdk.json` before deployment.

**For HA Deployment (Production)**:
```bash
# Review what will be deployed
cdk list --app "python3 app_ha.py"
# Output: mwaa-openlineage-network-ha, mwaa-openlineage-marquez-ha, mwaa-openlineage-mwaa-ha

# Deploy HA stacks
cdk deploy mwaa-openlineage-network-ha mwaa-openlineage-marquez-ha \
  --app "python3 app_ha.py" \
  --require-approval never \
  --region us-east-2
```

#### 4. Deployment Time

**Standard Deployment**: ~35-40 minutes
- Network Stack: ~3 minutes
- Marquez Stack: ~5 minutes (+ 2-3 minutes for Marquez to start)
- MWAA Stack: ~25-30 minutes
- Monitoring Stack: ~2 minutes (deployed automatically with MWAA stack)

**HA Deployment**: ~20-25 minutes
- Network Stack: ~3 minutes
- Marquez HA Stack: ~15-20 minutes (RDS Multi-AZ takes time)
- Instance initialization: ~3-5 minutes
- MWAA Stack: ~25-30 minutes (optional)

## Post-Deployment

### 1. Get Outputs

After deployment, note the CloudFormation outputs:

```bash
# Get all outputs
aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-mwaa-dev \
  --query 'Stacks[0].Outputs'
```

Key outputs:
- **MarquezUiUrl**: Marquez UI URL (http://...)
- **MarquezApiUrl**: Marquez API URL (http://...)
- **MwaaWebserverUrl**: Airflow UI URL (https://...)
- **MwaaBucketName**: S3 bucket name

### 2. Access Marquez UI

Open the Marquez UI URL in your browser:
```
http://<marquez-public-ip>:3000
```

### 3. Access CloudWatch Monitoring Dashboard

The monitoring dashboard is automatically created and provides real-time metrics:

```bash
# Get dashboard URL
aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-monitoring-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`DashboardUrl`].OutputValue' \
  --output text
```

Or navigate in AWS Console:
1. Go to CloudWatch → Dashboards
2. Find dashboard: `MWAA-{your-environment-name}`
3. View metrics:
   - Worker count and auto-scaling
   - Running/queued tasks
   - CPU and memory utilization
   - Database connections
   - Scheduler performance

### 4. Access Airflow UI

1. Go to AWS MWAA Console
2. Click on your environment (e.g., `mwaa-openlineage-dev`)
3. Click "Open Airflow UI"

### 5. Verify Configuration

In MWAA Console:
1. Go to your environment (e.g., `mwaa-openlineage-dev`)
2. Click "Edit"
3. Scroll to "Airflow configuration options"
4. Verify these settings exist:
   - `openlineage.transport`
   - `openlineage.namespace`
   - `openlineage.disabled`

### 6. Run the Demo DAG

1. In Airflow UI, find DAG: `openlineage_demo`
2. Enable the DAG (toggle switch)
3. Click "Trigger DAG"
4. Wait for completion (~2-3 minutes)

### 7. View Lineage in Marquez

1. Open Marquez UI
2. Select namespace (e.g., `mwaa-openlineage-dev`)
3. View jobs and lineage graph
4. You should see:
   - Job: `openlineage_demo`
   - Tasks: verify_openlineage_config, test_marquez_connectivity, etc.
   - Lineage connections between tasks

## Project Structure

```
mwaa-openlineage-cdk/
├── app.py                          # Standard deployment CDK app
├── app_ha.py                       # HA deployment CDK app
├── cdk.json                        # CDK configuration
├── requirements.txt                # Python dependencies
├── README.md                       # This file (main documentation)
├── FULL_HA_GUIDE.md                # Complete HA deployment guide
├── ARCHITECTURE.md                 # Architecture details (both deployments)
├── stacks/
│   ├── __init__.py
│   ├── network_stack.py           # VPC and networking (shared)
│   ├── marquez_stack.py           # Single Marquez instance (standard)
│   ├── marquez_ha_stack.py        # HA Marquez with ALB, ASG, RDS
│   └── mwaa_stack.py              # MWAA environment (shared)
├── assets/
│   ├── dags/
│   │   └── openlineage_demo_dag.py # Sample DAG
│   └── root/
│       └── requirements.txt        # Airflow requirements (native provider)
└── deploy_ha.sh                    # HA deployment helper script
```

**Key Files**:
- `app.py` - Entry point for standard deployment (default)
- `app_ha.py` - Entry point for HA deployment
- `stacks/marquez_stack.py` - Single instance Marquez
- `stacks/marquez_ha_stack.py` - HA Marquez with ALB, ASG, RDS
- `stacks/network_stack.py` - Shared by both deployments
- `stacks/mwaa_stack.py` - Shared by both deployments

## Configuration

### Customize Deployment

Edit `cdk.json` to change:

```json
{
  "context": {
    "project_name": "mwaa-openlineage",  // Change project name
    "environment": "dev",                 // Change environment
    "account": "123456789012",           // Your AWS account
    "region": "us-east-1"                // Your AWS region
  }
}
```

### Customize MWAA

Edit `stacks/mwaa_stack.py`:
- Change `environment_class` (mw1.small, mw1.medium, mw1.large)
- Change `airflow_version`
- Add more Airflow configuration options
- Modify logging levels

### Customize Marquez

Edit `stacks/marquez_stack.py`:
- Change instance type
- Change Marquez version
- Add custom configuration

## Adding Your Own DAGs

### Option 1: Add to assets/dags/

1. Create your DAG file in `assets/dags/`
2. Redeploy: `cdk deploy mwaa-openlineage-mwaa-dev`

### Option 2: Upload to S3

```bash
# Get bucket name
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-mwaa-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`MwaaBucketName`].OutputValue' \
  --output text)

# Upload DAG
aws s3 cp your_dag.py s3://$BUCKET/dags/
```

## Monitoring

### Check MWAA Status

```bash
aws mwaa get-environment \
  --name YOUR-ENVIRONMENT-NAME \
  --query 'Environment.Status'
```

### View MWAA Logs

1. Go to MWAA Console
2. Click environment
3. Monitoring > View Logs
4. Select log type (Scheduler, Task, Webserver)

### Check Marquez Status

```bash
# Get Marquez instance ID
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-marquez-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`MarquezInstanceId`].OutputValue' \
  --output text)

# Check Docker containers
aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker ps"]'
```

### View Marquez Logs

```bash
aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker logs marquez-api --tail 100"]'
```

## Troubleshooting

### MWAA Not Starting

- Check CloudWatch logs for errors
- Verify S3 bucket has correct files
- Check IAM role permissions
- Ensure VPC has internet access (NAT Gateway)

### No Lineage Appearing

**Important**: Airflow 3.0 uses the native provider approach with automatic configuration.

1. **Check Scheduler Logs**:
   - Look for "OpenLineage provider initialized"
   - Should see transport configuration messages
   - No warnings about "REMOVED" or deprecated packages

2. **Check Configuration**:
   - MWAA Console > Environment > Airflow configuration options
   - Verify openlineage.transport, openlineage.namespace, openlineage.disabled

3. **Check Task Logs**:
   - Run a DAG and check task logs
   - Look for "Sending OpenLineage event: START"
   - Look for "Sending OpenLineage event: COMPLETE"

4. **Test Marquez**:
   ```bash
   curl http://<marquez-ip>:5000/api/v1/namespaces
   ```

5. **Common Airflow 3.0 Issues**:
   - Configuration values must be lowercase strings ("false" not "False")
   - Must use apache-airflow-providers-openlineage package
   - Old openlineage-airflow package is deprecated and will cause errors

### Marquez Not Responding

If Marquez UI is not accessible:

1. **Check if Marquez containers are running**:
   ```bash
   # Get Marquez instance ID
   INSTANCE_ID=$(aws cloudformation describe-stacks \
     --stack-name mwaa-openlineage-marquez-dev \
     --query 'Stacks[0].Outputs[?OutputKey==`MarquezInstanceId`].OutputValue' \
     --output text)
   
   # Check container status
   aws ssm send-command \
     --instance-ids "$INSTANCE_ID" \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["docker ps"]'
   ```

2. **Restart Marquez if containers are stopped**:
   ```bash
   aws ssm send-command \
     --instance-ids "$INSTANCE_ID" \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["cd /home/ec2-user/marquez && sudo -u ec2-user ./docker/up.sh --tag 0.42.0 --detach"]'
   ```

3. **Access Marquez** (in private subnet):
   
   Marquez is deployed in a private subnet for security. See [ACCESSING_MARQUEZ.md](ACCESSING_MARQUEZ.md) for detailed access methods including:
   - SSM Session Manager (recommended - no SSH keys needed)
   - Port forwarding for UI access
   - Temporary IP whitelisting for development
   
   Quick test via SSM:
   ```bash
   # Get instance ID
   INSTANCE_ID=$(aws cloudformation describe-stacks \
     --stack-name mwaa-openlineage-marquez-dev \
     --query 'Stacks[0].Outputs[?OutputKey==`MarquezInstanceId`].OutputValue' \
     --output text)
   
   # Test API via SSM
   aws ssm send-command \
     --instance-ids "$INSTANCE_ID" \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["curl -s http://localhost:5000/api/v1/namespaces"]' \
     --query 'Command.CommandId' --output text
   ```

**Note**: After EC2 instance reboot, Marquez containers may need to be manually restarted. The systemd service is configured to auto-start on boot, but if it fails, use the restart command above.

## Costs

### Standard Deployment

Estimated monthly costs (us-east-1):

- **MWAA (mw1.small)**: ~$300/month
- **EC2 (t3.medium)**: ~$30/month
- **NAT Gateway**: ~$32/month
- **S3**: ~$1/month
- **Data Transfer**: Variable

**Total**: ~$363/month (approximate)

### High Availability Deployment

Estimated monthly costs (us-east-2):

- **MWAA (mw1.small)**: ~$300/month
- **RDS db.t3.small Multi-AZ**: ~$60/month
- **2x EC2 t3.medium**: ~$60/month
- **Internal ALB**: ~$20/month
- **NAT Gateway**: ~$32/month
- **S3**: ~$1/month

**Total**: ~$473/month (approximate)

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for cost optimization strategies.

## Cleanup

To avoid ongoing charges, destroy all resources when no longer needed.

### Standard Deployment Cleanup

```bash
# Destroy all standard stacks
cdk destroy --all

# Or destroy individually (reverse order recommended)
cdk destroy mwaa-openlineage-mwaa-dev
cdk destroy mwaa-openlineage-marquez-dev
cdk destroy mwaa-openlineage-network-dev
```

### HA Deployment Cleanup

```bash
# Destroy all HA stacks
cdk destroy mwaa-openlineage-mwaa-ha mwaa-openlineage-marquez-ha mwaa-openlineage-network-ha \
  --app "python3 app_ha.py" \
  --region us-east-2

# Or destroy individually (reverse order recommended)
cdk destroy mwaa-openlineage-mwaa-ha --app "python3 app_ha.py" --region us-east-2
cdk destroy mwaa-openlineage-marquez-ha --app "python3 app_ha.py" --region us-east-2
cdk destroy mwaa-openlineage-network-ha --app "python3 app_ha.py" --region us-east-2
```

**Note**: S3 buckets will be automatically emptied and deleted. RDS snapshots (HA deployment) are retained by default for 7 days.

## Security Features

This project implements security best practices out of the box:

### Built-in Security

1. **Private Subnet Deployment**:
   - ✅ Marquez deployed in private subnet (no public IP)
   - ✅ MWAA in private subnets
   - ✅ Access via SSM Session Manager (no SSH keys needed)
   - See [ACCESSING_MARQUEZ.md](ACCESSING_MARQUEZ.md) for access methods

2. **Encryption Enabled**:
   - ✅ S3 bucket encryption with KMS (key rotation enabled)
   - ✅ EBS volumes encrypted
   - ✅ Data encrypted at rest

3. **Restricted Access**:
   - ✅ SSH access disabled by default
   - ✅ Security groups allow only necessary ports
   - ✅ Marquez accessible only from within VPC
   - ✅ IAM roles with least privilege

4. **Monitoring Ready**:
   - ✅ CloudWatch logging enabled for MWAA
   - ✅ SSM Session Manager for secure access
   - ✅ VPC Flow Logs can be enabled

### Additional Production Recommendations

1. **Enhanced Monitoring**:
   - Set up CloudWatch alarms for critical metrics
   - Enable VPC Flow Logs
   - Enable CloudTrail logging

2. **Access Control**:
   - Set MWAA webserver to PRIVATE_ONLY for production
   - Use AWS Client VPN for team access
   - Implement MFA for AWS console access

3. **Secrets Management**:
   - Rotate credentials regularly
   - Use AWS Secrets Manager for sensitive data
   - Enable secret rotation policies

## Support

For issues or questions:
1. Check CloudWatch logs
2. Review MWAA documentation: https://docs.aws.amazon.com/mwaa/
3. Review OpenLineage docs: https://openlineage.io/docs/
4. Review Marquez docs: https://marquezproject.github.io/marquez/
5. Open an issue on GitHub: https://github.com/dgghosalaws/mwaa-openlineage-cdk/issues

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- AWS MWAA team for the managed Airflow service
- OpenLineage community for the lineage standard
- Marquez team for the lineage visualization tool
- AWS CDK team for the infrastructure as code framework

## Author

**Dipankar Ghosal**
- GitHub: [@dgghosalaws](https://github.com/dgghosalaws)

## Next Steps

1. ✅ Deploy the stacks
2. ✅ Verify Marquez is running
3. ✅ Run the demo DAG
4. ✅ View lineage in Marquez UI
5. 🚀 Add your own DAGs
6. 🚀 Integrate with your data pipelines
7. 🚀 Use lineage for impact analysis and compliance
