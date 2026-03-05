#!/bin/bash
set -e

echo "Updating MWAA environments to use plugins..."

# Update primary environment (us-east-2)
echo "Updating primary environment in us-east-2..."
aws mwaa update-environment \
    --name mwaa-openlineage-dr-primary-dev \
    --plugins-s3-path plugins.zip \
    --region us-east-2

# Update secondary environment (us-east-1)
echo "Updating secondary environment in us-east-1..."
aws mwaa update-environment \
    --name mwaa-openlineage-dr-secondary-dev \
    --plugins-s3-path plugins.zip \
    --region us-east-1

echo ""
echo "✓ Update initiated for both environments"
echo ""
echo "Monitor update status:"
echo "  Primary:   aws mwaa get-environment --name mwaa-openlineage-dr-primary-dev --region us-east-2 --query 'Environment.Status'"
echo "  Secondary: aws mwaa get-environment --name mwaa-openlineage-dr-secondary-dev --region us-east-1 --query 'Environment.Status'"
echo ""
echo "This will take 20-30 minutes. Once status is AVAILABLE, the plugin will be active."
