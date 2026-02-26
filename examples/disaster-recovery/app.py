#!/usr/bin/env python3
"""
MWAA DR Example - CDK App

This app deploys only the DynamoDB state table for DR.
MWAA environments must already exist - this does not create them.
"""
import aws_cdk as cdk
from stacks.mwaa_dr_state_stack import MwaaDRStateStack

app = cdk.App()

# Configuration
PROJECT_NAME = "mwaa-openlineage"
ENV_NAME = "dev"
PRIMARY_REGION = "us-east-2"

# Deploy DynamoDB state table
MwaaDRStateStack(
    app,
    "MwaaDRStateStack",
    project_name=PROJECT_NAME,
    env_name=ENV_NAME,
    env=cdk.Environment(region=PRIMARY_REGION),
    description="MWAA DR State Management - DynamoDB table for active region tracking"
)

app.synth()
