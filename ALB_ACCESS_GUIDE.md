# ALB Access Guide

## Overview

The Marquez HA deployment uses an Application Load Balancer (ALB) that can be configured as either internal or internet-facing.

## Configuration Options

### Option 1: Internal ALB (Default - Recommended for Production)

**Security**: ✅ Best security posture - only accessible from within VPC

**Deploy command**:
```bash
cdk deploy mwaa-openlineage-network-ha mwaa-openlineage-marquez-ha \
  --app "python3 app_ha.py" \
  --require-approval never \
  --region us-east-2
```

**Access methods**:

#### 1. Via EC2 Instance (Bastion Host)
```bash
# Launch an EC2 instance in the same VPC (public subnet)
aws ec2 run-instances \
  --region us-east-2 \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.micro \
  --subnet-id <public-subnet-id> \
  --security-group-ids <sg-id> \
  --key-name <your-key> \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=marquez-bastion}]'

# SSH into the instance
ssh -i your-key.pem ec2-user@<public-ip>

# Test the internal ALB
ALB_DNS="internal-mwaa-openlineage-marquez-ha-xxx.us-east-2.elb.amazonaws.com"
curl http://$ALB_DNS:5000/api/v1/namespaces
```

#### 2. Via AWS Systems Manager Session Manager (No SSH Key Needed)
```bash
# Get Marquez instance ID
INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups --region us-east-2 \
  --query 'AutoScalingGroups[?contains(AutoScalingGroupName, `Marquez`)].Instances[0].InstanceId' \
  --output text)

# Start session
aws ssm start-session --region us-east-2 --target $INSTANCE_ID

# Once connected, test locally
curl http://localhost:5000/api/v1/namespaces
```

#### 3. Via AWS Client VPN
If you have AWS Client VPN configured:
```bash
# Connect to VPN, then access directly
curl http://internal-alb-dns:5000/api/v1/namespaces
```

#### 4. Via MWAA (Primary Use Case)
MWAA runs in the same VPC and accesses the internal ALB automatically. No additional configuration needed.

---

### Option 2: Internet-Facing ALB (For Testing/Development)

**Security**: ⚠️ Publicly accessible - use only for testing

**Deploy command**:
```bash
cdk deploy mwaa-openlineage-network-ha mwaa-openlineage-marquez-ha \
  --app "python3 app_ha.py" \
  --context internet_facing=true \
  --require-approval never \
  --region us-east-2
```

**Access method**:
```bash
# Get ALB DNS
ALB_DNS=$(aws cloudformation describe-stacks --region us-east-2 \
  --stack-name mwaa-openlineage-marquez-ha \
  --query 'Stacks[0].Outputs[?OutputKey==`MarquezAlbDnsName`].OutputValue' \
  --output text)

# Access directly from anywhere
curl http://$ALB_DNS:5000/api/v1/namespaces
```

**Security recommendations for internet-facing**:
1. Add IP whitelist to security group
2. Add AWS WAF with rate limiting
3. Add Cognito authentication
4. Use HTTPS with ACM certificate

---

## Recommended Approach by Use Case

### For Production
✅ **Internal ALB** + AWS Client VPN or Direct Connect
- Most secure
- Complies with AWS security standards
- MWAA can access without issues

### For Development/Testing
✅ **Internal ALB** + Bastion Host or SSM Session Manager
- Secure enough for testing
- Easy to set up
- Can be torn down when not needed

### For Quick Testing Only
⚠️ **Internet-Facing ALB** with IP restrictions
- Fast to test
- Must add security controls
- Should not be used long-term

---

## Testing Commands

### Get ALB Information
```bash
# Get ALB DNS name
aws cloudformation describe-stacks --region us-east-2 \
  --stack-name mwaa-openlineage-marquez-ha \
  --query 'Stacks[0].Outputs[?OutputKey==`MarquezAlbDnsName`].OutputValue' \
  --output text

# Get ALB scheme (internal or internet-facing)
aws elbv2 describe-load-balancers --region us-east-2 \
  --names mwaa-openlineage-marquez-ha \
  --query 'LoadBalancers[0].Scheme' \
  --output text
```

### Test API Endpoints
```bash
ALB_DNS="<your-alb-dns>"

# List namespaces
curl http://$ALB_DNS:5000/api/v1/namespaces

# Get API version
curl http://$ALB_DNS:5000/api/v1/version

# Health check
curl http://$ALB_DNS:5000/api/v1/health
```

### Check Target Health
```bash
# Get target group ARN
TG_ARN=$(aws elbv2 describe-target-groups --region us-east-2 \
  --query 'TargetGroups[?contains(TargetGroupName, `Marqu`)].TargetGroupArn' \
  --output text)

# Check health
aws elbv2 describe-target-health --region us-east-2 \
  --target-group-arn $TG_ARN \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' \
  --output table
```

---

## Security Group Configuration

### For Internal ALB
```python
# ALB Security Group
- Ingress: Port 5000 from VPC CIDR (10.0.0.0/16)
- Egress: All traffic

# Instance Security Group  
- Ingress: Port 5000 from ALB Security Group
- Egress: All traffic
```

### For Internet-Facing ALB (with IP restriction)
```python
# ALB Security Group
- Ingress: Port 5000 from YOUR_IP/32 only
- Egress: All traffic

# Instance Security Group
- Ingress: Port 5000 from ALB Security Group
- Egress: All traffic
```

---

## Troubleshooting

### Cannot access internal ALB
1. Verify you're accessing from within the VPC
2. Check security group rules
3. Verify ALB is in "active" state
4. Check target health (both should be "healthy")

### Timeout errors
1. Check if targets are healthy
2. Verify security group allows traffic
3. Check if Marquez containers are running
4. Review CloudWatch logs

### 502 Bad Gateway
1. Targets are unhealthy - check container logs
2. Database connection issues - verify RDS is available
3. SSL configuration issues - check marquez-ssl.yml

---

## Quick Reference

| Access Method | Security | Setup Time | Best For |
|--------------|----------|------------|----------|
| Internal ALB + SSM | ✅ High | 5 min | Testing |
| Internal ALB + Bastion | ✅ High | 10 min | Development |
| Internal ALB + VPN | ✅ Highest | 1 hour | Production |
| Internet-Facing + IP | ⚠️ Medium | 5 min | Quick tests only |
| Internet-Facing + WAF | ⚠️ Medium | 30 min | Not recommended |

---

## Recommendation

For your use case (MWAA OpenLineage tracking):

1. **Deploy with internal ALB** (default)
2. **Use SSM Session Manager** for testing/debugging
3. **Let MWAA access it automatically** (primary use)
4. **No public access needed** - lineage is internal data

This provides the best security posture while maintaining full functionality.
