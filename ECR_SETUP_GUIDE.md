# ECR Setup Guide for Marquez HA (OPTIONAL)

## Overview

**Note**: ECR setup is **optional**. The default deployment uses Docker Hub images and works out of the box.

This guide explains how to mirror Marquez Docker images to Amazon ECR to avoid Docker Hub rate limits in production environments with frequent deployments or many instances.

## Why ECR? (Optional Optimization)

**Current Default**: The deployment uses Docker Hub images directly and works without ECR setup.

**When to use ECR**:
- Production environments with frequent redeployments
- Auto Scaling with many instances (>10)
- Avoiding Docker Hub rate limits

Docker Hub rate limits:
- **Anonymous users**: 100 pulls per 6 hours
- **Authenticated free users**: 200 pulls per 6 hours

For typical deployments with 2-4 instances, Docker Hub is sufficient. Consider ECR when:

By mirroring images to Amazon ECR Private, we:
- ✅ Avoid Docker Hub rate limits
- ✅ Get faster pulls (same AWS region)
- ✅ Enable image scanning for vulnerabilities
- ✅ Have full control over image availability

## Prerequisites

- AWS CLI configured
- Docker installed locally
- Appropriate IAM permissions for ECR

## Step 1: Create ECR Repositories

ECR repositories have already been created:
```bash
aws ecr create-repository --region us-east-2 --repository-name marquez
aws ecr create-repository --region us-east-2 --repository-name marquez-web
aws ecr create-repository --region us-east-2 --repository-name postgres
```

Repository URIs:
- `<YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/marquez`
- `<YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/marquez-web`
- `<YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/postgres`

## Step 2: Mirror Images to ECR

Run the provided script to pull images from Docker Hub and push to ECR:

```bash
cd mwaa-openlineage-cdk
./mirror_images_to_ecr.sh
```

This script will:
1. Login to ECR
2. Pull `marquezproject/marquez:0.42.0` from Docker Hub
3. Tag and push to ECR as `marquez:0.42.0` and `marquez:latest`
4. Pull `marquezproject/marquez-web:0.42.0` from Docker Hub
5. Tag and push to ECR as `marquez-web:0.42.0` and `marquez-web:latest`
6. Pull `postgres:15` from Docker Hub
7. Tag and push to ECR as `postgres:15` and `postgres:latest`

### Manual Steps (if script fails)

```bash
# Login to ECR
aws ecr get-login-password --region us-east-2 | \
  docker login --username AWS --password-stdin \
  <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com

# Pull and push Marquez API
docker pull marquezproject/marquez:0.42.0
docker tag marquezproject/marquez:0.42.0 \
  <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/marquez:0.42.0
docker push <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/marquez:0.42.0

# Pull and push Marquez Web
docker pull marquezproject/marquez-web:0.42.0
docker tag marquezproject/marquez-web:0.42.0 \
  <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/marquez-web:0.42.0
docker push <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/marquez-web:0.42.0

# Pull and push Postgres
docker pull postgres:15
docker tag postgres:15 \
  <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/postgres:15
docker push <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/postgres:15
```

## Step 3: Verify Images in ECR

```bash
# List images in marquez repository
aws ecr describe-images --region us-east-2 --repository-name marquez

# List images in marquez-web repository
aws ecr describe-images --region us-east-2 --repository-name marquez-web

# List images in postgres repository
aws ecr describe-images --region us-east-2 --repository-name postgres
```

## Step 4: Deploy HA Stack

The HA stack has been updated to:
1. Add `AmazonEC2ContainerRegistryReadOnly` policy to instance role
2. Login to ECR before pulling images
3. Use ECR image URLs in docker-compose.yml

Deploy the updated stack:

```bash
cd mwaa-openlineage-cdk
cdk deploy mwaa-openlineage-marquez-ha --app "python3 app_ha.py" --require-approval never --region us-east-2
```

## How It Works

### IAM Permissions
The Marquez instance role now includes:
```python
iam.ManagedPolicy.from_aws_managed_policy_name(
    "AmazonEC2ContainerRegistryReadOnly"
)
```

This allows instances to:
- Authenticate with ECR
- Pull images from ECR repositories

### User Data Script
The user data script now:
1. Gets AWS account ID and region
2. Constructs ECR registry URL
3. Logs in to ECR using instance credentials
4. Uses ECR images in docker-compose.yml

### Docker Compose
Images are now referenced as:
```yaml
services:
  marquez-api:
    image: ${ECR_REGISTRY}/marquez:0.42.0
  marquez-web:
    image: ${ECR_REGISTRY}/marquez-web:0.42.0
  wait-for-db:
    image: ${ECR_REGISTRY}/postgres:15
```

## Troubleshooting

### Image Pull Errors
If instances can't pull images:

1. **Check IAM permissions**:
   ```bash
   aws iam get-role --role-name <marquez-instance-role-name>
   ```

2. **Verify images exist in ECR**:
   ```bash
   aws ecr describe-images --region us-east-2 --repository-name marquez
   ```

3. **Check instance logs**:
   ```bash
   aws ssm send-command --region us-east-2 \
     --instance-ids <instance-id> \
     --document-name "AWS-RunShellScript" \
     --parameters 'commands=["tail -50 /var/log/cloud-init-output.log"]'
   ```

### ECR Login Failures
If ECR login fails on instances:

1. **Verify instance has IAM role attached**
2. **Check security group allows HTTPS (443) outbound**
3. **Verify ECR endpoints are accessible**

### Image Not Found
If specific image version doesn't exist:

```bash
# List available tags
aws ecr list-images --region us-east-2 --repository-name marquez

# Pull and push missing version
docker pull marquezproject/marquez:0.42.0
docker tag marquezproject/marquez:0.42.0 \
  <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/marquez:0.42.0
docker push <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/marquez:0.42.0
```

## Cost Considerations

### ECR Pricing (us-east-2)
- **Storage**: $0.10 per GB-month
- **Data Transfer**: 
  - IN: Free
  - OUT to EC2 in same region: Free
  - OUT to internet: Standard AWS data transfer rates

### Estimated Costs
For Marquez images (~2 GB total):
- Storage: ~$0.20/month
- Data transfer: $0 (same region)

**Total**: ~$0.20/month (negligible compared to avoiding deployment failures)

## Maintenance

### Updating Images
When new Marquez versions are released:

1. Pull new version from Docker Hub
2. Tag and push to ECR
3. Update docker-compose.yml in CDK stack
4. Deploy updated stack

```bash
# Example: Update to version 0.43.0
docker pull marquezproject/marquez:0.43.0
docker tag marquezproject/marquez:0.43.0 \
  <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/marquez:0.43.0
docker push <YOUR-AWS-ACCOUNT-ID>.dkr.ecr.us-east-2.amazonaws.com/marquez:0.43.0
```

### Image Scanning
ECR automatically scans images for vulnerabilities:

```bash
# View scan results
aws ecr describe-image-scan-findings \
  --region us-east-2 \
  --repository-name marquez \
  --image-id imageTag=0.42.0
```

## Benefits Summary

✅ **No rate limits**: Unlimited pulls from ECR
✅ **Faster deployments**: Images pulled from same region
✅ **Better reliability**: No dependency on Docker Hub availability
✅ **Security scanning**: Automatic vulnerability detection
✅ **Cost effective**: ~$0.20/month for all images
✅ **Full control**: Manage image lifecycle independently

## Next Steps

After mirroring images:
1. Run `./mirror_images_to_ecr.sh` to push images to ECR
2. Deploy the updated HA stack
3. Verify containers start successfully
4. Test Marquez API and UI endpoints
5. Run end-to-end lineage capture test
