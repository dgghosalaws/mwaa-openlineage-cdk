# Quick Access Guide - Internal ALB

## TL;DR

The Marquez HA deployment uses an **internal ALB** that's only accessible from within the VPC. Use SSM Session Manager for quick testing.

---

## Quick Test Commands

### Get ALB DNS and Instance ID

```bash
# Set region
export AWS_REGION=us-east-2

# Get ALB DNS
export ALB_DNS=$(aws cloudformation describe-stacks --region $AWS_REGION \
  --stack-name mwaa-openlineage-marquez-ha \
  --query 'Stacks[0].Outputs[?OutputKey==`MarquezAlbDnsName`].OutputValue' \
  --output text)

# Get instance ID
export INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups --region $AWS_REGION \
  --query 'AutoScalingGroups[?contains(AutoScalingGroupName, `Marquez`)].Instances[0].InstanceId' \
  --output text)

echo "ALB DNS: $ALB_DNS"
echo "Instance ID: $INSTANCE_ID"
```

### Test API (Port 5000)

```bash
# Send command
COMMAND_ID=$(aws ssm send-command --region $AWS_REGION \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"curl -s http://$ALB_DNS:5000/api/v1/namespaces | jq .\"]" \
  --query 'Command.CommandId' \
  --output text)

# Wait and get output
sleep 5
aws ssm get-command-invocation --region $AWS_REGION \
  --command-id $COMMAND_ID \
  --instance-id $INSTANCE_ID \
  --query 'StandardOutputContent' \
  --output text
```

### Test UI (Port 3000)

```bash
# Send command
COMMAND_ID=$(aws ssm send-command --region $AWS_REGION \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"curl -s -I http://$ALB_DNS:3000/ | head -10\"]" \
  --query 'Command.CommandId' \
  --output text)

# Wait and get output
sleep 5
aws ssm get-command-invocation --region $AWS_REGION \
  --command-id $COMMAND_ID \
  --instance-id $INSTANCE_ID \
  --query 'StandardOutputContent' \
  --output text
```

---

## Check Health Status

```bash
# Get target group ARNs
aws elbv2 describe-target-groups --region $AWS_REGION \
  --query 'TargetGroups[?contains(TargetGroupName, `Marqu`)].{Name:TargetGroupName,ARN:TargetGroupArn,Port:Port}' \
  --output table

# Check API target health (port 5000)
API_TG_ARN=$(aws elbv2 describe-target-groups --region $AWS_REGION \
  --query 'TargetGroups[?Port==`5000` && contains(TargetGroupName, `Marqu`)].TargetGroupArn' \
  --output text)

aws elbv2 describe-target-health --region $AWS_REGION \
  --target-group-arn $API_TG_ARN \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' \
  --output table

# Check UI target health (port 3000)
UI_TG_ARN=$(aws elbv2 describe-target-groups --region $AWS_REGION \
  --query 'TargetGroups[?Port==`3000` && contains(TargetGroupName, `Marqu`)].TargetGroupArn' \
  --output text)

aws elbv2 describe-target-health --region $AWS_REGION \
  --target-group-arn $UI_TG_ARN \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' \
  --output table
```

---

## View Logs

```bash
# Marquez API logs
COMMAND_ID=$(aws ssm send-command --region $AWS_REGION \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker logs marquez-api --tail 50"]' \
  --query 'Command.CommandId' \
  --output text)

sleep 5
aws ssm get-command-invocation --region $AWS_REGION \
  --command-id $COMMAND_ID \
  --instance-id $INSTANCE_ID \
  --query 'StandardOutputContent' \
  --output text

# Marquez Web logs
COMMAND_ID=$(aws ssm send-command --region $AWS_REGION \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker logs marquez-web --tail 50"]' \
  --query 'Command.CommandId' \
  --output text)

sleep 5
aws ssm get-command-invocation --region $AWS_REGION \
  --command-id $COMMAND_ID \
  --instance-id $INSTANCE_ID \
  --query 'StandardOutputContent' \
  --output text
```

---

## Access from MWAA

MWAA runs in the same VPC and can access the ALB directly:

```python
# In your Airflow DAG or configuration
MARQUEZ_URL = f"http://{ALB_DNS}:5000"

# Example: Configure OpenLineage transport
from airflow.providers.openlineage.conf import transport

transport = {
    "type": "http",
    "url": MARQUEZ_URL,
    "endpoint": "api/v1/lineage",
}
```

---

## Troubleshooting

### Targets Unhealthy?
```bash
# Check if containers are running
aws ssm send-command --region $AWS_REGION \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["docker ps"]'
```

### Cannot Connect to RDS?
```bash
# Check SSL configuration
aws ssm send-command --region $AWS_REGION \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cat /opt/marquez/marquez-ssl.yml | grep url"]'
```

### Need to Restart Marquez?
```bash
# Restart containers
aws ssm send-command --region $AWS_REGION \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/marquez && docker compose restart"]'
```

---

## URLs

**Example Deployment**:
- **ALB DNS**: `internal-<stack-name>-<random-id>.us-east-2.elb.amazonaws.com`
- **API**: `http://<ALB-DNS>:5000`
- **UI**: `http://internal-mwaa-openlineage-marquez-ha-695869712.us-east-2.elb.amazonaws.com:3000`

---

## For More Details

- [README_HA_DEPLOYMENT.md](README_HA_DEPLOYMENT.md) - Complete deployment guide
- [ALB_ACCESS_GUIDE.md](ALB_ACCESS_GUIDE.md) - Detailed access methods
- [DEPLOYMENT_SUCCESS_FEB13.md](DEPLOYMENT_SUCCESS_FEB13.md) - Latest deployment status

