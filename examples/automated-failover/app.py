#!/usr/bin/env python3
"""
MWAA Automated Failover - CDK App

Deploys automated failover infrastructure for MWAA DR.
Requires the disaster-recovery example to be deployed first.
"""
import aws_cdk as cdk
from stacks.automated_failover_stack import AutomatedFailoverStack

app = cdk.App()

# Configuration
PROJECT_NAME = "mwaa-openlineage"
ENV_NAME = "dev"
PRIMARY_ENV_NAME = "mwaa-openlineage-dev"
SECONDARY_ENV_NAME = "mwaa-openlineage-minimal-dev"
PRIMARY_REGION = "us-east-2"
SECONDARY_REGION = "us-east-1"
STATE_TABLE_NAME = "mwaa-openlineage-dr-state-dev"

# Automated failover configuration
HEALTH_CHECK_INTERVAL = "rate(1 minute)"  # How often to check health
FAILURE_THRESHOLD = 3  # Number of consecutive failures before failover
COOLDOWN_MINUTES = 30  # Cooldown period after failover to prevent flapping

# Health check criteria (optional)
REQUIRE_SCHEDULER_HEARTBEAT = False  # Set to True to make heartbeat mandatory
CHECK_ENVIRONMENT_STATUS = True  # Always check environment status (recommended)

# Notification emails (optional)
NOTIFICATION_EMAILS = [
    # "your-email@example.com",
]

# Deploy automated failover stack
AutomatedFailoverStack(
    app,
    "MwaaAutomatedFailoverStack",
    project_name=PROJECT_NAME,
    env_name=ENV_NAME,
    primary_env_name=PRIMARY_ENV_NAME,
    secondary_env_name=SECONDARY_ENV_NAME,
    primary_region=PRIMARY_REGION,
    secondary_region=SECONDARY_REGION,
    state_table_name=STATE_TABLE_NAME,
    health_check_interval=HEALTH_CHECK_INTERVAL,
    failure_threshold=FAILURE_THRESHOLD,
    cooldown_minutes=COOLDOWN_MINUTES,
    require_scheduler_heartbeat=REQUIRE_SCHEDULER_HEARTBEAT,
    check_environment_status=CHECK_ENVIRONMENT_STATUS,
    notification_emails=NOTIFICATION_EMAILS,
    env=cdk.Environment(region=PRIMARY_REGION),
    description="MWAA Automated Failover - Health monitoring and automated failover"
)

app.synth()
