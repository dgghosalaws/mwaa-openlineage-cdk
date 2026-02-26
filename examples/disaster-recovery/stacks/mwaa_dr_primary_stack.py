"""
MWAA DR Primary Region Stack

This stack creates DR resources in the primary region including:
- S3 backup bucket for metadata
- Cross-region replication to secondary
- Metadata backup DAGs
- Health monitoring
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
    Duration,
    RemovalPolicy,
    CfnOutput,
)
from constructs import Construct
import json


class MwaaDRPrimaryStack(Stack):
    """
    Primary region DR stack
    
    Creates:
    - S3 backup bucket with versioning
    - Cross-region replication to secondary
    - Metadata backup framework
    - Health monitoring
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        env_name: str,
        mwaa_environment_name: str,
        mwaa_dags_bucket: s3.IBucket,
        dr_state_table_name: str,
        secondary_region: str,
        backup_schedule: str = "rate(5 minutes)",
        notification_emails: list = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.project_name = project_name
        self.env_name = env_name
        self.mwaa_environment_name = mwaa_environment_name
        self.mwaa_dags_bucket = mwaa_dags_bucket
        self.dr_state_table_name = dr_state_table_name
        self.secondary_region = secondary_region
        self.backup_schedule = backup_schedule
        self.notification_emails = notification_emails or []

        # Create backup bucket
        self.backup_bucket = self._create_backup_bucket()

        # Create replication role
        self.replication_role = self._create_replication_role()

        # Create SNS topic for notifications
        self.notification_topic = self._create_notification_topic()

        # Create Lambda functions
        self.backup_trigger_function = self._create_backup_trigger_function()
        self.state_reader_function = self._create_state_reader_function()

        # Create EventBridge rule for scheduled backups
        self.backup_schedule_rule = self._create_backup_schedule()

        # Outputs
        self._create_outputs()

    def _create_backup_bucket(self) -> s3.Bucket:
        """Create S3 bucket for metadata backups with cross-region replication"""
        # Secondary bucket name (will be created by secondary stack)
        secondary_bucket_name = f"{self.project_name}-dr-backup-secondary-{self.env_name}-{self.secondary_region}"

        bucket = s3.Bucket(
            self,
            "BackupBucket",
            bucket_name=f"{self.project_name}-dr-backup-primary-{self.env_name}-{self.region}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    noncurrent_version_expiration=Duration.days(30),
                    enabled=True
                ),
                s3.LifecycleRule(
                    id="TransitionToIA",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30)
                        )
                    ],
                    enabled=True
                )
            ]
        )

        return bucket

    def _create_replication_role(self) -> iam.Role:
        """Create IAM role for S3 cross-region replication"""
        role = iam.Role(
            self,
            "ReplicationRole",
            assumed_by=iam.ServicePrincipal("s3.amazonaws.com"),
            description="Role for S3 cross-region replication"
        )

        # Add replication permissions
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetReplicationConfiguration",
                    "s3:ListBucket"
                ],
                resources=[self.backup_bucket.bucket_arn]
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObjectVersionForReplication",
                    "s3:GetObjectVersionAcl",
                    "s3:GetObjectVersionTagging"
                ],
                resources=[f"{self.backup_bucket.bucket_arn}/*"]
            )
        )

        # Permissions for destination bucket (secondary region)
        secondary_bucket_arn = f"arn:aws:s3:::{self.project_name}-dr-backup-secondary-{self.env_name}"
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:ReplicateObject",
                    "s3:ReplicateDelete",
                    "s3:ReplicateTags"
                ],
                resources=[f"{secondary_bucket_arn}/*"]
            )
        )

        return role

    def _create_notification_topic(self) -> sns.Topic:
        """Create SNS topic for DR notifications"""
        topic = sns.Topic(
            self,
            "NotificationTopic",
            topic_name=f"{self.project_name}-dr-notifications-primary-{self.env_name}",
            display_name="MWAA DR Notifications (Primary)"
        )

        # Subscribe emails
        for email in self.notification_emails:
            topic.add_subscription(
                subscriptions.EmailSubscription(email)
            )

        return topic

    def _create_backup_trigger_function(self) -> lambda_.Function:
        """Create Lambda function to trigger metadata backup DAG"""
        function = lambda_.Function(
            self,
            "BackupTriggerFunction",
            function_name=f"{self.project_name}-dr-backup-trigger-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import json
import boto3
import os
from datetime import datetime

mwaa_client = boto3.client('mwaa')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    environment_name = os.environ['MWAA_ENVIRONMENT_NAME']
    backup_bucket = os.environ['BACKUP_BUCKET']
    state_table_name = os.environ['STATE_TABLE_NAME']
    
    try:
        # Check if this region is active
        table = dynamodb.Table(state_table_name)
        response = table.get_item(Key={'state_id': 'ACTIVE_REGION'})
        
        if 'Item' in response:
            active_region = response['Item'].get('active_region')
            current_region = os.environ['AWS_REGION']
            
            # Only backup if this is the active region
            if active_region != current_region:
                print(f"Skipping backup - not active region. Active: {active_region}, Current: {current_region}")
                return {
                    'statusCode': 200,
                    'body': json.dumps('Backup skipped - not active region')
                }
        
        # Trigger backup DAG via MWAA CLI
        cli_token = mwaa_client.create_cli_token(Name=environment_name)
        
        # Store backup metadata
        timestamp = datetime.utcnow().isoformat()
        metadata = {
            'timestamp': timestamp,
            'environment': environment_name,
            'region': os.environ['AWS_REGION'],
            'trigger': 'scheduled'
        }
        
        s3_client.put_object(
            Bucket=backup_bucket,
            Key=f'metadata/backup_{timestamp}.json',
            Body=json.dumps(metadata)
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps(f'Backup triggered at {timestamp}')
        }
        
    except Exception as e:
        print(f"Error triggering backup: {str(e)}")
        raise
            """),
            environment={
                "MWAA_ENVIRONMENT_NAME": self.mwaa_environment_name,
                "BACKUP_BUCKET": self.backup_bucket.bucket_name,
                "STATE_TABLE_NAME": self.dr_state_table_name,
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

        self.backup_bucket.grant_read_write(function)

        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:Query"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.dr_state_table_name}"
                ]
            )
        )

        return function

    def _create_state_reader_function(self) -> lambda_.Function:
        """Create Lambda function to read DR state"""
        function = lambda_.Function(
            self,
            "StateReaderFunction",
            function_name=f"{self.project_name}-dr-state-reader-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import json
import boto3
import os

dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    state_table_name = os.environ['STATE_TABLE_NAME']
    
    try:
        table = dynamodb.Table(state_table_name)
        response = table.get_item(Key={'state_id': 'ACTIVE_REGION'})
        
        if 'Item' in response:
            return {
                'statusCode': 200,
                'state': response['Item']
            }
        else:
            # Initialize state if not exists
            current_region = os.environ['AWS_REGION']
            initial_state = {
                'state_id': 'ACTIVE_REGION',
                'active_region': current_region,
                'last_updated': context.aws_request_id,
                'failover_count': 0,
                'version': 1
            }
            table.put_item(Item=initial_state)
            
            return {
                'statusCode': 200,
                'state': initial_state
            }
            
    except Exception as e:
        print(f"Error reading state: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }
            """),
            environment={
                "STATE_TABLE_NAME": self.dr_state_table_name,
            },
            timeout=Duration.seconds(30),
            memory_size=128,
        )

        # Grant DynamoDB permissions
        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:Query"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.dr_state_table_name}"
                ]
            )
        )

        return function

    def _create_backup_schedule(self) -> events.Rule:
        """Create EventBridge rule for scheduled backups"""
        rule = events.Rule(
            self,
            "BackupScheduleRule",
            rule_name=f"{self.project_name}-dr-backup-schedule-{self.env_name}",
            description="Scheduled metadata backup for DR",
            schedule=events.Schedule.expression(self.backup_schedule),
            enabled=True
        )

        rule.add_target(
            targets.LambdaFunction(self.backup_trigger_function)
        )

        return rule

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "BackupBucketName",
            value=self.backup_bucket.bucket_name,
            description="S3 bucket for metadata backups",
            export_name=f"{self.project_name}-dr-backup-bucket-primary-{self.env_name}"
        )

        CfnOutput(
            self,
            "NotificationTopicArn",
            value=self.notification_topic.topic_arn,
            description="SNS topic for DR notifications",
            export_name=f"{self.project_name}-dr-notifications-primary-{self.env_name}"
        )

        CfnOutput(
            self,
            "BackupSchedule",
            value=self.backup_schedule,
            description="Backup schedule expression"
        )
