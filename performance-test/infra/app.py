#!/usr/bin/env python3
"""
Performance Test MWAA Infrastructure

Deploys a standalone MWAA environment for performance testing.
No Marquez/OpenLineage — just network + MWAA.

Usage:
    cd performance-test/infra
    cdk deploy --all
"""
import aws_cdk as cdk
from network_stack import PerfTestNetworkStack
from mwaa_perf_stack import MwaaPerfStack

app = cdk.App()

env_name = app.node.try_get_context("env_name") or "perf-test"
region = app.node.try_get_context("region") or "us-east-2"
account = app.node.try_get_context("account") or None
env_class = app.node.try_get_context("environment_class") or "mw1.2xlarge"
min_workers = app.node.try_get_context("min_workers") or 20
max_workers = app.node.try_get_context("max_workers") or 50

cdk_env = cdk.Environment(account=account, region=region)

network = PerfTestNetworkStack(
    app, f"{env_name}-network",
    env_name=env_name,
    env=cdk_env,
)

mwaa = MwaaPerfStack(
    app, f"{env_name}-mwaa",
    vpc=network.vpc,
    mwaa_sg=network.mwaa_sg,
    env_name=env_name,
    environment_class=env_class,
    min_workers=min_workers,
    max_workers=max_workers,
    env=cdk_env,
)
mwaa.add_dependency(network)

cdk.Tags.of(app).add("Project", "mwaa-perf-test")
cdk.Tags.of(app).add("ManagedBy", "CDK")

app.synth()
