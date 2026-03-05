#!/bin/bash
set -e

echo "=========================================="
echo "MWAA DR Complete Deployment"
echo "=========================================="
echo ""
echo "This script deploys a complete MWAA DR setup:"
echo "  - Network infrastructure (VPC, subnets, security groups)"
echo "  - S3 buckets for MWAA assets"
echo "  - DynamoDB state table for DR coordination"
echo "  - Upload plugin, DAGs, and requirements to S3"
echo "  - MWAA environments in primary (us-east-2) and secondary (us-east-1) regions"
echo "  - DR plugin enabled from deployment"
echo "  - Test DAG for verification"
echo ""
echo "Deployment time: ~40-50 minutes (MWAA takes 20-30 minutes per region)"
echo ""

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "Error: AWS CLI is not configured or credentials are invalid"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Deploying to AWS Account: $ACCOUNT_ID"
echo ""

# Install dependencies if needed
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo ""
echo "=========================================="
echo "Step 1: Deploy Primary Region Infrastructure (us-east-2)"
echo "=========================================="
echo ""

echo "Deploying network stack..."
cdk deploy MwaaDRNetworkPrimary --require-approval never

echo ""
echo "Deploying S3 bucket stack..."
cdk deploy MwaaDRS3Primary --require-approval never

echo ""
echo "Deploying DynamoDB state table..."
cdk deploy MwaaDRStateStack --require-approval never

echo ""
echo "=========================================="
echo "Step 2: Upload Assets to Primary S3 Bucket"
echo "=========================================="
echo ""

# Get bucket name from CDK output
PRIMARY_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name MwaaDRS3Primary \
    --region us-east-2 \
    --query 'Stacks[0].Outputs[?OutputKey==`MwaaBucketName`].OutputValue' \
    --output text)

echo "Primary bucket: $PRIMARY_BUCKET"
./scripts/upload_assets.sh "$PRIMARY_BUCKET" us-east-2

echo ""
echo "=========================================="
echo "Step 3: Deploy Primary MWAA Environment"
echo "=========================================="
echo ""

echo "Deploying MWAA environment (this takes 20-30 minutes)..."
cdk deploy MwaaDRMwaaPrimary --require-approval never

echo ""
echo "=========================================="
echo "Step 4: Deploy Secondary Region Infrastructure (us-east-1)"
echo "=========================================="
echo ""

echo "Deploying network stack..."
cdk deploy MwaaDRNetworkSecondary --require-approval never

echo ""
echo "Deploying S3 bucket stack..."
cdk deploy MwaaDRS3Secondary --require-approval never

echo ""
echo "=========================================="
echo "Step 5: Upload Assets to Secondary S3 Bucket"
echo "=========================================="
echo ""

# Get bucket name from CDK output
SECONDARY_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name MwaaDRS3Secondary \
    --region us-east-1 \
    --query 'Stacks[0].Outputs[?OutputKey==`MwaaBucketName`].OutputValue' \
    --output text)

echo "Secondary bucket: $SECONDARY_BUCKET"
./scripts/upload_assets.sh "$SECONDARY_BUCKET" us-east-1

echo ""
echo "=========================================="
echo "Step 6: Deploy Secondary MWAA Environment"
echo "=========================================="
echo ""

echo "Deploying MWAA environment (this takes 20-30 minutes)..."
cdk deploy MwaaDRMwaaSecondary --require-approval never

echo ""
echo "=========================================="
echo "Step 7: Initialize DR State"
echo "=========================================="
echo ""

echo "Setting us-east-2 as active region..."
./scripts/init_dr_state.sh us-east-2

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Next Steps:"
echo ""
echo "1. Verify MWAA environments are available:"
echo "   Primary:   https://console.aws.amazon.com/mwaa/home?region=us-east-2"
echo "   Secondary: https://console.aws.amazon.com/mwaa/home?region=us-east-1"
echo ""
echo "2. Check DR plugin is working:"
echo "   - Open Airflow UI in both regions"
echo "   - Check scheduler logs for 'DR state checking ENABLED' message"
echo "   - Verify dr_test_dag is running in primary, skipped in secondary"
echo ""
echo "3. Test failover:"
echo "   ./scripts/failover_with_dag_control.sh us-east-1 'Testing failover'"
echo ""
echo "4. Monitor DR state:"
echo "   aws dynamodb get-item \\"
echo "     --table-name mwaa-openlineage-dr-state-dev \\"
echo "     --key '{\"state_id\": {\"S\": \"ACTIVE_REGION\"}}' \\"
echo "     --region us-east-2"
echo ""
