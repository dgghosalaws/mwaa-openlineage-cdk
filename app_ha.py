#!/usr/bin/env python3
"""
MWAA with OpenLineage CDK Application - High Availability Version

This CDK app creates:
1. Marquez HA setup with RDS Multi-AZ, ALB, and Auto Scaling Group
2. MWAA environment with OpenLineage integration
3. Sample DAG to demonstrate lineage capture

Key differences from standard deployment:
- RDS PostgreSQL Multi-AZ instead of containerized database
- Application Load Balancer for high availability
- Auto Scaling Group with 2-4 instances
- Enhanced monitoring and health checks
"""
import aws_cdk as cdk
from stacks.network_stack import NetworkStack
from stacks.marquez_ha_stack import MarquezHAStack
from stacks.mwaa_stack import MwaaStack

app = cdk.App()

# Get configuration from context or use defaults
env = cdk.Environment(
    account=app.node.try_get_context("account") or None,
    region=app.node.try_get_context("region") or "us-east-2"
)

project_name = "mwaa-openlineage"
environment = "ha"  # Force HA environment name

# ALB configuration - set to True for internet-facing (testing), False for internal (production)
internet_facing_alb = app.node.try_get_context("internet_facing") or False

# Stack 1: Network Infrastructure (VPC, Subnets, Security Groups)
network_stack = NetworkStack(
    app,
    f"{project_name}-network-{environment}",
    project_name=project_name,
    environment=environment,
    env=env,
    description="Network infrastructure for MWAA and Marquez HA"
)

# Stack 2: Marquez HA Server (RDS + ALB + ASG)
marquez_stack = MarquezHAStack(
    app,
    f"{project_name}-marquez-{environment}",
    vpc=network_stack.vpc,
    marquez_sg=network_stack.marquez_sg,
    project_name=project_name,
    environment=environment,
    internet_facing=internet_facing_alb,
    env=env,
    description="Marquez HA lineage server with RDS, ALB, and Auto Scaling"
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
    description="MWAA environment with OpenLineage integration (HA)"
)

# Dependencies
marquez_stack.add_dependency(network_stack)
mwaa_stack.add_dependency(network_stack)
mwaa_stack.add_dependency(marquez_stack)

# Tags
cdk.Tags.of(app).add("Project", project_name)
cdk.Tags.of(app).add("Environment", environment)
cdk.Tags.of(app).add("ManagedBy", "CDK")
cdk.Tags.of(app).add("HighAvailability", "true")

app.synth()
