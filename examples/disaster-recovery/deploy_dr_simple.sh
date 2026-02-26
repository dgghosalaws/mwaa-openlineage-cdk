#!/bin/bash

# Simple DR Deployment Script
# Deploys MWAA in two regions with DAG control based on active region
# Does NOT include backup/restore (requires redesign for Airflow 3.0)

set -e

PROJECT_NAME="mwaa-openlineage"
ENV_NAME="dev"
PRIMARY_REGION="us-east-2"
SECONDARY_REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "=========================================="
echo "MWAA DR Deployment (Simplified)"
echo "=========================================="
echo ""
echo "Project: $PROJECT_NAME"
echo "Environment: $ENV_NAME"
echo "Primary Region: $PRIMARY_REGION"
echo "Secondary Region: $SECONDARY_REGION"
echo "Account: $ACCOUNT_ID"
echo ""
echo "This will deploy:"
echo "  1. DynamoDB state table (tracks active region)"
echo "  2. Primary MWAA environment ($PRIMARY_REGION)"
echo "  3. Secondary MWAA environment ($SECONDARY_REGION)"
echo "  4. DR state plugin (auto pause/unpause DAGs)"
echo ""
echo "NOT included (requires separate implementation):"
echo "  ✗ Metadata backup/restore (Airflow 3.0 limitation)"
echo "  ✗ Automatic failover (manual only)"
echo "  ✗ Data replication (S3, databases)"
echo ""
read -p "Continue with deployment? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Step 1: Deploy DynamoDB State Table
echo ""
echo "=========================================="
echo "Step 1: Deploying DynamoDB State Table"
echo "=========================================="
echo ""

cd stacks
cdk deploy MwaaDRStateStack \
    --region $PRIMARY_REGION \
    --require-approval never

echo "✓ DynamoDB state table deployed"

# Step 2: Initialize DR State
echo ""
echo "=========================================="
echo "Step 2: Initializing DR State"
echo "=========================================="
echo ""

../scripts/init_dr_state.sh $PRIMARY_REGION

echo "✓ DR state initialized (active region: $PRIMARY_REGION)"

# Step 3: Deploy Primary MWAA
echo ""
echo "=========================================="
echo "Step 3: Deploying Primary MWAA"
echo "=========================================="
echo ""

cdk deploy MwaaDRPrimaryStack \
    --region $PRIMARY_REGION \
    --require-approval never

echo "✓ Primary MWAA environment deployed"

# Step 4: Deploy Secondary MWAA
echo ""
echo "=========================================="
echo "Step 4: Deploying Secondary MWAA"
echo "=========================================="
echo ""

cdk deploy MwaaDRSecondaryStack \
    --region $SECONDARY_REGION \
    --require-approval never

echo "✓ Secondary MWAA environment deployed"

# Step 5: Upload DR Plugin
echo ""
echo "=========================================="
echo "Step 5: Uploading DR State Plugin"
echo "=========================================="
echo ""

# Get S3 bucket names
PRIMARY_BUCKET=$(aws mwaa get-environment \
    --name ${PROJECT_NAME}-${ENV_NAME} \
    --region $PRIMARY_REGION \
    --query 'Environment.SourceBucketArn' \
    --output text | cut -d':' -f6)

SECONDARY_BUCKET=$(aws mwaa get-environment \
    --name ${PROJECT_NAME}-minimal-${ENV_NAME} \
    --region $SECONDARY_REGION \
    --query 'Environment.SourceBucketArn' \
    --output text | cut -d':' -f6)

echo "Primary bucket: $PRIMARY_BUCKET"
echo "Secondary bucket: $SECONDARY_BUCKET"
echo ""

# Upload plugin to both regions
aws s3 cp ../assets/plugins/dr_state_plugin.py \
    s3://$PRIMARY_BUCKET/plugins/ \
    --region $PRIMARY_REGION

aws s3 cp ../assets/plugins/dr_state_plugin.py \
    s3://$SECONDARY_BUCKET/plugins/ \
    --region $SECONDARY_REGION

echo "✓ DR state plugin uploaded to both regions"

# Summary
echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "What was deployed:"
echo "  ✓ DynamoDB state table in $PRIMARY_REGION"
echo "  ✓ Primary MWAA in $PRIMARY_REGION (ACTIVE)"
echo "  ✓ Secondary MWAA in $SECONDARY_REGION (STANDBY)"
echo "  ✓ DR state plugin in both regions"
echo ""
echo "Current state:"
echo "  Active region: $PRIMARY_REGION"
echo "  Standby region: $SECONDARY_REGION"
echo ""
echo "Next steps:"
echo "  1. Wait 20-30 minutes for MWAA environments to be AVAILABLE"
echo "  2. Check MWAA status in AWS Console"
echo "  3. Verify plugin in scheduler logs"
echo "  4. Deploy test DAG: aws s3 cp assets/dags/dr_test_dag.py s3://\$PRIMARY_BUCKET/dags/"
echo "  5. Test failover: ./scripts/failover_with_dag_control.sh $SECONDARY_REGION"
echo ""
echo "Airflow UI URLs:"
echo "  Primary: https://$(aws mwaa get-environment --name ${PROJECT_NAME}-${ENV_NAME} --region $PRIMARY_REGION --query 'Environment.WebserverUrl' --output text 2>/dev/null || echo 'pending')"
echo "  Secondary: https://$(aws mwaa get-environment --name ${PROJECT_NAME}-minimal-${ENV_NAME} --region $SECONDARY_REGION --query 'Environment.WebserverUrl' --output text 2>/dev/null || echo 'pending')"
echo ""
echo "Documentation:"
echo "  - README.md - Overview and usage"
echo "  - AIRFLOW3_DR_LIMITATIONS.md - Metadata backup limitations"
echo ""
