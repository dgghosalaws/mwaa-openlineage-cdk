"""
MetaDB Backup/Restore Stack

Deploys infrastructure for MWAA metadata database backup and restore:
- Glue IAM role (for JDBC connection to MWAA metadb)
- S3 bucket for backup storage
- Step Functions workflow for orchestrating export/restore
- Lambda functions for Glue connection management
- Automated restore workflow (FindLatestBackup → TriggerRestoreDAG → Monitor → Validate → Notify)

Assumes MWAA environments already exist in both regions.
"""
import os
from pathlib import Path

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_iam as iam,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_logs as logs,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    CfnOutput,
)
from constructs import Construct

# Resolve asset paths relative to this file's parent (project root)
_STACK_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _STACK_DIR.parent
_LAMBDA_DIR = str(_PROJECT_DIR / "assets" / "lambda")


class MetaDBBackupRestoreStack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        mwaa_env_name: str,
        mwaa_region: str,
        source_env_name: str = "",
        source_region: str = "",
        notification_email: str = "",
        backup_bucket_name: str = "",
        existing_glue_role_name: str = "",
        skip_glue_jobs: bool = False,
        glue_worker_type: str = "G.1X",
        glue_num_workers: int = 2,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ====================================================================
        # S3 Bucket for backups
        # ====================================================================
        if backup_bucket_name:
            self.backup_bucket = s3.Bucket.from_bucket_name(
                self, "BackupBucket", backup_bucket_name
            )
        else:
            self.backup_bucket = s3.Bucket(
                self,
                "BackupBucket",
                bucket_name=f"mwaa-metadb-backups-{self.account}-{mwaa_region}",
                removal_policy=RemovalPolicy.RETAIN,
                versioned=True,
                encryption=s3.BucketEncryption.S3_MANAGED,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            )

        # ====================================================================
        # Glue IAM Role
        # ====================================================================
        if existing_glue_role_name:
            self.glue_role = iam.Role.from_role_name(
                self, "GlueRole", existing_glue_role_name
            )
        else:
            self.glue_role = iam.Role(
                self,
                "GlueRole",
                role_name=f"mwaa-metadb-glue-{mwaa_region}",
                assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "service-role/AWSGlueServiceRole"
                    ),
                ],
            )

            # S3 access — own region bucket (read/write)
            self.backup_bucket.grant_read_write(self.glue_role)

            # S3 access — cross-region bucket (read for restore)
            cross_region = source_region or mwaa_region
            self.glue_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"],
                    resources=[
                        f"arn:aws:s3:::mwaa-metadb-backups-{self.account}-{cross_region}",
                        f"arn:aws:s3:::mwaa-metadb-backups-{self.account}-{cross_region}/*",
                    ],
                )
            )

            # Glue connection + job management
            self.glue_role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "glue:CreateConnection",
                        "glue:DeleteConnection",
                        "glue:GetConnection",
                        "glue:UpdateConnection",
                    ],
                    resources=["*"],
                )
            )

            # EC2 network access (Glue needs ENIs in MWAA VPC)
            self.glue_role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "ec2:DescribeSubnets",
                        "ec2:DescribeSecurityGroups",
                        "ec2:DescribeVpcEndpoints",
                        "ec2:DescribeRouteTables",
                        "ec2:CreateNetworkInterface",
                        "ec2:DeleteNetworkInterface",
                        "ec2:DescribeNetworkInterfaces",
                    ],
                    resources=["*"],
                )
            )

            # CloudWatch Logs for Glue
            self.glue_role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws-glue/*"],
                )
            )

        # ====================================================================
        # Glue Jobs (skip if already created manually or by previous deploy)
        # ====================================================================
        if not skip_glue_jobs:
            import aws_cdk.aws_glue as glue

            glue.CfnJob(
                self,
                "ExportGlueJob",
                name=f"{mwaa_env_name}_metadb_export",
                role=self.glue_role.role_arn,
                command=glue.CfnJob.JobCommandProperty(
                    name="glueetl",
                    script_location=f"s3://{self.backup_bucket.bucket_name}/scripts/mwaa_metadb_export.py",
                    python_version="3",
                ),
                glue_version="4.0",
                number_of_workers=glue_num_workers,
                worker_type=glue_worker_type,
                default_arguments={
                    "--additional-python-modules": "pg8000",
                    "--enable-metrics": "true",
                },
            )

            glue.CfnJob(
                self,
                "RestoreGlueJob",
                name=f"{mwaa_env_name}_metadb_restore",
                role=self.glue_role.role_arn,
                command=glue.CfnJob.JobCommandProperty(
                    name="glueetl",
                    script_location=f"s3://{self.backup_bucket.bucket_name}/scripts/mwaa_metadb_restore.py",
                    python_version="3",
                ),
                glue_version="4.0",
                number_of_workers=glue_num_workers,
                worker_type=glue_worker_type,
                default_arguments={
                    "--additional-python-modules": "pg8000",
                    "--enable-metrics": "true",
                },
            )

        # ====================================================================
        # Automated Restore Workflow
        # FindLatestBackup → TriggerRestoreDAG → Monitor loop → Validate → Notify
        # ====================================================================

        # Source env defaults to the other region's env for cross-region restore
        _source_env = source_env_name or mwaa_env_name
        _source_region = source_region or mwaa_region

        # SNS topic for notifications
        self.notification_topic = sns.Topic(
            self,
            "RestoreNotificationTopic",
            topic_name=f"mwaa-metadb-restore-notify-{mwaa_region}",
            display_name=f"MWAA MetaDB Restore Notifications ({mwaa_region})",
        )
        if notification_email:
            self.notification_topic.add_subscription(
                subs.EmailSubscription(notification_email)
            )

        # --- Lambda: Find Latest Backup ---
        find_backup_role = iam.Role(
            self, "FindBackupRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        find_backup_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket", "s3:GetObject"],
                resources=[
                    f"arn:aws:s3:::mwaa-metadb-backups-{self.account}-*",
                    f"arn:aws:s3:::mwaa-metadb-backups-{self.account}-*/*",
                ],
            )
        )

        find_backup_fn = _lambda.Function(
            self, "FindLatestBackupFn",
            function_name=f"mwaa-metadb-find-backup-{mwaa_region}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="find_latest_backup.handler",
            timeout=Duration.minutes(2),
            memory_size=256,
            role=find_backup_role,
            environment={
                "SOURCE_BACKUP_BUCKET": f"mwaa-metadb-backups-{self.account}-{_source_region}",
                "SOURCE_ENV_NAME": _source_env,
            },
            code=_lambda.Code.from_asset(_LAMBDA_DIR),
        )

        # --- Lambda: Trigger Restore DAG ---
        trigger_role = iam.Role(
            self, "TriggerRestoreRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        trigger_role.add_to_policy(
            iam.PolicyStatement(
                actions=["airflow:CreateCliToken"],
                resources=[f"arn:aws:airflow:{mwaa_region}:{self.account}:environment/{mwaa_env_name}"],
            )
        )

        trigger_fn = _lambda.Function(
            self, "TriggerRestoreDagFn",
            function_name=f"mwaa-metadb-trigger-restore-{mwaa_region}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="trigger_restore_dag.handler",
            timeout=Duration.minutes(2),
            memory_size=256,
            role=trigger_role,
            environment={
                "TARGET_ENV_NAME": mwaa_env_name,
                "TARGET_REGION": mwaa_region,
            },
            code=_lambda.Code.from_asset(_LAMBDA_DIR),
        )

        # --- Lambda: Monitor DAG Run ---
        monitor_role = iam.Role(
            self, "MonitorDagRunRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        monitor_role.add_to_policy(
            iam.PolicyStatement(
                actions=["airflow:CreateCliToken"],
                resources=[f"arn:aws:airflow:{mwaa_region}:{self.account}:environment/{mwaa_env_name}"],
            )
        )
        monitor_role.add_to_policy(
            iam.PolicyStatement(
                actions=["glue:GetJobRun", "glue:GetJobRuns"],
                resources=[
                    f"arn:aws:glue:{mwaa_region}:{self.account}:job/{mwaa_env_name}_metadb_restore",
                ],
            )
        )

        monitor_fn = _lambda.Function(
            self, "MonitorDagRunFn",
            function_name=f"mwaa-metadb-monitor-dag-{mwaa_region}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="monitor_dag_run.handler",
            timeout=Duration.minutes(2),
            memory_size=256,
            role=monitor_role,
            environment={
                "TARGET_ENV_NAME": mwaa_env_name,
                "TARGET_REGION": mwaa_region,
            },
            code=_lambda.Code.from_asset(_LAMBDA_DIR),
        )

        # --- Lambda: Validate Restore ---
        validate_role = iam.Role(
            self, "ValidateRestoreRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        validate_role.add_to_policy(
            iam.PolicyStatement(
                actions=["airflow:CreateCliToken", "airflow:GetEnvironment"],
                resources=[f"arn:aws:airflow:{mwaa_region}:{self.account}:environment/{mwaa_env_name}"],
            )
        )

        validate_fn = _lambda.Function(
            self, "ValidateRestoreFn",
            function_name=f"mwaa-metadb-validate-restore-{mwaa_region}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="validate_restore.handler",
            timeout=Duration.minutes(3),
            memory_size=256,
            role=validate_role,
            environment={
                "TARGET_ENV_NAME": mwaa_env_name,
                "TARGET_REGION": mwaa_region,
            },
            code=_lambda.Code.from_asset(_LAMBDA_DIR),
        )

        # --- Step Functions: Automated Restore Workflow ---
        find_backup_task = tasks.LambdaInvoke(
            self, "FindLatestBackup",
            lambda_function=find_backup_fn,
            payload=sfn.TaskInput.from_object({
                "source_bucket": f"mwaa-metadb-backups-{self.account}-{_source_region}",
                "source_env_name": _source_env,
            }),
            result_path="$.backupResult",
            result_selector={
                "backup_path.$": "$.Payload.backup_path",
                "timestamp.$": "$.Payload.timestamp",
                "total_rows.$": "$.Payload.total_rows",
            },
        )

        trigger_restore_task = tasks.LambdaInvoke(
            self, "TriggerRestoreDAG",
            lambda_function=trigger_fn,
            payload=sfn.TaskInput.from_object({
                "backup_path.$": "$.backupResult.backup_path",
                "target_env_name": mwaa_env_name,
                "target_region": mwaa_region,
                "restore_mode": "append",
            }),
            result_path="$.triggerResult",
            result_selector={
                "dag_run_id.$": "$.Payload.dag_run_id",
                "target_env_name.$": "$.Payload.target_env_name",
                "target_region.$": "$.Payload.target_region",
                "backup_path.$": "$.Payload.backup_path",
            },
        )

        wait_step = sfn.Wait(
            self, "WaitForRestore",
            time=sfn.WaitTime.duration(Duration.seconds(60)),
        )

        monitor_task = tasks.LambdaInvoke(
            self, "MonitorDAGRun",
            lambda_function=monitor_fn,
            payload=sfn.TaskInput.from_object({
                "dag_run_id.$": "$.triggerResult.dag_run_id",
                "target_env_name.$": "$.triggerResult.target_env_name",
                "target_region.$": "$.triggerResult.target_region",
                "backup_path.$": "$.triggerResult.backup_path",
            }),
            result_path="$.monitorResult",
            result_selector={
                "status.$": "$.Payload.status",
                "dag_run_id.$": "$.Payload.dag_run_id",
                "glue_run_id.$": "$.Payload.glue_run_id",
                "detail.$": "$.Payload.detail",
            },
        )

        validate_task = tasks.LambdaInvoke(
            self, "ValidateRestore",
            lambda_function=validate_fn,
            payload=sfn.TaskInput.from_object({
                "target_env_name.$": "$.triggerResult.target_env_name",
                "target_region.$": "$.triggerResult.target_region",
                "backup_path.$": "$.triggerResult.backup_path",
            }),
            result_path="$.validateResult",
            result_selector={
                "valid.$": "$.Payload.valid",
                "checks.$": "$.Payload.checks",
            },
        )

        # SNS notifications
        notify_success = tasks.SnsPublish(
            self, "NotifySuccess",
            topic=self.notification_topic,
            subject="MetaDB Restore Succeeded",
            message=sfn.TaskInput.from_object({
                "status": "SUCCESS",
                "backup_path.$": "$.backupResult.backup_path",
                "backup_timestamp.$": "$.backupResult.timestamp",
                "target_env": mwaa_env_name,
                "target_region": mwaa_region,
                "validation.$": "$.validateResult.checks",
            }),
            result_path=sfn.JsonPath.DISCARD,
        )

        notify_failure = tasks.SnsPublish(
            self, "NotifyFailure",
            topic=self.notification_topic,
            subject="MetaDB Restore FAILED",
            message=sfn.TaskInput.from_object({
                "status": "FAILED",
                "backup_path.$": "$.backupResult.backup_path",
                "target_env": mwaa_env_name,
                "target_region": mwaa_region,
                "detail.$": "$.monitorResult.detail",
            }),
            result_path=sfn.JsonPath.DISCARD,
        )

        notify_validation_failed = tasks.SnsPublish(
            self, "NotifyValidationFailed",
            topic=self.notification_topic,
            subject="MetaDB Restore - Validation FAILED",
            message=sfn.TaskInput.from_object({
                "status": "VALIDATION_FAILED",
                "backup_path.$": "$.backupResult.backup_path",
                "target_env": mwaa_env_name,
                "target_region": mwaa_region,
                "validation.$": "$.validateResult.checks",
            }),
            result_path=sfn.JsonPath.DISCARD,
        )

        # Build the state machine:
        # FindLatestBackup → TriggerRestoreDAG → Wait → Monitor → Choice
        #   running → Wait (loop)
        #   success → Validate → Choice (valid → NotifySuccess, invalid → NotifyValidationFailed)
        #   failed → NotifyFailure

        check_status = sfn.Choice(self, "CheckDAGRunStatus")
        check_validation = sfn.Choice(self, "CheckValidation")

        restore_succeeded = sfn.Condition.string_equals("$.monitorResult.status", "success")
        restore_failed = sfn.Condition.string_equals("$.monitorResult.status", "failed")
        validation_passed = sfn.Condition.boolean_equals("$.validateResult.valid", True)

        # Wire it up
        auto_restore_definition = (
            find_backup_task
            .next(trigger_restore_task)
            .next(wait_step)
            .next(monitor_task)
            .next(
                check_status
                .when(restore_succeeded,
                      validate_task.next(
                          check_validation
                          .when(validation_passed, notify_success)
                          .otherwise(notify_validation_failed)
                      ))
                .when(restore_failed, notify_failure)
                .otherwise(wait_step)  # still running → loop back
            )
        )

        auto_restore_log_group = logs.LogGroup(
            self, "AutoRestoreLogGroup",
            log_group_name=f"/aws/stepfunctions/mwaa-metadb-auto-restore-{mwaa_region}",
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.auto_restore_state_machine = sfn.StateMachine(
            self, "AutoRestoreStateMachine",
            state_machine_name=f"mwaa-metadb-auto-restore-{mwaa_region}",
            definition_body=sfn.DefinitionBody.from_chainable(auto_restore_definition),
            timeout=Duration.hours(3),
            logs=sfn.LogOptions(
                destination=auto_restore_log_group,
                level=sfn.LogLevel.ALL,
            ),
        )

        # Grant permissions
        for fn in [find_backup_fn, trigger_fn, monitor_fn, validate_fn]:
            fn.grant_invoke(self.auto_restore_state_machine.role)

        self.auto_restore_state_machine.role.add_to_policy(
            iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=[self.notification_topic.topic_arn],
            )
        )

        # ====================================================================
        # Outputs
        # ====================================================================
        CfnOutput(self, "BackupBucketName",
                  value=self.backup_bucket.bucket_name,
                  description="S3 bucket for metadb backups")
        CfnOutput(self, "GlueRoleName",
                  value=self.glue_role.role_name,
                  description="Glue IAM role name")
        CfnOutput(self, "GlueRoleArn",
                  value=self.glue_role.role_arn,
                  description="Glue IAM role ARN")
        CfnOutput(self, "AutoRestoreStateMachineArn",
                  value=self.auto_restore_state_machine.state_machine_arn,
                  description="Automated Restore Step Functions workflow ARN")
        CfnOutput(self, "NotificationTopicArn",
                  value=self.notification_topic.topic_arn,
                  description="SNS topic for restore notifications")
