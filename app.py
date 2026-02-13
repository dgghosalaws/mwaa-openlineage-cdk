#!/usr/bin/env python3
"""
MWAA with OpenLineage CDK Application

This CDK app creates:
1. Marquez server on EC2 for lineage tracking
2. MWAA environment with OpenLineage integration
3. Sample DAG to demonstrate lineage capture
"""
import aws_cdk as cdk
from stacks.network_stack import NetworkStack
from stacks.marquez_stack import MarquezStack
from stacks.mwaa_stack import MwaaStack

app = cdk.App()

# Get configuration from context or use defaults
env = cdk.Environment(
    account=app.node.try_get_context("account") or None,
    region=app.node.try_get_context("region") or "us-east-1"
)

project_name = app.node.try_get_context("project_name") or "mwaa-openlineage"
environment = app.node.try_get_context("environment") or "dev"

# Stack 1: Network Infrastructure (VPC, Subnets, Security Groups)
network_stack = NetworkStack(
    app,
    f"{project_name}-network-{environment}",
    project_name=project_name,
    environment=environment,
    env=env,
    description="Network infrastructure for MWAA and Marquez"
)

# Stack 2: Marquez Server (EC2 with Docker)
marquez_stack = MarquezStack(
    app,
    f"{project_name}-marquez-{environment}",
    vpc=network_stack.vpc,
    marquez_sg=network_stack.marquez_sg,
    project_name=project_name,
    environment=environment,
    env=env,
    description="Marquez lineage server on EC2"
)

# Stack 3: MWAA Environment with OpenLineage
mwaa_stack = MwaaStack(
    app,
    f"{project_name}-mwaa-{environment}",
    vpc=network_stack.vpc,
    mwaa_sg=network_stack.mwaa_sg,
    marquez_url=marquez_stack.marquez_api_url,
    project_name=project_name,
    environment=environment,
    env=env,
    description="MWAA environment with OpenLineage integration"
)

# Dependencies
marquez_stack.add_dependency(network_stack)
mwaa_stack.add_dependency(network_stack)
mwaa_stack.add_dependency(marquez_stack)

# Tags
cdk.Tags.of(app).add("Project", project_name)
cdk.Tags.of(app).add("Environment", environment)
cdk.Tags.of(app).add("ManagedBy", "CDK")

app.synth()
