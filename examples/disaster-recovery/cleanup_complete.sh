#!/bin/bash
set -e

echo "=========================================="
echo "MWAA DR Complete Cleanup"
echo "=========================================="
echo ""
echo "This script will delete all DR infrastructure:"
echo "  - MWAA environments in both regions"
echo "  - Network infrastructure in both regions"
echo "  - DynamoDB state table"
echo ""
echo "WARNING: This is destructive and cannot be undone!"
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cleanup cancelled"
    exit 0
fi

echo ""
echo "Starting cleanup..."
echo ""

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "=========================================="
echo "Step 1: Delete MWAA Environments"
echo "=========================================="
echo ""

echo "Deleting primary MWAA environment..."
cdk destroy MwaaDRMwaaPrimary --force || echo "Primary MWAA stack not found or already deleted"

echo ""
echo "Deleting secondary MWAA environment..."
cdk destroy MwaaDRMwaaSecondary --force || echo "Secondary MWAA stack not found or already deleted"

echo ""
echo "Waiting for MWAA environments to finish deleting (this takes 10-15 minutes)..."
echo "You can monitor progress in the AWS Console"
echo ""

# Wait for MWAA stacks to be deleted
echo "Checking if MWAA stacks are deleted..."
while true; do
    primary_status=$(aws cloudformation describe-stacks --stack-name MwaaDRMwaaPrimary --region us-east-2 --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DELETED")
    secondary_status=$(aws cloudformation describe-stacks --stack-name MwaaDRMwaaSecondary --region us-east-1 --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DELETED")
    
    if [ "$primary_status" = "DELETED" ] && [ "$secondary_status" = "DELETED" ]; then
        echo "✓ MWAA environments deleted"
        break
    fi
    
    echo "  Primary: $primary_status | Secondary: $secondary_status"
    sleep 30
done

echo ""
echo "=========================================="
echo "Step 2: Delete S3 Buckets"
echo "=========================================="
echo ""

echo "Deleting primary S3 bucket..."
cdk destroy MwaaDRS3Primary --force || echo "Primary S3 stack not found or already deleted"

echo ""
echo "Deleting secondary S3 bucket..."
cdk destroy MwaaDRS3Secondary --force || echo "Secondary S3 stack not found or already deleted"

echo ""
echo "=========================================="
echo "Step 3: Delete DynamoDB State Table"
echo "=========================================="
echo ""

echo "Deleting DynamoDB state table..."
cdk destroy MwaaDRStateStack --force || echo "State table stack not found or already deleted"

echo ""
echo "=========================================="
echo "Step 4: Delete Network Infrastructure"
echo "=========================================="
echo ""

echo "Deleting primary network..."
cdk destroy MwaaDRNetworkPrimary --force || echo "Primary network stack not found or already deleted"

echo ""
echo "Deleting secondary network..."
cdk destroy MwaaDRNetworkSecondary --force || echo "Secondary network stack not found or already deleted"

echo ""
echo "=========================================="
echo "Cleanup Complete!"
echo "=========================================="
echo ""
echo "All DR infrastructure has been deleted."
echo ""
