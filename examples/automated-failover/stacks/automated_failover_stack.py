"""
MWAA Automated Failover Stack

Creates Lambda functions and EventBridge rules for automated failover.
"""
from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    Duration,
    CfnOutput,
)
from constructs import Construct


class AutomatedFailoverStack(Stack):
    """
    Automated failover stack
    
    Creates:
    - Health check Lambda function
    - Failover Lambda function
    - EventBridge rule for periodic health checks
    - SNS topic for notifications
    - IAM roles and permissions
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        env_name: str,
        primary_env_name: str,
        secondary_env_name: str,
        primary_region: str,
        secondary_region: str,
        state_table_name: str,
        health_check_interval: str = "rate(1 minute)",
        failure_threshold: int = 3,
        cooldown_minutes: int = 30,
        notification_emails: list = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.project_name = project_name
        self.env_name = env_name
        self.primary_env_name = primary_env_name
        self.secondary_env_name = secondary_env_name
        self.primary_region = primary_region
        self.secondary_region = secondary_region
        self.state_table_name = state_table_name
        self.health_check_interval = health_check_interval
        self.failure_threshold = failure_threshold
        self.cooldown_minutes = cooldown_minutes
        self.notification_emails = notification_emails or []

        # Create SNS topic
        self.notification_topic = self._create_notification_topic()

        # Create failover Lambda
        self.failover_function = self._create_failover_function()

        # Create health check Lambda
        self.health_check_function = self._create_health_check_function()

        # Create EventBridge rule
        self.health_check_rule = self._create_health_check_rule()

        # Outputs
        self._create_outputs()

    def _create_notification_topic(self) -> sns.Topic:
        """Create SNS topic for notifications"""
        topic = sns.Topic(
            self,
            "NotificationTopic",
            topic_name=f"{self.project_name}-automated-failover-{self.env_name}",
            display_name="MWAA Automated Failover Notifications"
        )

        for email in self.notification_emails:
            topic.add_subscription(
                subscriptions.EmailSubscription(email)
            )

        return topic

    def _create_failover_function(self) -> lambda_.Function:
        """Create failover Lambda function"""
        function = lambda_.Function(
            self,
            "FailoverFunction",
            function_name=f"{self.project_name}-automated-failover-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="failover.lambda_handler",
            code=lambda_.Code.from_asset("lambda"),
            timeout=Duration.minutes(5),
            memory_size=256,
            environment={
                "PRIMARY_ENV_NAME": self.primary_env_name,
                "SECONDARY_ENV_NAME": self.secondary_env_name,
                "PRIMARY_REGION": self.primary_region,
                "SECONDARY_REGION": self.secondary_region,
                "STATE_TABLE_NAME": self.state_table_name,
                "NOTIFICATION_TOPIC_ARN": self.notification_topic.topic_arn,
            }
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
                    f"arn:aws:airflow:{self.primary_region}:{self.account}:environment/{self.primary_env_name}",
                    f"arn:aws:airflow:{self.secondary_region}:{self.account}:environment/{self.secondary_env_name}"
                ]
            )
        )

        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.state_table_name}"
                ]
            )
        )

        self.notification_topic.grant_publish(function)

        return function

    def _create_health_check_function(self) -> lambda_.Function:
        """Create health check Lambda function"""
        function = lambda_.Function(
            self,
            "HealthCheckFunction",
            function_name=f"{self.project_name}-health-check-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="health_check.lambda_handler",
            code=lambda_.Code.from_asset("lambda"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "PRIMARY_ENV_NAME": self.primary_env_name,
                "PRIMARY_REGION": self.primary_region,
                "SECONDARY_REGION": self.secondary_region,
                "STATE_TABLE_NAME": self.state_table_name,
                "FAILURE_THRESHOLD": str(self.failure_threshold),
                "COOLDOWN_MINUTES": str(self.cooldown_minutes),
                "NOTIFICATION_TOPIC_ARN": self.notification_topic.topic_arn,
                "FAILOVER_FUNCTION_ARN": self.failover_function.function_arn,
            }
        )

        # Grant permissions
        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "airflow:GetEnvironment"
                ],
                resources=[
                    f"arn:aws:airflow:{self.primary_region}:{self.account}:environment/{self.primary_env_name}"
                ]
            )
        )

        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudwatch:GetMetricStatistics"
                ],
                resources=["*"]
            )
        )

        function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.state_table_name}"
                ]
            )
        )

        self.notification_topic.grant_publish(function)

        # Allow health check to invoke failover
        self.failover_function.grant_invoke(function)

        return function

    def _create_health_check_rule(self) -> events.Rule:
        """Create EventBridge rule for periodic health checks"""
        rule = events.Rule(
            self,
            "HealthCheckRule",
            rule_name=f"{self.project_name}-health-check-{self.env_name}",
            description="Periodic MWAA health check for automated failover",
            schedule=events.Schedule.expression(self.health_check_interval),
            enabled=True
        )

        rule.add_target(
            targets.LambdaFunction(self.health_check_function)
        )

        return rule

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "HealthCheckFunctionArn",
            value=self.health_check_function.function_arn,
            description="Health check Lambda function ARN"
        )

        CfnOutput(
            self,
            "FailoverFunctionArn",
            value=self.failover_function.function_arn,
            description="Failover Lambda function ARN"
        )

        CfnOutput(
            self,
            "NotificationTopicArn",
            value=self.notification_topic.topic_arn,
            description="SNS topic for notifications"
        )

        CfnOutput(
            self,
            "HealthCheckSchedule",
            value=self.health_check_interval,
            description="Health check schedule"
        )

        CfnOutput(
            self,
            "FailureThreshold",
            value=str(self.failure_threshold),
            description="Consecutive failures before failover"
        )
