"""
MWAA DR Secondary Region Stack

This stack creates DR resources in the secondary region including:
- S3 backup bucket (replication target)
- Health monitoring of primary
- Automated failover workflow
- Automated fallback workflow
"""
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_events as events,
    aws_events_targets as targets,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_logs as logs,
    Duration,
    RemovalPolicy,
    CfnOutput,
)
from constructs import Construct


class MwaaDRSecondaryStack(Stack):
    """
    Secondary region DR stack with failover and fallback
    
    Creates:
    - S3 backup bucket (replication target)
    - Health monitoring Step Functions
    - Failover orchestration
    - Fallback orchestration
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        env_name: str,
        mwaa_environment_name: str,
        primary_mwaa_environment_name: str,
        dr_state_table_name: str,
        primary_region: str,
        health_check_interval: str = "rate(1 minute)",
        health_check_threshold: int = 3,
        fallback_cooldown_minutes: int = 30,
        notification_emails: list = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.project_name = project_name
        self.env_name = env_name
        self.mwaa_environment_name = mwaa_environment_name
        self.primary_mwaa_environment_name = primary_mwaa_environment_name
        self.dr_state_table_name = dr_state_table_name
        self.primary_region = primary_region
        self.health_check_interval = health_check_interval
        self.health_check_threshold = health_check_threshold
        self.fallback_cooldown_minutes = fallback_cooldown_minutes
        self.notification_emails = notification_emails or []

        # Create backup bucket (replication target)
        self.backup_bucket = self._create_backup_bucket()

        # Create SNS topic
        self.notification_topic = self._create_notification_topic()

        # Create Lambda functions
        self.health_check_function = self._create_health_check_function()
        self.state_updater_function = self._create_state_updater_function()
        self.failover_function = self._create_failover_function()
        self.fallback_function = self._create_fallback_function()

        # Create Step Functions workflows
        self.dr_orchestration_workflow = self._create_dr_orchestration_workflow()

        # Create EventBridge rule for health monitoring
        self.health_check_rule = self._create_health_check_schedule()

        # Outputs
        self._create_outputs()

    def _create_backup_bucket(self) -> s3.Bucket:
        """Create S3 bucket for metadata backups (replication target)"""
        bucket = s3.Bucket(
            self,
            "BackupBucket",
            bucket_name=f"{self.project_name}-dr-backup-secondary-{self.env_name}-{self.region}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    noncurrent_version_expiration=Duration.days(30),
                    enabled=True
                )
            ]
        )

        return bucket

    def _create_notification_topic(self) -> sns.Topic:
        """Create SNS topic for DR notifications"""
        topic = sns.Topic(
            self,
            "NotificationTopic",
            topic_name=f"{self.project_name}-dr-notifications-secondary-{self.env_name}",
            display_name="MWAA DR Notifications (Secondary)"
        )

        for email in self.notification_emails:
            topic.add_subscription(
                subscriptions.EmailSubscription(email)
            )

        return topic

    def _create_health_check_function(self) -> lambda_.Function:
        """Create Lambda function to check primary region health"""
        function = lambda_.Function(
            self,
            "HealthCheckFunction",
            function_name=f"{self.project_name}-dr-health-check-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import json
import boto3
import os
from datetime import datetime, timedelta

def handler(event, context):
    primary_region = os.environ['PRIMARY_REGION']
    primary_env_name = os.environ['PRIMARY_MWAA_ENVIRONMENT_NAME']
    
    # Create MWAA client for primary region
    mwaa_client = boto3.client('mwaa', region_name=primary_region)
    cloudwatch = boto3.client('cloudwatch', region_name=primary_region)
    
    try:
        # Check 1: Get environment status
        env_response = mwaa_client.get_environment(Name=primary_env_name)
        env_status = env_response['Environment']['Status']
        
        # Check 2: Get scheduler heartbeat metric
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=5)
        
        metrics_response = cloudwatch.get_metric_statistics(
            Namespace='AmazonMWAA',
            MetricName='SchedulerHeartbeat',
            Dimensions=[
                {'Name': 'Environment', 'Value': primary_env_name}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=60,
            Statistics=['Average']
        )
        
        has_heartbeat = len(metrics_response['Datapoints']) > 0
        
        # Determine health status
        is_healthy = (
            env_status == 'AVAILABLE' and
            has_heartbeat
        )
        
        return {
            'statusCode': 200,
            'isHealthy': is_healthy,
            'environmentStatus': env_status,
            'hasHeartbeat': has_heartbeat,
            'timestamp': datetime.utcnow().isoformat(),
            'region': primary_region
        }
        
    except Exception as e:
        print(f"Health check failed: {str(e)}")
        return {
            'statusCode': 500,
            'isHealthy': False,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat(),
            'region': primary_region
        }
            """),
            environment={
                "PRIMARY_REGION": self.primary_region,
                "PRIMARY_MWAA_ENVIRONMENT_NAME": self.primary_mwaa_environment_name,
            },
            timeout=Duration.seconds(30),
            memory_size=256,
        )

        # Grant permissions to check primary region
        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "airflow:GetEnvironment",
                ],
                resources=[
                    f"arn:aws:airflow:{self.primary_region}:{self.account}:environment/{self.primary_mwaa_environment_name}"
                ]
            )
        )

        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudwatch:GetMetricStatistics",
                ],
                resources=["*"]
            )
        )

        return function

    def _create_state_updater_function(self) -> lambda_.Function:
        """Create Lambda function to update DR state"""
        function = lambda_.Function(
            self,
            "StateUpdaterFunction",
            function_name=f"{self.project_name}-dr-state-updater-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import json
import boto3
import os
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

def handler(event, context):
    state_table_name = os.environ['STATE_TABLE_NAME']
    notification_topic_arn = os.environ['NOTIFICATION_TOPIC_ARN']
    
    action = event.get('action')  # 'failover' or 'fallback'
    reason = event.get('reason', 'Unknown')
    new_active_region = event.get('new_active_region')
    
    try:
        table = dynamodb.Table(state_table_name)
        
        # Get current state
        response = table.get_item(Key={'state_id': 'ACTIVE_REGION'})
        current_state = response.get('Item', {})
        current_version = int(current_state.get('version', 0))
        
        # Prepare new state
        timestamp = datetime.utcnow().isoformat()
        failover_count = int(current_state.get('failover_count', 0))
        
        new_state = {
            'state_id': 'ACTIVE_REGION',
            'active_region': new_active_region,
            'last_updated': timestamp,
            'failover_count': failover_count + (1 if action == 'failover' else 0),
            'version': current_version + 1
        }
        
        if action == 'failover':
            new_state['last_failover_time'] = timestamp
            new_state['failover_reason'] = reason
        elif action == 'fallback':
            new_state['last_fallback_time'] = timestamp
        
        # Conditional update with optimistic locking
        table.put_item(
            Item=new_state,
            ConditionExpression='attribute_not_exists(version) OR version = :current_version',
            ExpressionAttributeValues={':current_version': current_version}
        )
        
        # Send notification
        message = f'''
MWAA DR State Change

Action: {action.upper()}
New Active Region: {new_active_region}
Reason: {reason}
Timestamp: {timestamp}
Failover Count: {new_state["failover_count"]}
        '''
        
        sns.publish(
            TopicArn=notification_topic_arn,
            Subject=f"MWAA DR: {action.upper()} Completed",
            Message=message
        )
        
        return {
            'statusCode': 200,
            'state': new_state
        }
        
    except Exception as e:
        print(f"Error updating state: {str(e)}")
        raise
"""),
            environment={
                "STATE_TABLE_NAME": self.dr_state_table_name,
                "NOTIFICATION_TOPIC_ARN": self.notification_topic.topic_arn,
            },
            timeout=Duration.seconds(30),
            memory_size=128,
        )

        # Grant permissions
        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.dr_state_table_name}"
                ]
            )
        )

        self.notification_topic.grant_publish(function)

        return function

    def _create_failover_function(self) -> lambda_.Function:
        """Create Lambda function to execute failover"""
        function = lambda_.Function(
            self,
            "FailoverFunction",
            function_name=f"{self.project_name}-dr-failover-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import json
import boto3
import os

mwaa_client = boto3.client('mwaa')

def handler(event, context):
    secondary_env_name = os.environ['SECONDARY_MWAA_ENVIRONMENT_NAME']
    
    try:
        # Trigger restore metadata DAG in secondary MWAA
        # This will be implemented with actual DAG trigger logic
        
        print(f"Executing failover to {secondary_env_name}")
        
        # TODO: Trigger restore_metadata DAG
        # cli_token = mwaa_client.create_cli_token(Name=secondary_env_name)
        
        return {
            'statusCode': 200,
            'message': f'Failover initiated for {secondary_env_name}'
        }
        
    except Exception as e:
        print(f"Failover failed: {str(e)}")
        raise
            """),
            environment={
                "SECONDARY_MWAA_ENVIRONMENT_NAME": self.mwaa_environment_name,
            },
            timeout=Duration.minutes(5),
            memory_size=256,
        )

        # Grant permissions
        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "airflow:CreateCliToken",
                    "airflow:GetEnvironment"
                ],
                resources=[
                    f"arn:aws:airflow:{self.region}:{self.account}:environment/{self.mwaa_environment_name}"
                ]
            )
        )

        self.backup_bucket.grant_read(function)

        return function

    def _create_fallback_function(self) -> lambda_.Function:
        """Create Lambda function to execute fallback"""
        function = lambda_.Function(
            self,
            "FallbackFunction",
            function_name=f"{self.project_name}-dr-fallback-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import json
import boto3
import os

def handler(event, context):
    primary_region = os.environ['PRIMARY_REGION']
    primary_env_name = os.environ['PRIMARY_MWAA_ENVIRONMENT_NAME']
    
    try:
        # Sync metadata from secondary to primary
        # Trigger restore in primary region
        
        print(f"Executing fallback to {primary_env_name} in {primary_region}")
        
        # TODO: Trigger metadata sync and restore in primary
        
        return {
            'statusCode': 200,
            'message': f'Fallback initiated to {primary_env_name}'
        }
        
    except Exception as e:
        print(f"Fallback failed: {str(e)}")
        raise
            """),
            environment={
                "PRIMARY_REGION": self.primary_region,
                "PRIMARY_MWAA_ENVIRONMENT_NAME": self.primary_mwaa_environment_name,
            },
            timeout=Duration.minutes(5),
            memory_size=256,
        )

        # Grant permissions
        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "airflow:CreateCliToken",
                    "airflow:GetEnvironment"
                ],
                resources=[
                    f"arn:aws:airflow:{self.primary_region}:{self.account}:environment/{self.primary_mwaa_environment_name}"
                ]
            )
        )

        return function

    def _create_dr_orchestration_workflow(self) -> sfn.StateMachine:
        """Create Step Functions workflow for DR orchestration"""
        
        # Define tasks
        health_check_task = tasks.LambdaInvoke(
            self, "CheckPrimaryHealth",
            lambda_function=self.health_check_function,
            output_path="$.Payload"
        )

        # Choice: Is primary healthy?
        is_healthy_choice = sfn.Choice(self, "IsPrimaryHealthy?")

        # Get current state
        get_state_task = tasks.LambdaInvoke(
            self, "GetCurrentState",
            lambda_function=self.state_updater_function,
            payload=sfn.TaskInput.from_object({
                "action": "get_state"
            }),
            output_path="$.Payload"
        )

        # Failover branch
        execute_failover = tasks.LambdaInvoke(
            self, "ExecuteFailover",
            lambda_function=self.failover_function,
            output_path="$.Payload"
        )

        update_state_failover = tasks.LambdaInvoke(
            self, "UpdateStateFailover",
            lambda_function=self.state_updater_function,
            payload=sfn.TaskInput.from_object({
                "action": "failover",
                "new_active_region": self.region,
                "reason": "Primary region unhealthy"
            }),
            output_path="$.Payload"
        )

        # Fallback branch
        execute_fallback = tasks.LambdaInvoke(
            self, "ExecuteFallback",
            lambda_function=self.fallback_function,
            output_path="$.Payload"
        )

        update_state_fallback = tasks.LambdaInvoke(
            self, "UpdateStateFallback",
            lambda_function=self.state_updater_function,
            payload=sfn.TaskInput.from_object({
                "action": "fallback",
                "new_active_region": self.primary_region,
                "reason": "Primary region recovered"
            }),
            output_path="$.Payload"
        )

        # Success state
        success = sfn.Succeed(self, "Success")

        # Define workflow
        definition = health_check_task.next(
            is_healthy_choice
                .when(
                    sfn.Condition.boolean_equals("$.isHealthy", False),
                    execute_failover.next(update_state_failover).next(success)
                )
                .when(
                    sfn.Condition.boolean_equals("$.isHealthy", True),
                    # Check if we should fallback
                    execute_fallback.next(update_state_fallback).next(success)
                )
                .otherwise(success)
        )

        # Create state machine
        log_group = logs.LogGroup(
            self,
            "DRWorkflowLogGroup",
            log_group_name=f"/aws/vendedlogs/states/{self.project_name}-dr-workflow-{self.env_name}",
            removal_policy=RemovalPolicy.DESTROY
        )

        state_machine = sfn.StateMachine(
            self,
            "DROrchestrationWorkflow",
            state_machine_name=f"{self.project_name}-dr-orchestration-{self.env_name}",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(30),
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL
            )
        )

        return state_machine

    def _create_health_check_schedule(self) -> events.Rule:
        """Create EventBridge rule for health monitoring"""
        rule = events.Rule(
            self,
            "HealthCheckScheduleRule",
            rule_name=f"{self.project_name}-dr-health-check-{self.env_name}",
            description="Periodic health check of primary region",
            schedule=events.Schedule.expression(self.health_check_interval),
            enabled=True
        )

        rule.add_target(
            targets.SfnStateMachine(self.dr_orchestration_workflow)
        )

        return rule

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "BackupBucketName",
            value=self.backup_bucket.bucket_name,
            description="S3 bucket for metadata backups (secondary)",
            export_name=f"{self.project_name}-dr-backup-bucket-secondary-{self.env_name}"
        )

        CfnOutput(
            self,
            "DRWorkflowArn",
            value=self.dr_orchestration_workflow.state_machine_arn,
            description="Step Functions workflow for DR orchestration"
        )

        CfnOutput(
            self,
            "NotificationTopicArn",
            value=self.notification_topic.topic_arn,
            description="SNS topic for DR notifications"
        )
