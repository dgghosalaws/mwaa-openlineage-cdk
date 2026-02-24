#!/bin/bash
set -e

echo "=========================================="
echo "MWAA OpenLineage Stack Cleanup"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get configuration
ENABLE_BLUE_GREEN=$(grep -A 1 '"enable_blue_green"' cdk.json | tail -1 | grep -o 'true\|false')

echo -e "${YELLOW}Current Configuration:${NC}"
echo "  Blue-Green Mode: $ENABLE_BLUE_GREEN"
echo ""

# Confirm with user
echo -e "${RED}WARNING: This will destroy all stacks and resources!${NC}"
echo ""
echo "This will delete:"
echo "  - All MWAA environments"
echo "  - Marquez server"
echo "  - VPC and networking"
echo "  - S3 buckets (with all DAGs and logs)"
echo "  - Parameter Store parameters"
echo ""

read -p "Are you sure you want to continue? (type 'yes' to confirm): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo "Starting cleanup..."
echo ""

# Destroy stacks based on mode
if [ "$ENABLE_BLUE_GREEN" = "true" ]; then
    echo -e "${YELLOW}Destroying Blue-Green deployment...${NC}"
    
    # Destroy MWAA Blue-Green stack
    echo "1. Destroying MWAA Blue-Green stack..."
    cdk destroy mwaa-openlineage-mwaa-bluegreen-dev --force || echo "Stack not found or already deleted"
    
else
    echo -e "${YELLOW}Destroying Standard deployment...${NC}"
    
    # Destroy MWAA stack
    echo "1. Destroying MWAA stack..."
    cdk destroy mwaa-openlineage-mwaa-dev --force || echo "Stack not found or already deleted"
fi

# Destroy Marquez stack
echo "2. Destroying Marquez stack..."
cdk destroy mwaa-openlineage-marquez-dev --force || echo "Stack not found or already deleted"

# Destroy Network stack
echo "3. Destroying Network stack..."
cdk destroy mwaa-openlineage-network-dev --force || echo "Stack not found or already deleted"

echo ""
echo -e "${GREEN}✓ Cleanup complete!${NC}"
echo ""
echo "All stacks have been destroyed."
echo ""
echo "Note: Some resources may take a few minutes to fully delete:"
echo "  - S3 buckets (emptying objects)"
echo "  - VPC (detaching network interfaces)"
echo "  - CloudWatch log groups (retention period)"
echo ""
