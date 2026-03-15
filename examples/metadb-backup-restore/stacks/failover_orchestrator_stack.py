"""
Failover Orchestrator Stack

Deploys a Step Functions workflow that orchestrates a full failover:
1. Starts the MetaDB auto-restore state machine in the secondary region
   (via Lambda, since Step Functions can't do cross-region natively)
2. Polls the restore execution until complete
3. Flips active region (pause/unpause DAGs, update DynamoDB)
4. Sends SNS notification

Also deploys:
- Health check Lambda + EventBridge schedule for automated triggering
- Failover flip Lambda
- Cross-region restore start/poll Lambdas
- DynamoDB state table
"""
from pathlib import Path

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_logs as logs,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_cloudwatch as cloudwatch,
    CfnOutput,
)
from constructs import Construct

_STACK_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _STACK_DIR.parent
_LAMBDA_DIR = str(_PROJECT_DIR / "assets" / "lambda")


class FailoverOrchestratorStack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        primary_env_name: str,
        primary_region: str,
        secondary_env_name: str,
        secondary_region: str,
        restore_state_machine_arn: str,
        notification_email: str = "",
        health_check_interval: str = "rate(1 minute)",
        failure_threshold: int = 3,
        cooldown_minutes: int = 30,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ================================================================
        # DynamoDB state table (single-region, deployed where this stack runs)
        # ================================================================
        self.state_table = dynamodb.Table(
            self, "FailoverStateTable",
            table_name=f"mwaa-failover-state-{self.region}",
            partition_key=dynamodb.Attribute(
                name="state_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ================================================================
        # SNS topic
        # ================================================================
        self.notification_topic = sns.Topic(
            self, "FailoverNotificationTopic",
            topic_name=f"mwaa-failover-notify-{self.region}",
            display_name=f"MWAA Failover Notifications ({self.region})",
        )
        if notification_email:
            self.notification_topic.add_subscription(
                subs.EmailSubscription(notification_email)
            )

        # ================================================================
        # Lambda: Failover Flip (pause/unpause DAGs, update DynamoDB)
        # ================================================================
        flip_role = iam.Role(
            self, "FlipRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        flip_role.add_to_policy(iam.PolicyStatement(
            actions=["airflow:CreateCliToken", "airflow:GetEnvironment"],
            resources=[
                f"arn:aws:airflow:{primary_region}:{self.account}:environment/{primary_env_name}",
                f"arn:aws:airflow:{secondary_region}:{self.account}:environment/{secondary_env_name}",
            ],
        ))
        self.state_table.grant_read_write_data(flip_role)

        self.flip_fn = _lambda.Function(
            self, "FailoverFlipFn",
            function_name=f"mwaa-failover-flip-{self.region}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="failover_flip.handler",
            timeout=Duration.minutes(5),
            memory_size=256,
            role=flip_role,
            environment={
                "PRIMARY_ENV_NAME": primary_env_name,
                "SECONDARY_ENV_NAME": secondary_env_name,
                "PRIMARY_REGION": primary_region,
                "SECONDARY_REGION": secondary_region,
                "STATE_TABLE_NAME": self.state_table.table_name,
            },
            code=_lambda.Code.from_asset(_LAMBDA_DIR),
        )

        # ================================================================
        # Lambda: Start Cross-Region Restore
        # ================================================================
        start_restore_role = iam.Role(
            self, "StartRestoreRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        start_restore_role.add_to_policy(iam.PolicyStatement(
            actions=["states:StartExecution"],
            resources=[restore_state_machine_arn],
        ))

        self.start_restore_fn = _lambda.Function(
            self, "StartCrossRegionRestoreFn",
            function_name=f"mwaa-failover-start-restore-{self.region}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="start_cross_region_restore.handler",
            timeout=Duration.seconds(30),
            memory_size=128,
            role=start_restore_role,
            environment={
                "RESTORE_STATE_MACHINE_ARN": restore_state_machine_arn,
                "TARGET_REGION": secondary_region,
            },
            code=_lambda.Code.from_asset(_LAMBDA_DIR),
        )

        # ================================================================
        # Lambda: Poll Cross-Region Restore
        # ================================================================
        poll_restore_role = iam.Role(
            self, "PollRestoreRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        poll_restore_role.add_to_policy(iam.PolicyStatement(
            actions=["states:DescribeExecution"],
            resources=[
                # Allow describing any execution of the restore SM
                f"arn:aws:states:{secondary_region}:{self.account}:execution:"
                f"{restore_state_machine_arn.split(':')[-1]}:*"
            ],
        ))

        self.poll_restore_fn = _lambda.Function(
            self, "PollCrossRegionRestoreFn",
            function_name=f"mwaa-failover-poll-restore-{self.region}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="poll_cross_region_restore.handler",
            timeout=Duration.seconds(30),
            memory_size=128,
            role=poll_restore_role,
            environment={
                "TARGET_REGION": secondary_region,
            },
            code=_lambda.Code.from_asset(_LAMBDA_DIR),
        )

        # ================================================================
        # Step Functions: Failover Orchestrator
        #   1. Pause DAGs in active (source) region
        #   2. Start cross-region restore (Lambda)
        #   3. Wait → Poll → Choice loop until restore completes
        #   4. Activate target region (update DDB + unpause target DAGs)
        #   5. Notify
        # ================================================================

        # Task 1: Pause DAGs in the source (active) region before restore
        pause_active_task = tasks.LambdaInvoke(
            self, "PauseActiveDags",
            lambda_function=self.flip_fn,
            payload=sfn.TaskInput.from_object({
                "mode": "pause_only",
                "source_env_name": primary_env_name,
                "source_region": primary_region,
                "target_env_name": secondary_env_name,
                "target_region": secondary_region,
                "reason.$": "$.reason",
            }),
            result_path="$.pauseResult",
            result_selector={
                "status.$": "$.Payload.status",
                "source_paused.$": "$.Payload.source_paused",
                "duration_seconds.$": "$.Payload.duration_seconds",
            },
        )

        # Task 2: Start the restore SM in the secondary region via Lambda
        start_restore_task = tasks.LambdaInvoke(
            self, "StartCrossRegionRestore",
            lambda_function=self.start_restore_fn,
            payload=sfn.TaskInput.from_object({
                "restore_state_machine_arn": restore_state_machine_arn,
                "target_region": secondary_region,
                "reason.$": "$.reason",
            }),
            result_path="$.restoreExec",
            result_selector={
                "execution_arn.$": "$.Payload.execution_arn",
                "target_region.$": "$.Payload.target_region",
                "reason.$": "$.Payload.reason",
            },
        )

        # Wait 60s between polls
        wait_for_restore = sfn.Wait(
            self, "WaitForRestore",
            time=sfn.WaitTime.duration(Duration.seconds(60)),
        )

        # Poll restore execution status
        poll_restore_task = tasks.LambdaInvoke(
            self, "PollCrossRegionRestore",
            lambda_function=self.poll_restore_fn,
            payload=sfn.TaskInput.from_object({
                "execution_arn.$": "$.restoreExec.execution_arn",
                "target_region.$": "$.restoreExec.target_region",
                "reason.$": "$.restoreExec.reason",
            }),
            result_path="$.pollResult",
            result_selector={
                "status.$": "$.Payload.status",
                "detail.$": "$.Payload.detail",
                "execution_arn.$": "$.Payload.execution_arn",
                "target_region.$": "$.Payload.target_region",
                "reason.$": "$.Payload.reason",
            },
        )

        # Choice: check poll result
        restore_choice = sfn.Choice(self, "RestoreComplete?")

        # Task: Activate target region (update DDB + unpause target DAGs)
        flip_task = tasks.LambdaInvoke(
            self, "ActivateTargetRegion",
            lambda_function=self.flip_fn,
            payload=sfn.TaskInput.from_object({
                "mode": "activate",
                "target_env_name": secondary_env_name,
                "target_region": secondary_region,
                "source_env_name": primary_env_name,
                "source_region": primary_region,
                "reason.$": "$.restoreExec.reason",
            }),
            result_path="$.flipResult",
            result_selector={
                "status.$": "$.Payload.status",
                "target_unpaused.$": "$.Payload.target_unpaused",
                "dynamodb_updated.$": "$.Payload.dynamodb_updated",
                "duration_seconds.$": "$.Payload.duration_seconds",
            },
        )

        # Notify success
        notify_success = tasks.SnsPublish(
            self, "NotifyFailoverSuccess",
            topic=self.notification_topic,
            subject="MWAA Failover Complete (with MetaDB Restore)",
            message=sfn.TaskInput.from_object({
                "status": "SUCCESS",
                "target_env": secondary_env_name,
                "target_region": secondary_region,
                "source_env": primary_env_name,
                "source_region": primary_region,
                "restore": "SUCCEEDED",
                "flip.$": "$.flipResult",
                "reason.$": "$.restoreExec.reason",
            }),
            result_path=sfn.JsonPath.DISCARD,
        )

        # Notify restore failure
        notify_restore_failed = tasks.SnsPublish(
            self, "NotifyRestoreFailed",
            topic=self.notification_topic,
            subject="MWAA Failover FAILED - MetaDB Restore Error",
            message=sfn.TaskInput.from_object({
                "status": "RESTORE_FAILED",
                "target_env": secondary_env_name,
                "target_region": secondary_region,
                "reason.$": "$.restoreExec.reason",
                "detail.$": "$.pollResult.detail",
                "error": "MetaDB restore failed. Source DAGs are PAUSED — manual intervention needed to unpause or retry.",
            }),
            result_path=sfn.JsonPath.DISCARD,
        )

        # Notify flip failure
        notify_flip_failed = tasks.SnsPublish(
            self, "NotifyFlipFailed",
            topic=self.notification_topic,
            subject="MWAA Failover FAILED - Region Activation Error",
            message=sfn.TaskInput.from_object({
                "status": "FLIP_FAILED",
                "target_env": secondary_env_name,
                "target_region": secondary_region,
                "reason.$": "$.restoreExec.reason",
                "error": "MetaDB restored but target activation failed. Source DAGs are PAUSED — manual intervention needed.",
            }),
            result_path=sfn.JsonPath.DISCARD,
        )

        # Notify pause failure
        notify_pause_failed = tasks.SnsPublish(
            self, "NotifyPauseFailed",
            topic=self.notification_topic,
            subject="MWAA Failover FAILED - Could Not Pause Active DAGs",
            message=sfn.TaskInput.from_object({
                "status": "PAUSE_FAILED",
                "source_env": primary_env_name,
                "source_region": primary_region,
                "reason.$": "$.reason",
                "error": "Failed to pause DAGs in active region. Failover aborted.",
            }),
            result_path=sfn.JsonPath.DISCARD,
        )

        # Notify start failure
        notify_start_failed = tasks.SnsPublish(
            self, "NotifyStartFailed",
            topic=self.notification_topic,
            subject="MWAA Failover FAILED - Could Not Start Restore",
            message=sfn.TaskInput.from_object({
                "status": "START_FAILED",
                "target_env": secondary_env_name,
                "target_region": secondary_region,
                "reason.$": "$.reason",
                "error": "Failed to start cross-region restore. DAGs in source region are paused — manual intervention needed.",
            }),
            result_path=sfn.JsonPath.DISCARD,
        )

        # Error handling
        pause_active_task.add_catch(
            notify_pause_failed,
            errors=["States.ALL"],
            result_path="$.pauseError",
        )
        start_restore_task.add_catch(
            notify_start_failed,
            errors=["States.ALL"],
            result_path="$.startError",
        )
        poll_restore_task.add_catch(
            notify_restore_failed,
            errors=["States.ALL"],
            result_path="$.pollError",
        )
        flip_task.add_catch(
            notify_flip_failed,
            errors=["States.ALL"],
            result_path="$.flipError",
        )

        # Wire the poll loop: wait → poll → choice
        # Choice branches:
        #   running → loop back to wait
        #   success → flip → notify success
        #   failed  → notify restore failed
        restore_choice.when(
            sfn.Condition.string_equals("$.pollResult.status", "running"),
            wait_for_restore,
        ).when(
            sfn.Condition.string_equals("$.pollResult.status", "success"),
            flip_task.next(notify_success),
        ).otherwise(
            notify_restore_failed,
        )

        # Loop: wait → poll → choice (choice loops back to wait for "running")
        wait_for_restore.next(poll_restore_task).next(restore_choice)

        # Full chain: pause → start restore → wait → poll → choice (loop or proceed)
        definition = pause_active_task.next(start_restore_task).next(wait_for_restore)

        failover_log_group = logs.LogGroup(
            self, "FailoverOrchestratorLogGroup",
            log_group_name=f"/aws/stepfunctions/mwaa-failover-orchestrator-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.failover_state_machine = sfn.StateMachine(
            self, "FailoverOrchestratorSM",
            state_machine_name=f"mwaa-failover-orchestrator-{self.region}",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(4),
            logs=sfn.LogOptions(
                destination=failover_log_group,
                level=sfn.LogLevel.ALL,
            ),
        )

        # Grant orchestrator permission to invoke the Lambdas
        self.start_restore_fn.grant_invoke(self.failover_state_machine.role)
        self.poll_restore_fn.grant_invoke(self.failover_state_machine.role)
        self.flip_fn.grant_invoke(self.failover_state_machine.role)
        self.failover_state_machine.role.add_to_policy(iam.PolicyStatement(
            actions=["sns:Publish"],
            resources=[self.notification_topic.topic_arn],
        ))

        # ================================================================
        # Health Check Lambda + EventBridge schedule
        # ================================================================
        health_role = iam.Role(
            self, "HealthCheckRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        health_role.add_to_policy(iam.PolicyStatement(
            actions=["airflow:GetEnvironment"],
            resources=[
                f"arn:aws:airflow:{primary_region}:{self.account}:environment/{primary_env_name}",
            ],
        ))
        health_role.add_to_policy(iam.PolicyStatement(
            actions=["cloudwatch:GetMetricStatistics"],
            resources=["*"],
        ))
        self.state_table.grant_read_write_data(health_role)
        self.notification_topic.grant_publish(health_role)

        # Health check needs to start the orchestrator SM (not invoke a Lambda)
        health_role.add_to_policy(iam.PolicyStatement(
            actions=["states:StartExecution"],
            resources=[self.failover_state_machine.state_machine_arn],
        ))

        self.health_check_fn = _lambda.Function(
            self, "HealthCheckFn",
            function_name=f"mwaa-failover-health-check-{self.region}",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="health_check.handler",
            timeout=Duration.seconds(30),
            memory_size=256,
            role=health_role,
            environment={
                "PRIMARY_ENV_NAME": primary_env_name,
                "PRIMARY_REGION": primary_region,
                "SECONDARY_REGION": secondary_region,
                "STATE_TABLE_NAME": self.state_table.table_name,
                "FAILURE_THRESHOLD": str(failure_threshold),
                "COOLDOWN_MINUTES": str(cooldown_minutes),
                "NOTIFICATION_TOPIC_ARN": self.notification_topic.topic_arn,
                "FAILOVER_STATE_MACHINE_ARN": self.failover_state_machine.state_machine_arn,
            },
            code=_lambda.Code.from_asset(_LAMBDA_DIR),
        )

        # EventBridge schedule
        rule = events.Rule(
            self, "HealthCheckSchedule",
            rule_name=f"mwaa-failover-health-check-{self.region}",
            schedule=events.Schedule.expression(health_check_interval),
            enabled=False,  # Disabled by default — enable after testing
        )
        rule.add_target(events_targets.LambdaFunction(self.health_check_fn))

        # ================================================================
        # Outputs
        # ================================================================
        CfnOutput(self, "FailoverStateMachineArn",
                  value=self.failover_state_machine.state_machine_arn,
                  description="Failover orchestrator Step Functions ARN")
        CfnOutput(self, "StateTableName",
                  value=self.state_table.table_name,
                  description="DynamoDB failover state table")
        CfnOutput(self, "HealthCheckFunctionArn",
                  value=self.health_check_fn.function_arn,
                  description="Health check Lambda ARN")
        CfnOutput(self, "FlipFunctionArn",
                  value=self.flip_fn.function_arn,
                  description="Failover flip Lambda ARN")
        CfnOutput(self, "NotificationTopicArn",
                  value=self.notification_topic.topic_arn,
                  description="SNS notification topic ARN")
