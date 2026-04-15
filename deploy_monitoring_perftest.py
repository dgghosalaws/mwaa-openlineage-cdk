#!/usr/bin/env python3
"""Quick standalone deploy of monitoring stack for Performance-test cluster"""
import aws_cdk as cdk
from stacks.mwaa_monitoring_stack import MwaaMonitoringStack

app = cdk.App()

MwaaMonitoringStack(
    app,
    "perf-test-monitoring",
    mwaa_environment_name="Performance-test",
    project_name="perf-test",
    environment="dev",
    env=cdk.Environment(account="834811675783", region="us-east-2"),
    description="CloudWatch dashboard for Performance-test MWAA cluster",
)

app.synth()
