#!/usr/bin/env python3
"""
MWAA with OpenLineage CDK Application

Supports four deployment modes:
1. Standard: Single MWAA + Single Marquez EC2
2. Blue-Green MWAA: Dual MWAA + Single Marquez EC2 (zero-downtime orchestration)
3. HA Marquez: Single MWAA + HA Marquez (ALB + ASG + RDS)
4. Full HA: Dual MWAA + HA Marquez (complete high availability)

Configuration flags in cdk.json:
- enable_blue_green: true/false (MWAA blue-green deployment)
- enable_ha_marquez: true/false (HA Marquez with ALB + ASG + RDS)

This CDK app creates:
1. Network infrastructure (VPC, subnets, security groups)
2. Marquez server (EC2 or HA with ALB + ASG + RDS)
3. MWAA environment(s) with OpenLineage integration
4. (Optional) Blue-Green setup with Parameter Store for zero-downtime switching
"""
import aws_cdk as cdk
from stacks.network_stack import NetworkStack
from stacks.marquez_stack import MarquezStack
from stacks.marquez_ha_stack import MarquezHAStack
from stacks.mwaa_stack import MwaaStack
from stacks.mwaa_blue_green_stack import MwaaBlueGreenStack
from stacks.mwaa_monitoring_stack import MwaaMonitoringStack

app = cdk.App()

# Get configuration from context or use defaults
env = cdk.Environment(
    account=app.node.try_get_context("account") or None,
    region=app.node.try_get_context("region") or "us-east-2"
)

project_name = app.node.try_get_context("project_name") or "mwaa-openlineage"
environment = app.node.try_get_context("environment") or "dev"
enable_blue_green = app.node.try_get_context("enable_blue_green") or False
enable_ha_marquez = app.node.try_get_context("enable_ha_marquez") or False
enable_monitoring = app.node.try_get_context("enable_monitoring")
if enable_monitoring is None:
    enable_monitoring = True  # Enable by default

# MWAA configuration
mwaa_environment_class = app.node.try_get_context("mwaa_environment_class") or "mw1.small"
mwaa_min_workers = app.node.try_get_context("mwaa_min_workers") or 1
mwaa_max_workers = app.node.try_get_context("mwaa_max_workers") or 10

# Determine deployment mode
if enable_blue_green and enable_ha_marquez:
    mode = "Full HA (Blue-Green MWAA + HA Marquez)"
elif enable_blue_green:
    mode = "Blue-Green MWAA"
elif enable_ha_marquez:
    mode = "HA Marquez"
else:
    mode = "Standard"

print(f"\n{'='*60}")
print(f"Deploying MWAA OpenLineage Stack")
print(f"{'='*60}")
print(f"Project: {project_name}")
print(f"Environment: {environment}")
print(f"Region: {env.region}")
print(f"Deployment Mode: {mode}")
print(f"  - Blue-Green MWAA: {'Enabled' if enable_blue_green else 'Disabled'}")
print(f"  - HA Marquez: {'Enabled' if enable_ha_marquez else 'Disabled'}")
print(f"  - CloudWatch Monitoring: {'Enabled' if enable_monitoring else 'Disabled'}")
print(f"MWAA Configuration:")
print(f"  - Environment Class: {mwaa_environment_class}")
print(f"  - Min Workers: {mwaa_min_workers}")
print(f"  - Max Workers: {mwaa_max_workers}")
print(f"{'='*60}\n")

# Stack 1: Network Infrastructure (VPC, Subnets, Security Groups)
network_stack = NetworkStack(
    app,
    f"{project_name}-network-{environment}",
    project_name=project_name,
    environment=environment,
    env=env,
    description="Network infrastructure for MWAA and Marquez"
)

# Stack 2: Marquez Server (EC2 or HA with ALB + ASG + RDS)
if enable_ha_marquez:
    # HA Marquez: ALB + ASG + RDS
    print("Creating HA Marquez deployment (ALB + ASG + RDS)...")
    marquez_stack = MarquezHAStack(
        app,
        f"{project_name}-marquez-ha-{environment}",
        vpc=network_stack.vpc,
        marquez_sg=network_stack.marquez_sg,
        project_name=project_name,
        environment=environment,
        env=env,
        description="HA Marquez lineage server with ALB, ASG, and RDS"
    )
else:
    # Standard Marquez: Single EC2 with Docker
    print("Creating standard Marquez deployment (EC2)...")
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

# Stack 3: MWAA Environment(s) with OpenLineage
if enable_blue_green:
    # Blue-Green deployment: Two MWAA environments with zero-downtime switching
    print("Creating Blue-Green MWAA deployment...")
    mwaa_stack = MwaaBlueGreenStack(
        app,
        f"{project_name}-mwaa-bluegreen-{environment}",
        vpc=network_stack.vpc,
        mwaa_sg=network_stack.mwaa_sg,
        marquez_url=marquez_stack.marquez_api_url,
        project_name=project_name,
        environment=environment,
        env=env,
        description="Blue-Green MWAA environments with zero-downtime switching"
    )
else:
    # Standard deployment: Single MWAA environment
    print("Creating standard MWAA deployment...")
    mwaa_stack = MwaaStack(
        app,
        f"{project_name}-mwaa-{environment}",
        vpc=network_stack.vpc,
        mwaa_sg=network_stack.mwaa_sg,
        marquez_url=marquez_stack.marquez_api_url,
        project_name=project_name,
        environment=environment,
        environment_class=mwaa_environment_class,
        min_workers=mwaa_min_workers,
        max_workers=mwaa_max_workers,
        env=env,
        description="MWAA environment with OpenLineage integration"
    )

# Dependencies
marquez_stack.add_dependency(network_stack)
mwaa_stack.add_dependency(network_stack)
mwaa_stack.add_dependency(marquez_stack)

# Optional: CloudWatch Monitoring Dashboard (enabled by default)
if enable_monitoring:
    print("Creating CloudWatch monitoring dashboard...")
    
    # Get MWAA environment name(s) for monitoring
    if enable_blue_green:
        # Monitor both blue and green environments
        blue_env_name = f"{project_name}-blue-{environment}"
        green_env_name = f"{project_name}-green-{environment}"
        
        # Create monitoring dashboard for Blue environment
        blue_monitoring_stack = MwaaMonitoringStack(
            app,
            f"{project_name}-monitoring-blue-{environment}",
            mwaa_environment_name=blue_env_name,
            project_name=f"{project_name}-blue",
            environment=environment,
            env=env,
            description="CloudWatch dashboard for Blue MWAA environment monitoring"
        )
        blue_monitoring_stack.add_dependency(mwaa_stack)
        
        # Create monitoring dashboard for Green environment
        green_monitoring_stack = MwaaMonitoringStack(
            app,
            f"{project_name}-monitoring-green-{environment}",
            mwaa_environment_name=green_env_name,
            project_name=f"{project_name}-green",
            environment=environment,
            env=env,
            description="CloudWatch dashboard for Green MWAA environment monitoring"
        )
        green_monitoring_stack.add_dependency(mwaa_stack)
        
        print(f"  - Blue environment dashboard: {blue_env_name}")
        print(f"  - Green environment dashboard: {green_env_name}")
    else:
        # Monitor single environment
        mwaa_env_name = f"{project_name}-{environment}"
        
        monitoring_stack = MwaaMonitoringStack(
            app,
            f"{project_name}-monitoring-{environment}",
            mwaa_environment_name=mwaa_env_name,
            project_name=project_name,
            environment=environment,
            env=env,
            description="CloudWatch dashboard for MWAA performance monitoring"
        )
        monitoring_stack.add_dependency(mwaa_stack)
else:
    print("CloudWatch monitoring dashboard disabled (set enable_monitoring: true in cdk.json to enable)")

# Tags
cdk.Tags.of(app).add("Project", project_name)
cdk.Tags.of(app).add("Environment", environment)
cdk.Tags.of(app).add("ManagedBy", "CDK")
if enable_blue_green and enable_ha_marquez:
    cdk.Tags.of(app).add("DeploymentMode", "FullHA")
elif enable_blue_green:
    cdk.Tags.of(app).add("DeploymentMode", "BlueGreen")
elif enable_ha_marquez:
    cdk.Tags.of(app).add("DeploymentMode", "HAMarquez")
else:
    cdk.Tags.of(app).add("DeploymentMode", "Standard")

app.synth()
