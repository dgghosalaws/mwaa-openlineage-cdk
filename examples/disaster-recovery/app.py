#!/usr/bin/env python3
"""
MWAA DR Example - Complete CDK App

This app deploys a multi-region MWAA setup:
- Network infrastructure in both regions
- S3 buckets for MWAA assets in both regions
- MWAA environments in both regions
- Test DAG for verification

Deployment order:
1. Deploy S3 buckets
2. Upload assets (plugin, DAGs, requirements) to S3
3. Deploy MWAA environments
"""
import aws_cdk as cdk
from stacks.dr_network_stack import DRNetworkStack
from stacks.dr_s3_stack import DRS3Stack
from stacks.dr_mwaa_stack import DRMwaaStack

app = cdk.App()

# Configuration
PROJECT_NAME = "mwaa-openlineage"
ENV_NAME = "dev"
PRIMARY_REGION = "us-east-2"
SECONDARY_REGION = "us-east-1"

# Get AWS account from environment
account = app.node.try_get_context("account") or cdk.Aws.ACCOUNT_ID

# ============================================================================
# PRIMARY REGION (us-east-2)
# ============================================================================

# Network Stack - Primary
primary_network = DRNetworkStack(
    app,
    "MwaaDRNetworkPrimary",
    project_name=PROJECT_NAME,
    env_name=ENV_NAME,
    env=cdk.Environment(account=account, region=PRIMARY_REGION),
    description="MWAA DR Network - Primary Region (us-east-2)"
)

# S3 Bucket Stack - Primary
primary_s3 = DRS3Stack(
    app,
    "MwaaDRS3Primary",
    project_name=PROJECT_NAME,
    env_name=ENV_NAME,
    region_name="primary",
    env=cdk.Environment(account=account, region=PRIMARY_REGION),
    description="MWAA DR S3 Bucket - Primary Region (us-east-2)"
)

# MWAA Stack - Primary
# Note: Requires assets to be uploaded to S3 first
primary_mwaa = DRMwaaStack(
    app,
    "MwaaDRMwaaPrimary",
    vpc=primary_network.vpc,
    mwaa_sg=primary_network.mwaa_sg,
    mwaa_bucket=primary_s3.mwaa_bucket,
    project_name=PROJECT_NAME,
    env_name=ENV_NAME,
    region_name="primary",
    primary_region=PRIMARY_REGION,
    environment_class="mw1.small",
    min_workers=1,
    max_workers=2,
    env=cdk.Environment(account=account, region=PRIMARY_REGION),
    description="MWAA DR Environment - Primary Region (us-east-2)"
)
primary_mwaa.add_dependency(primary_network)
primary_mwaa.add_dependency(primary_s3)

# ============================================================================
# SECONDARY REGION (us-east-1)
# ============================================================================

# Network Stack - Secondary
secondary_network = DRNetworkStack(
    app,
    "MwaaDRNetworkSecondary",
    project_name=PROJECT_NAME,
    env_name=ENV_NAME,
    env=cdk.Environment(account=account, region=SECONDARY_REGION),
    description="MWAA DR Network - Secondary Region (us-east-1)"
)

# S3 Bucket Stack - Secondary
secondary_s3 = DRS3Stack(
    app,
    "MwaaDRS3Secondary",
    project_name=PROJECT_NAME,
    env_name=ENV_NAME,
    region_name="secondary",
    env=cdk.Environment(account=account, region=SECONDARY_REGION),
    description="MWAA DR S3 Bucket - Secondary Region (us-east-1)"
)

# MWAA Stack - Secondary
# Note: Requires assets to be uploaded to S3 first
secondary_mwaa = DRMwaaStack(
    app,
    "MwaaDRMwaaSecondary",
    vpc=secondary_network.vpc,
    mwaa_sg=secondary_network.mwaa_sg,
    mwaa_bucket=secondary_s3.mwaa_bucket,
    project_name=PROJECT_NAME,
    env_name=ENV_NAME,
    region_name="secondary",
    primary_region=PRIMARY_REGION,
    environment_class="mw1.small",
    min_workers=1,
    max_workers=2,
    env=cdk.Environment(account=account, region=SECONDARY_REGION),
    description="MWAA DR Environment - Secondary Region (us-east-1)"
)
secondary_mwaa.add_dependency(secondary_network)
secondary_mwaa.add_dependency(secondary_s3)

app.synth()
