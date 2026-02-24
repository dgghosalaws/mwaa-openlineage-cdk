#!/bin/bash
set -e

# OPTIONAL: Setup ECR with Marquez images for HA deployment
# 
# NOTE: This script is OPTIONAL. The default deployment uses Docker Hub
# images and works without ECR setup. Use this only if you need to avoid
# Docker Hub rate limits in production environments.
#
# This script pulls Marquez images from Docker Hub and pushes to ECR

REGION=${1:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
REPOSITORY_NAME="mwaa-openlineage-marquez"
MARQUEZ_VERSION="0.42.0"

echo "============================================================"
echo "Setting up ECR for Marquez HA Deployment"
echo "============================================================"
echo "Region: ${REGION}"
echo "Account: ${ACCOUNT_ID}"
echo "ECR Registry: ${ECR_REGISTRY}"
echo "Marquez Version: ${MARQUEZ_VERSION}"
echo "============================================================"

# Step 1: Create ECR repository if it doesn't exist
echo ""
echo "Step 1: Creating ECR repository..."
aws ecr create-repository \
    --repository-name ${REPOSITORY_NAME} \
    --region ${REGION} \
    --image-scanning-configuration scanOnPush=true \
    --encryption-configuration encryptionType=AES256 \
    2>/dev/null || echo "Repository already exists"

# Step 2: Login to ECR
echo ""
echo "Step 2: Logging in to ECR..."
aws ecr get-login-password --region ${REGION} | \
    docker login --username AWS --password-stdin ${ECR_REGISTRY}

# Step 3: Pull Marquez images from Docker Hub
echo ""
echo "Step 3: Pulling Marquez images from Docker Hub..."
echo "  - Pulling marquezproject/marquez:${MARQUEZ_VERSION}..."
docker pull marquezproject/marquez:${MARQUEZ_VERSION}

echo "  - Pulling marquezproject/marquez-web:${MARQUEZ_VERSION}..."
docker pull marquezproject/marquez-web:${MARQUEZ_VERSION}

# Step 4: Tag images for ECR
echo ""
echo "Step 4: Tagging images for ECR..."
docker tag marquezproject/marquez:${MARQUEZ_VERSION} \
    ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-${MARQUEZ_VERSION}

docker tag marquezproject/marquez-web:${MARQUEZ_VERSION} \
    ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-web-${MARQUEZ_VERSION}

# Also tag as latest
docker tag marquezproject/marquez:${MARQUEZ_VERSION} \
    ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-latest

docker tag marquezproject/marquez-web:${MARQUEZ_VERSION} \
    ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-web-latest

# Step 5: Push images to ECR
echo ""
echo "Step 5: Pushing images to ECR..."
echo "  - Pushing marquez:${MARQUEZ_VERSION}..."
docker push ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-${MARQUEZ_VERSION}

echo "  - Pushing marquez-web:${MARQUEZ_VERSION}..."
docker push ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-web-${MARQUEZ_VERSION}

echo "  - Pushing marquez:latest..."
docker push ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-latest

echo "  - Pushing marquez-web:latest..."
docker push ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-web-latest

# Step 6: Verify images in ECR
echo ""
echo "Step 6: Verifying images in ECR..."
aws ecr list-images \
    --repository-name ${REPOSITORY_NAME} \
    --region ${REGION} \
    --output table

echo ""
echo "============================================================"
echo "✓ ECR Setup Complete!"
echo "============================================================"
echo ""
echo "Images available in ECR:"
echo "  - ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-${MARQUEZ_VERSION}"
echo "  - ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-web-${MARQUEZ_VERSION}"
echo "  - ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-latest"
echo "  - ${ECR_REGISTRY}/${REPOSITORY_NAME}:marquez-web-latest"
echo ""
echo "You can now deploy HA Marquez with:"
echo "  cdk deploy --all"
echo "============================================================"
