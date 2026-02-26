#!/bin/bash

# MWAA DR Setup Script - Add to Existing MWAA Environments
# This script adds DR capabilities to your existing MWAA environments
# Does NOT create MWAA environments - they must already exist

set -e

# ============================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================
PRIMARY_MWAA_NAME="mwaa-openlineage-dev"
SECONDARY_MWAA_NAME="mwaa-openlineage-minimal-dev"
PRIMARY_REGION="us-east-2"
SECONDARY_REGION="us-east-1"
STATE_TABLE_NAME="mwaa-openlineage-dr-state-dev"

# ============================================
# DO NOT EDIT BELOW THIS LINE
# ============================================
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "=========================================="
echo "MWAA DR Setup - Add to Existing MWAA"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  Primary MWAA: $PRIMARY_MWAA_NAME ($PRIMARY_REGION)"
echo "  Secondary MWAA: $SECONDARY_MWAA_NAME ($SECONDARY_REGION)"
echo "  State Table: $STATE_TABLE_NAME"
echo "  Account: $ACCOUNT_ID"
echo ""
echo "This script will:"
echo "  1. Verify your existing MWAA environments"
echo "  2. Deploy DynamoDB state table"
echo "  3. Initialize DR state (set active region)"
echo "  4. Upload DR plugin to both MWAA environments"
echo "  5. Trigger MWAA environment updates to load plugin"
echo "  6. Upload test DAG (optional)"
echo ""
echo "IMPORTANT:"
echo "  - MWAA environments must already exist"
echo "  - MWAA will take 20-30 minutes to apply plugin updates"
echo "  - Environments will show 'Updating' status during this time"
echo ""
read -p "Continue with deployment? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# ============================================
# Step 1: Verify MWAA Environments Exist
# ============================================
echo ""
echo "=========================================="
echo "Step 1: Verifying MWAA Environments"
echo "=========================================="
echo ""

PRIMARY_ENV=$(aws mwaa get-environment \
    --name $PRIMARY_MWAA_NAME \
    --region $PRIMARY_REGION \
    --query 'Environment.Name' \
    --output text 2>/dev/null || echo "NOT_FOUND")

SECONDARY_ENV=$(aws mwaa get-environment \
    --name $SECONDARY_MWAA_NAME \
    --region $SECONDARY_REGION \
    --query 'Environment.Name' \
    --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$PRIMARY_ENV" == "NOT_FOUND" ]; then
    echo "✗ Primary MWAA environment not found: $PRIMARY_MWAA_NAME in $PRIMARY_REGION"
    echo ""
    echo "Please create MWAA environment first, then run this script again."
    exit 1
fi

if [ "$SECONDARY_ENV" == "NOT_FOUND" ]; then
    echo "✗ Secondary MWAA environment not found: $SECONDARY_MWAA_NAME in $SECONDARY_REGION"
    echo ""
    echo "Please create MWAA environment first, then run this script again."
    exit 1
fi

echo "✓ Primary MWAA environment found: $PRIMARY_ENV"
echo "✓ Secondary MWAA environment found: $SECONDARY_ENV"

# Get S3 bucket names
PRIMARY_BUCKET=$(aws mwaa get-environment \
    --name $PRIMARY_MWAA_NAME \
    --region $PRIMARY_REGION \
    --query 'Environment.SourceBucketArn' \
    --output text | cut -d':' -f6)

SECONDARY_BUCKET=$(aws mwaa get-environment \
    --name $SECONDARY_MWAA_NAME \
    --region $SECONDARY_REGION \
    --query 'Environment.SourceBucketArn' \
    --output text | cut -d':' -f6)

echo "✓ Primary S3 bucket: $PRIMARY_BUCKET"
echo "✓ Secondary S3 bucket: $SECONDARY_BUCKET"

# ============================================
# Step 2: Deploy DynamoDB State Table
# ============================================
echo ""
echo "=========================================="
echo "Step 2: Deploying DynamoDB State Table"
echo "=========================================="
echo ""

# Check if table already exists
TABLE_EXISTS=$(aws dynamodb describe-table \
    --table-name $STATE_TABLE_NAME \
    --region $PRIMARY_REGION \
    --query 'Table.TableName' \
    --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$TABLE_EXISTS" != "NOT_FOUND" ]; then
    echo "✓ DynamoDB table already exists: $STATE_TABLE_NAME"
else
    echo "Creating DynamoDB table: $STATE_TABLE_NAME"
    
    aws dynamodb create-table \
        --table-name $STATE_TABLE_NAME \
        --attribute-definitions AttributeName=state_id,AttributeType=S \
        --key-schema AttributeName=state_id,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region $PRIMARY_REGION \
        --tags Key=Project,Value=mwaa-dr Key=Environment,Value=dev \
        > /dev/null
    
    echo "Waiting for table to be active..."
    aws dynamodb wait table-exists \
        --table-name $STATE_TABLE_NAME \
        --region $PRIMARY_REGION
    
    echo "✓ DynamoDB state table created"
fi

# ============================================
# Step 3: Initialize DR State
# ============================================
echo ""
echo "=========================================="
echo "Step 3: Initializing DR State"
echo "=========================================="
echo ""

# Check if state already exists
STATE_EXISTS=$(aws dynamodb get-item \
    --table-name $STATE_TABLE_NAME \
    --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
    --region $PRIMARY_REGION \
    --query 'Item.active_region.S' \
    --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$STATE_EXISTS" != "NOT_FOUND" ]; then
    echo "✓ DR state already initialized"
    echo "  Current active region: $STATE_EXISTS"
else
    echo "Initializing DR state with active region: $PRIMARY_REGION"
    
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    aws dynamodb put-item \
        --table-name $STATE_TABLE_NAME \
        --item "{
            \"state_id\": {\"S\": \"ACTIVE_REGION\"},
            \"active_region\": {\"S\": \"$PRIMARY_REGION\"},
            \"last_updated\": {\"S\": \"$TIMESTAMP\"},
            \"failover_count\": {\"N\": \"0\"},
            \"version\": {\"N\": \"1\"}
        }" \
        --region $PRIMARY_REGION \
        > /dev/null
    
    echo "✓ DR state initialized (active region: $PRIMARY_REGION)"
fi

# ============================================
# Step 4: Upload DR Plugin
# ============================================
echo ""
echo "=========================================="
echo "Step 4: Uploading DR State Plugin"
echo "=========================================="
echo ""

# Upload plugin to both regions
echo "Uploading plugin to primary region..."
aws s3 cp assets/plugins/dr_state_plugin.py \
    s3://$PRIMARY_BUCKET/plugins/ \
    --region $PRIMARY_REGION

echo "Uploading plugin to secondary region..."
aws s3 cp assets/plugins/dr_state_plugin.py \
    s3://$SECONDARY_BUCKET/plugins/ \
    --region $SECONDARY_REGION

echo "✓ DR state plugin uploaded to both regions"

# ============================================
# Step 5: Trigger MWAA Environment Updates
# ============================================
echo ""
echo "=========================================="
echo "Step 5: Triggering MWAA Environment Updates"
echo "=========================================="
echo ""

echo "Triggering primary environment update..."
aws mwaa update-environment \
    --name $PRIMARY_MWAA_NAME \
    --region $PRIMARY_REGION \
    --plugins-s3-path plugins/dr_state_plugin.py \
    > /dev/null 2>&1 || echo "Note: Primary environment may already be updating"

echo "Triggering secondary environment update..."
aws mwaa update-environment \
    --name $SECONDARY_MWAA_NAME \
    --region $SECONDARY_REGION \
    --plugins-s3-path plugins/dr_state_plugin.py \
    > /dev/null 2>&1 || echo "Note: Secondary environment may already be updating"

echo "✓ Environment updates triggered"
echo ""
echo "IMPORTANT: MWAA will take 20-30 minutes to apply the plugin update"
echo "           Environments will show 'Updating' status during this time"

# ============================================
# Step 6: Upload Test DAG (Optional)
# ============================================
echo ""
echo "=========================================="
echo "Step 6: Upload Test DAG (Optional)"
echo "=========================================="
echo ""
read -p "Upload test DAG to verify DR plugin? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Uploading test DAG to primary region..."
    aws s3 cp assets/dags/dr_test_dag.py \
        s3://$PRIMARY_BUCKET/dags/ \
        --region $PRIMARY_REGION
    
    echo "Uploading test DAG to secondary region..."
    aws s3 cp assets/dags/dr_test_dag.py \
        s3://$SECONDARY_BUCKET/dags/ \
        --region $SECONDARY_REGION
    
    echo "✓ Test DAG uploaded to both regions"
    echo "  MWAA will detect the DAG within 30 seconds"
else
    echo "Skipped test DAG upload"
fi

# ============================================
# Summary
# ============================================
echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "What was deployed:"
echo "  ✓ DynamoDB state table: $STATE_TABLE_NAME"
echo "  ✓ DR plugin uploaded to both MWAA environments"
echo "  ✓ MWAA environment updates triggered"
echo ""
echo "Current state:"
echo "  Active region: $PRIMARY_REGION"
echo "  Standby region: $SECONDARY_REGION"
echo ""
echo "Next steps:"
echo "  1. Wait 20-30 minutes for MWAA environments to be AVAILABLE"
echo "  2. Check MWAA status:"
echo "     aws mwaa get-environment --name $PRIMARY_MWAA_NAME --region $PRIMARY_REGION --query 'Environment.Status'"
echo "  3. Verify plugin in Airflow scheduler logs (CloudWatch)"
echo "  4. Check test DAG status in Airflow UI (if uploaded)"
echo "  5. Test failover:"
echo "     ./scripts/failover_with_dag_control.sh $SECONDARY_REGION 'Testing failover'"
echo ""
echo "Airflow UI URLs:"
PRIMARY_URL=$(aws mwaa get-environment --name $PRIMARY_MWAA_NAME --region $PRIMARY_REGION --query 'Environment.WebserverUrl' --output text 2>/dev/null || echo 'pending')
SECONDARY_URL=$(aws mwaa get-environment --name $SECONDARY_MWAA_NAME --region $SECONDARY_REGION --query 'Environment.WebserverUrl' --output text 2>/dev/null || echo 'pending')
echo "  Primary: https://$PRIMARY_URL"
echo "  Secondary: https://$SECONDARY_URL"
echo ""
echo "Documentation:"
echo "  - README.md - Overview and usage"
echo "  - AIRFLOW3_DR_LIMITATIONS.md - Metadata backup limitations"
echo ""
