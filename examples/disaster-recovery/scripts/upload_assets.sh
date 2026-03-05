#!/bin/bash
set -e

# Upload MWAA assets (plugin, DAGs, requirements) to S3 bucket
# Usage: ./upload_assets.sh <bucket-name> <region>

if [ $# -ne 2 ]; then
    echo "Usage: $0 <bucket-name> <region>"
    echo "Example: $0 mwaa-openlineage-dr-primary-dev-123456789 us-east-2"
    exit 1
fi

BUCKET_NAME=$1
REGION=$2

echo "=========================================="
echo "Uploading MWAA Assets to S3"
echo "=========================================="
echo "Bucket: $BUCKET_NAME"
echo "Region: $REGION"
echo ""

# Check if bucket exists
if ! aws s3 ls "s3://$BUCKET_NAME" --region "$REGION" &> /dev/null; then
    echo "Error: Bucket $BUCKET_NAME does not exist or is not accessible"
    exit 1
fi

# Create temporary directory for plugin zip
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

echo "Step 1: Creating plugin zip file..."
cd assets/plugins
zip -q "$TEMP_DIR/plugins.zip" dr_state_plugin.py
cd ../..
echo "✓ Plugin zip created"

echo ""
echo "Step 2: Uploading plugin to S3..."
aws s3 cp "$TEMP_DIR/plugins.zip" "s3://$BUCKET_NAME/plugins/plugins.zip" --region "$REGION"
echo "✓ Plugin uploaded: s3://$BUCKET_NAME/plugins/plugins.zip"

echo ""
echo "Step 3: Uploading DAGs to S3..."
aws s3 sync assets/dags "s3://$BUCKET_NAME/dags/" --region "$REGION" --delete
echo "✓ DAGs uploaded: s3://$BUCKET_NAME/dags/"

echo ""
echo "Step 4: Uploading requirements.txt to S3..."
aws s3 cp assets/requirements/requirements.txt "s3://$BUCKET_NAME/requirements.txt" --region "$REGION"
echo "✓ Requirements uploaded: s3://$BUCKET_NAME/requirements.txt"

echo ""
echo "=========================================="
echo "Upload Complete!"
echo "=========================================="
echo ""
echo "Verify uploads:"
echo "  aws s3 ls s3://$BUCKET_NAME/plugins/ --region $REGION"
echo "  aws s3 ls s3://$BUCKET_NAME/dags/ --region $REGION"
echo "  aws s3 ls s3://$BUCKET_NAME/requirements.txt --region $REGION"
echo ""
