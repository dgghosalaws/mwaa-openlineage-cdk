# Accessing Marquez in Private Subnet

Since Marquez is deployed in a private subnet for security, it's not directly accessible from the internet. Here are the methods to access it:

## Method 1: Via SSM Session Manager (Recommended)

No SSH keys or bastion hosts needed. Uses AWS Systems Manager.

### Access Marquez API

```bash
# Get instance ID
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-marquez-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`MarquezInstanceId`].OutputValue' \
  --output text)

# Get Marquez private IP
MARQUEZ_IP=$(aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-marquez-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`MarquezPrivateIp`].OutputValue' \
  --output text)

# Test API
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"curl -s http://$MARQUEZ_IP:5000/api/v1/namespaces\"]" \
  --query 'Command.CommandId' \
  --output text
```

### Access Marquez UI

Since the UI is in a private subnet, you'll need to use port forwarding:

```bash
# Start SSM session with port forwarding
aws ssm start-session \
  --target $INSTANCE_ID \
  --document-name AWS-StartPortForwardingSession \
  --parameters "portNumber=3000,localPortNumber=3000"
```

Then open your browser to: http://localhost:3000

## Method 2: Via EC2 Bastion Host

Launch a bastion host in a public subnet:

```bash
# Get VPC ID
VPC_ID=$(aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-network-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`VpcId`].OutputValue' \
  --output text)

# Get public subnet
PUBLIC_SUBNET=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:aws-cdk:subnet-type,Values=Public" \
  --query 'Subnets[0].SubnetId' \
  --output text)

# Launch bastion (replace with your key pair name)
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.micro \
  --subnet-id $PUBLIC_SUBNET \
  --key-name YOUR-KEY-NAME \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=marquez-bastion}]'
```

Then SSH to bastion and access Marquez from there.

## Method 3: Via AWS Client VPN

For production environments, set up AWS Client VPN:

1. Create Client VPN endpoint in the VPC
2. Associate with private subnets
3. Configure authentication (Active Directory or certificate-based)
4. Download VPN configuration
5. Connect and access Marquez directly

## Method 4: Via MWAA (Primary Use Case)

MWAA runs in the same VPC and can access Marquez automatically. No additional configuration needed.

## Allowing External Access (Development Only)

If you need to temporarily allow access from your IP for testing:

### Allow API Access (Port 5000)

```bash
# Get your IP
MY_IP=$(curl -s https://checkip.amazonaws.com)

# Get Marquez security group ID
SG_ID=$(aws cloudformation describe-stacks \
  --stack-name mwaa-openlineage-network-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`MarquezSecurityGroupId`].OutputValue' \
  --output text)

# Allow your IP to access API
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --ip-permissions IpProtocol=tcp,FromPort=5000,ToPort=5000,IpRanges="[{CidrIp=$MY_IP/32,Description='My IP for API access'}]"
```

### Allow UI Access (Port 3000)

```bash
# Allow your IP to access UI
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --ip-permissions IpProtocol=tcp,FromPort=3000,ToPort=3000,IpRanges="[{CidrIp=$MY_IP/32,Description='My IP for UI access'}]"
```

### Allow SSH Access (Port 22)

```bash
# Allow your IP for SSH
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 22 \
  --cidr $MY_IP/32 \
  --description "SSH access from my IP"
```

### Remove Access When Done

```bash
# Revoke API access
aws ec2 revoke-security-group-ingress \
  --group-id $SG_ID \
  --ip-permissions IpProtocol=tcp,FromPort=5000,ToPort=5000,IpRanges="[{CidrIp=$MY_IP/32}]"

# Revoke UI access
aws ec2 revoke-security-group-ingress \
  --group-id $SG_ID \
  --ip-permissions IpProtocol=tcp,FromPort=3000,ToPort=3000,IpRanges="[{CidrIp=$MY_IP/32}]"

# Revoke SSH access
aws ec2 revoke-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 22 \
  --cidr $MY_IP/32
```

## Security Best Practices

1. **Never allow 0.0.0.0/0** for SSH, API, or UI access
2. **Use SSM Session Manager** instead of SSH when possible
3. **Remove temporary rules** after testing
4. **Use VPN or bastion** for production access
5. **Monitor security group changes** with CloudTrail
6. **Rotate credentials** regularly
7. **Enable VPC Flow Logs** for network monitoring

## Troubleshooting

### Cannot connect via SSM

- Ensure SSM agent is running on the instance
- Check IAM role has `AmazonSSMManagedInstanceCore` policy
- Verify instance is in a private subnet with NAT Gateway

### Cannot access Marquez API

- Check security group rules allow traffic from your source
- Verify Marquez containers are running: `docker ps`
- Check Marquez logs: `docker logs marquez-api`

### Port forwarding not working

- Ensure AWS CLI is up to date
- Check Session Manager plugin is installed
- Verify your IAM user has SSM permissions
