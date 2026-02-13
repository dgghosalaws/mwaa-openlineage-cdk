#!/bin/bash
set -e

echo "========================================="
echo "MWAA + OpenLineage HA Deployment"
echo "========================================="
echo ""

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "Error: AWS CLI is not configured. Please run 'aws configure' first."
    exit 1
fi

# Get AWS account and region
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region || echo "us-east-2")

echo "AWS Account: $AWS_ACCOUNT"
echo "AWS Region: $AWS_REGION"
echo ""

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt
echo ""

# Bootstrap CDK (if not already done)
echo "Bootstrapping CDK..."
cdk bootstrap aws://$AWS_ACCOUNT/$AWS_REGION
echo ""

# Deploy stacks using HA app
echo "Deploying HA stacks..."
echo ""
echo "This will deploy:"
echo "  1. Network Stack (VPC, Subnets, Security Groups)"
echo "  2. Marquez HA Stack (RDS Multi-AZ, ALB, Auto Scaling Group)"
echo "  3. MWAA Stack (Airflow 3.0.6 with OpenLineage)"
echo ""
echo "Estimated deployment time: 45-50 minutes"
echo "  - Network: ~3 minutes"
echo "  - Marquez HA: ~10 minutes (RDS takes time)"
echo "  - MWAA: ~35 minutes"
echo ""

read -p "Continue with deployment? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

# Deploy all stacks
cdk deploy --all --app "python app_ha.py" --require-approval never

echo ""
echo "========================================="
echo "Deployment Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Wait 5-10 minutes for Marquez instances to fully initialize"
echo "2. Access Marquez UI via the ALB URL (port 3000)"
echo "3. Access MWAA Airflow UI via the webserver URL"
echo "4. Run the demo DAG to test lineage capture"
echo ""
echo "To get stack outputs:"
echo "  aws cloudformation describe-stacks --stack-name mwaa-openlineage-marquez-ha --query 'Stacks[0].Outputs'"
echo ""
echo "To destroy all resources:"
echo "  cdk destroy --all --app 'python app_ha.py'"
echo ""
