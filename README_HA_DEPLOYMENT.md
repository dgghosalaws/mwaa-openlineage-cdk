# MWAA with OpenLineage - High Availability Deployment Guide

## Overview

This guide covers deploying the High Availability (HA) version of the MWAA OpenLineage infrastructure with:
- Internal Application Load Balancer (ALB)
- RDS PostgreSQL Multi-AZ
- Auto Scaling Group (2-4 instances)
- SSL/TLS encryption
- Enhanced security posture

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         VPC                                  │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │              Private Subnets                        │    │
│  │                                                     │    │
│  │  ┌──────────────────┐      ┌──────────────────┐  │    │
│  │  │  Internal ALB    │      │  RDS Multi-AZ    │  │    │
│  │  │  Port 5000 (API) │      │  PostgreSQL      │  │    │
│  │  │  Port 3000 (UI)  │      │  (SSL required)  │  │    │
│  │  └────────┬─────────┘      └────────▲─────────┘  │    │
│  │           │                          │            │    │
│  │           │                          │            │    │
│  │  ┌────────▼─────────┐      ┌────────┴─────────┐  │    │
│  │  │  EC2 Instance 1  │      │  EC2 Instance 2  │  │    │
│  │  │  Marquez API     │      │  Marquez API     │  │    │
│  │  │  Marquez Web     │      │  Marquez Web     │  │    │
│  │  └──────────────────┘      └──────────────────┘  │    │
│  │                                                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │              Private Subnets                        │    │
│  │                                                     │    │
│  │  ┌──────────────────┐                              │    │
│  │  │  MWAA            │                              │    │
│  │  │  Environment     │──────────────────────────────┼────┤
│  │  │                  │  Accesses Internal ALB       │    │
│  │  └──────────────────┘                              │    │
│  │                                                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

1. AWS CLI configured with appropriate credentials
2. AWS CDK installed (`npm install -g aws-cdk`)
3. Python 3.9+ with pip
4. Docker images mirrored to ECR (see [ECR_SETUP_GUIDE.md](ECR_SETUP_GUIDE.md))

---

## Deployment Steps

### 1. Install Dependencies

```bash
cd mwaa-openlineage-cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Deploy HA Infrastructure

```bash
# Deploy network and Marquez HA stacks
cdk deploy mwaa-openlineage-network-ha mwaa-openlineage-marquez-ha \
  --app "python3 app_ha.py" \
  --require-approval never \
  --region us-east-2
```

**Deployment time**: ~15-20 minutes

**What gets deployed**:
- VPC with public and private subnets
- RDS PostgreSQL Multi-AZ with SSL
- Internal ALB in private subnets
- Auto Scaling Group with 2 instances
- Security groups with least privilege access

### 3. Verify Deployment

Wait 3-5 minutes after deployment for instances to initialize, then check target health:

```bash
# Get target group ARNs
aws elbv2 describe-target-groups --region us-east-2 \
  --query 'TargetGroups[?contains(TargetGroupName, `Marqu`)].{Name:TargetGroupName,ARN:TargetGroupArn,Port:Port}' \
  --output table

# Check API target health (port 5000)
aws elbv2 describe-target-health --region us-east-2 \
  --target-group-arn <API-TARGET-GROUP-ARN> \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' \
  --output table

# Check UI target health (port 3000)
aws elbv2 describe-target-health --region us-east-2 \
  --target-group-arn <UI-TARGET-GROUP-ARN> \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' \
  --output table
```

Expected output: Both targets should show `healthy` state.

### 4. Deploy MWAA Stack (Optional)

```bash
cdk deploy mwaa-openlineage-mwaa-ha \
  --app "python3 app_ha.py" \
  --require-approval never \
  --region us-east-2
```

**Deployment time**: ~25-30 minutes

---

## Accessing the Internal ALB

Since the ALB is internal (not internet-facing), it can only be accessed from within the VPC. Here are the available methods:

### Method 1: Via SSM Session Manager (Recommended for Testing)

This method doesn't require SSH keys or bastion hosts.

```bash
# Get instance ID
INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups --region us-east-2 \
  --query 'AutoScalingGroups[?contains(AutoScalingGroupName, `Marquez`)].Instances[0].InstanceId' \
  --output text)

# Get ALB DNS
ALB_DNS=$(aws cloudformation describe-stacks --region us-east-2 \
  --stack-name mwaa-openlineage-marquez-ha \
  --query 'Stacks[0].Outputs[?OutputKey==`MarquezAlbDnsName`].OutputValue' \
  --output text)

# Test API endpoint
COMMAND_ID=$(aws ssm send-command --region us-east-2 \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"curl -s http://$ALB_DNS:5000/api/v1/namespaces\"]" \
  --query 'Command.CommandId' \
  --output text)

# Wait a few seconds, then get output
sleep 5
aws ssm get-command-invocation --region us-east-2 \
  --command-id $COMMAND_ID \
  --instance-id $INSTANCE_ID \
  --query 'StandardOutputContent' \
  --output text

# Test UI endpoint
COMMAND_ID=$(aws ssm send-command --region us-east-2 \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"curl -s -I http://$ALB_DNS:3000/\"]" \
  --query 'Command.CommandId' \
  --output text)

sleep 5
aws ssm get-command-invocation --region us-east-2 \
  --command-id $COMMAND_ID \
  --instance-id $INSTANCE_ID \
  --query 'StandardOutputContent' \
  --output text
```

### Method 2: Via Bastion Host

Launch an EC2 instance in a public subnet of the same VPC:

```bash
# Get VPC ID
VPC_ID=$(aws cloudformation describe-stacks --region us-east-2 \
  --stack-name mwaa-openlineage-network-ha \
  --query 'Stacks[0].Outputs[?OutputKey==`VpcId`].OutputValue' \
  --output text)

# Get public subnet ID
PUBLIC_SUBNET=$(aws ec2 describe-subnets --region us-east-2 \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:aws-cdk:subnet-type,Values=Public" \
  --query 'Subnets[0].SubnetId' \
  --output text)

# Launch bastion instance
aws ec2 run-instances --region us-east-2 \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.micro \
  --subnet-id $PUBLIC_SUBNET \
  --key-name <your-key-name> \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=marquez-bastion}]'

# SSH into bastion
ssh -i your-key.pem ec2-user@<bastion-public-ip>

# From bastion, access ALB
curl http://$ALB_DNS:5000/api/v1/namespaces
curl http://$ALB_DNS:3000/
```

### Method 3: Via AWS Client VPN (Production)

For production environments, set up AWS Client VPN for secure remote access:

1. Create Client VPN endpoint in the VPC
2. Associate with private subnets
3. Configure authentication (Active Directory or certificate-based)
4. Download VPN configuration
5. Connect and access ALB directly

### Method 4: Via MWAA (Primary Use Case)

MWAA runs in the same VPC and can access the internal ALB automatically. No additional configuration needed.

**API URL**: `http://<ALB-DNS>:5000`  
**UI URL**: `http://<ALB-DNS>:3000`

---

## Configuration Options

### Internal ALB (Default - Recommended)

```bash
# Deploy with internal ALB (default)
cdk deploy mwaa-openlineage-network-ha mwaa-openlineage-marquez-ha \
  --app "python3 app_ha.py" \
  --require-approval never \
  --region us-east-2
```

**Security**: ✅ Best security posture - only accessible from within VPC  
**Use case**: Production deployments

### Internet-Facing ALB (Testing Only)

```bash
# Deploy with internet-facing ALB
cdk deploy mwaa-openlineage-network-ha mwaa-openlineage-marquez-ha \
  --app "python3 app_ha.py" \
  --context internet_facing=true \
  --require-approval never \
  --region us-east-2
```

**Security**: ⚠️ Publicly accessible - use only for testing  
**Use case**: Quick testing and development

**Important**: If using internet-facing ALB, add additional security controls:
- IP whitelist in security group
- AWS WAF with rate limiting
- Cognito authentication
- HTTPS with ACM certificate

---

## Endpoints

### API Endpoint (Port 5000)

**Base URL**: `http://<ALB-DNS>:5000`

**Available endpoints**:
- `GET /api/v1/namespaces` - List all namespaces
- `GET /api/v1/jobs` - List all jobs
- `GET /api/v1/datasets` - List all datasets
- `GET /api/v1/lineage` - Get lineage graph
- `GET /api/v1/health` - Health check
- `GET /api/v1/version` - API version

### UI Endpoint (Port 3000)

**URL**: `http://<ALB-DNS>:3000`

The Marquez Web UI provides:
- Visual lineage graphs
- Dataset exploration
- Job run history
- Search functionality
- Namespace management

---

## Monitoring and Troubleshooting

### Check Target Health

```bash
# List all target groups
aws elbv2 describe-target-groups --region us-east-2 \
  --query 'TargetGroups[?contains(TargetGroupName, `Marqu`)].{Name:TargetGroupName,ARN:TargetGroupArn}' \
  --output table

# Check specific target group health
aws elbv2 describe-target-health --region us-east-2 \
  --target-group-arn <TARGET-GROUP-ARN>
```

### View Instance Logs

```bash
# Get instance ID
INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups --region us-east-2 \
  --query 'AutoScalingGroups[?contains(AutoScalingGroupName, `Marquez`)].Instances[0].InstanceId' \
  --output text)

# View Marquez API logs
aws ssm send-command --region us-east-2 \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker logs marquez-api --tail 50"]'

# View Marquez Web logs
aws ssm send-command --region us-east-2 \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker logs marquez-web --tail 50"]'
```

### Verify SSL Configuration

```bash
aws ssm send-command --region us-east-2 \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cat /opt/marquez/marquez-ssl.yml"]'
```

### Common Issues

#### Targets Unhealthy
- Wait 3-5 minutes after deployment for initialization
- Check security group rules allow ALB → instances traffic
- Verify Docker containers are running
- Check RDS connectivity

#### Cannot Access ALB
- Verify you're accessing from within the VPC
- Check ALB is in "active" state
- Verify security group allows traffic on ports 5000 and 3000
- Confirm ALB is internal (not internet-facing)

#### 502 Bad Gateway
- Targets are unhealthy - check container logs
- Database connection issues - verify RDS is available
- SSL configuration issues - check marquez-ssl.yml

---

## Security Best Practices

### Network Security ✅
- Internal ALB in private subnets
- No public endpoints exposed
- Security groups with least privilege
- VPC flow logs enabled

### Data Security ✅
- RDS encryption at rest
- SSL/TLS for database connections
- Secrets Manager for credentials
- IAM roles instead of access keys

### Access Control ✅
- SSM Session Manager (no SSH keys)
- IAM policies for resource access
- Security group restrictions
- VPC isolation

---

## Cost Optimization

### Estimated Monthly Costs (us-east-2)

| Resource | Configuration | Estimated Cost |
|----------|--------------|----------------|
| RDS PostgreSQL | db.t3.small Multi-AZ | ~$60 |
| EC2 Instances | 2x t3.medium | ~$60 |
| ALB | Internal | ~$20 |
| Data Transfer | Minimal | ~$5 |
| **Total** | | **~$145/month** |

### Cost Reduction Tips
- Use Reserved Instances for predictable workloads
- Enable RDS storage autoscaling
- Use Spot Instances for non-production
- Set up Auto Scaling to scale down during off-hours

---

## Cleanup

To avoid ongoing charges, destroy the stacks when no longer needed:

```bash
# Destroy all HA stacks
cdk destroy mwaa-openlineage-mwaa-ha mwaa-openlineage-marquez-ha mwaa-openlineage-network-ha \
  --app "python3 app_ha.py" \
  --region us-east-2
```

**Note**: This will delete all resources including the RDS database. Ensure you have backups if needed.

---

## Additional Resources

- [ALB_ACCESS_GUIDE.md](ALB_ACCESS_GUIDE.md) - Comprehensive access guide
- [ECR_SETUP_GUIDE.md](ECR_SETUP_GUIDE.md) - Docker image mirroring guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed architecture overview
- [SECURITY.md](SECURITY.md) - Security policy and best practices

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review CloudWatch logs
3. Check target health status
4. Verify security group rules
5. Open an issue on GitHub

---

## License

MIT License - see [LICENSE](../LICENSE) file for details.

