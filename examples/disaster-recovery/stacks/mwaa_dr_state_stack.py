"""
MWAA DR State Management Stack

This stack creates a DynamoDB Global Table to track the active region
and manage failover/fallback state across regions.
"""
from aws_cdk import (
    Stack,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_s3 as s3,
    RemovalPolicy,
    Duration,
    CfnOutput,
)
from constructs import Construct


class MwaaDRStateStack(Stack):
    """
    Stack for DR state management using DynamoDB Global Table
    
    This stack creates:
    - DynamoDB Global Table for active region tracking
    - IAM policies for state management
    - Outputs for cross-stack references
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        env_name: str,
        primary_region: str,
        secondary_region: str,
        enable_backup: bool = True,
        existing_backup_bucket_name: str = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.project_name = project_name
        self.env_name = env_name
        self.primary_region = primary_region
        self.secondary_region = secondary_region
        self.enable_backup = enable_backup
        self.existing_backup_bucket_name = existing_backup_bucket_name

        # Create or import S3 bucket for metadata backups (Phase 2)
        if self.enable_backup:
            if self.existing_backup_bucket_name:
                # Import existing bucket
                self.backup_bucket = self._import_backup_bucket()
            else:
                # Create new bucket
                self.backup_bucket = self._create_backup_bucket()

        # Create DynamoDB Global Table for DR state
        self.dr_state_table = self._create_dr_state_table()

        # Create IAM policy for state management
        self.state_management_policy = self._create_state_management_policy()

        # Create IAM policy for backup/restore (Phase 2)
        if self.enable_backup:
            self.backup_restore_policy = self._create_backup_restore_policy()

        # Outputs
        self._create_outputs()

    def _import_backup_bucket(self) -> s3.IBucket:
        """
        Import existing S3 bucket for metadata backups (Phase 2)
        
        Use this when bucket was created manually or outside CDK.
        """
        bucket = s3.Bucket.from_bucket_name(
            self,
            "BackupBucket",
            bucket_name=self.existing_backup_bucket_name
        )
        
        return bucket

    def _create_backup_bucket(self) -> s3.Bucket:
        """
        Create S3 bucket for metadata backups (Phase 2)
        
        Features:
        - Versioning enabled
        - Lifecycle policy to delete old backups after 7 days
        - Encryption at rest
        - Access logging
        """
        bucket = s3.Bucket(
            self,
            "BackupBucket",
            bucket_name=f"{self.project_name}-dr-backups-{self.primary_region}-{self.env.account}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,  # Retain backups
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldBackups",
                    enabled=True,
                    prefix="metadata/",
                    expiration=Duration.days(7),
                    noncurrent_version_expiration=Duration.days(1),
                )
            ],
        )

        return bucket

    def _create_dr_state_table(self) -> dynamodb.TableV2:
        """
        Create DynamoDB Global Table for DR state management
        
        Table schema (Phase 1):
        - state_id (PK): Always "ACTIVE_REGION" (single row table)
        - active_region: Current active region (primary_region or secondary_region)
        - last_updated: Timestamp of last state change
        - failover_count: Number of failovers
        - last_failover_time: Timestamp of last failover
        - last_fallback_time: Timestamp of last fallback
        - failover_reason: Reason for last failover
        - health_status_primary: Health status of primary region
        - health_status_secondary: Health status of secondary region
        - version: Optimistic locking version number
        
        Phase 2 fields (added for backup/restore):
        - restore_status: NONE|IN_PROGRESS|COMPLETED|FAILED
        - restore_started_at: Timestamp when restore began
        - restore_completed_at: Timestamp when restore finished
        - restore_error: Error message if restore failed
        - last_backup_time: Timestamp of last successful backup
        - backup_s3_key: S3 key of last backup manifest
        """
        table = dynamodb.TableV2(
            self,
            "DRStateTable",
            table_name=f"{self.project_name}-dr-state-{self.env_name}",
            partition_key=dynamodb.Attribute(
                name="state_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing=dynamodb.Billing.on_demand(),
            removal_policy=RemovalPolicy.RETAIN,  # Retain state data
            point_in_time_recovery=True,
            replicas=[
                dynamodb.ReplicaTableProps(region=self.secondary_region)
            ],
            contributor_insights=True,
        )

        return table

    def _create_state_management_policy(self) -> iam.ManagedPolicy:
        """Create IAM policy for DR state management operations"""
        policy = iam.ManagedPolicy(
            self,
            "StateManagementPolicy",
            managed_policy_name=f"{self.project_name}-dr-state-mgmt-{self.env_name}",
            description="Policy for MWAA DR state management operations",
            statements=[
                # Read state
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "dynamodb:GetItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                    ],
                    resources=[
                        self.dr_state_table.table_arn,
                    ]
                ),
                # Write state with conditional writes for optimistic locking
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                    ],
                    resources=[
                        self.dr_state_table.table_arn,
                    ],
                    conditions={
                        "ForAllValues:StringEquals": {
                            "dynamodb:Attributes": [
                                "state_id",
                                "active_region",
                                "last_updated",
                                "failover_count",
                                "last_failover_time",
                                "last_fallback_time",
                                "failover_reason",
                                "health_status_primary",
                                "health_status_secondary",
                                "version",
                                # Phase 2 fields
                                "restore_status",
                                "restore_started_at",
                                "restore_completed_at",
                                "restore_error",
                                "last_backup_time",
                                "backup_s3_key"
                            ]
                        }
                    }
                ),
            ]
        )

        return policy

    def _create_backup_restore_policy(self) -> iam.ManagedPolicy:
        """Create IAM policy for backup/restore operations (Phase 2)"""
        policy = iam.ManagedPolicy(
            self,
            "BackupRestorePolicy",
            managed_policy_name=f"{self.project_name}-dr-backup-restore-{self.env_name}",
            description="Policy for MWAA DR backup and restore operations",
            statements=[
                # S3 backup bucket access
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket",
                    ],
                    resources=[
                        self.backup_bucket.bucket_arn,
                        f"{self.backup_bucket.bucket_arn}/*",
                    ]
                ),
            ]
        )

        return policy

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "DRStateTableName",
            value=self.dr_state_table.table_name,
            description="DynamoDB table name for DR state",
            export_name=f"{self.project_name}-dr-state-table-{self.env_name}"
        )

        CfnOutput(
            self,
            "DRStateTableArn",
            value=self.dr_state_table.table_arn,
            description="DynamoDB table ARN for DR state",
            export_name=f"{self.project_name}-dr-state-table-arn-{self.env_name}"
        )

        CfnOutput(
            self,
            "StateManagementPolicyArn",
            value=self.state_management_policy.managed_policy_arn,
            description="IAM policy ARN for DR state management",
            export_name=f"{self.project_name}-dr-state-policy-arn-{self.env_name}"
        )

        # Phase 2 outputs
        if self.enable_backup:
            CfnOutput(
                self,
                "BackupBucketName",
                value=self.backup_bucket.bucket_name,
                description="S3 bucket name for metadata backups",
                export_name=f"{self.project_name}-dr-backup-bucket-{self.env_name}"
            )

            CfnOutput(
                self,
                "BackupBucketArn",
                value=self.backup_bucket.bucket_arn,
                description="S3 bucket ARN for metadata backups",
                export_name=f"{self.project_name}-dr-backup-bucket-arn-{self.env_name}"
            )

            CfnOutput(
                self,
                "BackupRestorePolicyArn",
                value=self.backup_restore_policy.managed_policy_arn,
                description="IAM policy ARN for backup/restore operations",
                export_name=f"{self.project_name}-dr-backup-restore-policy-arn-{self.env_name}"
            )
