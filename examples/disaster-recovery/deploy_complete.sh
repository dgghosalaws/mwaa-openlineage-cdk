#!/bin/bash
set -e

echo "=========================================="
echo "MWAA DR Complete Deployment"
echo "=========================================="
echo ""
echo "This script deploys multi-region MWAA infrastructure:"
echo "  - Network infrastructure (VPC, subnets, security groups)"
echo "  - S3 buckets for MWAA assets"
echo "  - MWAA environments in primary (us-east-2) and secondary (us-east-1)"
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
npx cdk deploy MwaaDRNetworkPrimary -c account=$ACCOUNT_ID --require-approval never

echo ""
echo "Deploying S3 bucket stack..."
npx cdk deploy MwaaDRS3Primary -c account=$ACCOUNT_ID --require-approval never

echo ""
echo "=========================================="
echo "Step 2: Deploy Primary MWAA Environment"
echo "=========================================="
echo ""

echo "Deploying MWAA environment (this takes 20-30 minutes)..."
npx cdk deploy MwaaDRMwaaPrimary -c account=$ACCOUNT_ID --require-approval never

echo ""
echo "=========================================="
echo "Step 3: Deploy Secondary Region Infrastructure (us-east-1)"
echo "=========================================="
echo ""

echo "Deploying network stack..."
npx cdk deploy MwaaDRNetworkSecondary -c account=$ACCOUNT_ID --require-approval never

echo ""
echo "Deploying S3 bucket stack..."
npx cdk deploy MwaaDRS3Secondary -c account=$ACCOUNT_ID --require-approval never

echo ""
echo "=========================================="
echo "Step 4: Deploy Secondary MWAA Environment"
echo "=========================================="
echo ""

echo "Deploying MWAA environment (this takes 20-30 minutes)..."
npx cdk deploy MwaaDRMwaaSecondary -c account=$ACCOUNT_ID --require-approval never

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
echo "2. Deploy metadb-backup-restore example for backup/restore + failover:"
echo "   cd ../metadb-backup-restore"
echo "   See README.md for instructions"
echo ""
