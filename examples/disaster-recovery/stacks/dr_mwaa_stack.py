"""
DR MWAA Stack - Minimal MWAA with DR Plugin
"""
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_iam as iam,
    aws_mwaa as mwaa,
    aws_dynamodb as dynamodb,
    CfnOutput,
)
from constructs import Construct


class DRMwaaStack(Stack):
    """Creates minimal MWAA environment with DR plugin"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        mwaa_sg: ec2.SecurityGroup,
        mwaa_bucket: s3.IBucket,
        dr_state_table: dynamodb.Table,
        project_name: str,
        env_name: str,
        region_name: str,
        primary_region: str,
        environment_class: str = "mw1.small",
        min_workers: int = 1,
        max_workers: int = 2,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # IAM Role for MWAA
        mwaa_role = iam.Role(
            self,
            "MwaaExecutionRole",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("airflow.amazonaws.com"),
                iam.ServicePrincipal("airflow-env.amazonaws.com"),
            ),
            description="Execution role for MWAA DR environment",
        )

        # Grant S3 permissions
        mwaa_bucket.grant_read_write(mwaa_role)

        # Grant DynamoDB read permissions for DR state
        dr_state_table.grant_read_data(mwaa_role)

        # Additional permissions for MWAA
        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "airflow:PublishMetrics",
                ],
                resources=[
                    f"arn:aws:airflow:{self.region}:{self.account}:environment/{project_name}-dr-{region_name}-{env_name}",
                ],
            )
        )

        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogStream",
                    "logs:CreateLogGroup",
                    "logs:PutLogEvents",
                    "logs:GetLogEvents",
                    "logs:GetLogRecord",
                    "logs:GetLogGroupFields",
                    "logs:GetQueryResults",
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:airflow-{project_name}-dr-{region_name}-{env_name}-*",
                ],
            )
        )

        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:DescribeLogGroups",
                ],
                resources=["*"],
            )
        )

        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudwatch:PutMetricData",
                ],
                resources=["*"],
            )
        )

        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sqs:ChangeMessageVisibility",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                    "sqs:ReceiveMessage",
                    "sqs:SendMessage",
                ],
                resources=[
                    f"arn:aws:sqs:{self.region}:*:airflow-celery-*",
                ],
            )
        )

        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "kms:Decrypt",
                    "kms:DescribeKey",
                    "kms:GenerateDataKey*",
                    "kms:Encrypt",
                ],
                resources=["*"],
                conditions={
                    "StringLike": {
                        "kms:ViaService": [
                            f"sqs.{self.region}.amazonaws.com",
                        ]
                    }
                },
            )
        )
        private_subnet_ids = [subnet.subnet_id for subnet in vpc.private_subnets]

        # MWAA Environment with DR configuration
        # Note: S3 bucket must already have DAGs and requirements uploaded
        # DR is managed by automated failover Lambda (pauses/unpauses DAGs)
        # Using MWAA's default AWS-managed encryption
        self.mwaa_environment = mwaa.CfnEnvironment(
            self,
            "MwaaEnvironment",
            name=f"{project_name}-dr-{region_name}-{env_name}",
            airflow_version="3.0.6",
            environment_class=environment_class,
            min_workers=min_workers,
            max_workers=max_workers,
            execution_role_arn=mwaa_role.role_arn,
            source_bucket_arn=mwaa_bucket.bucket_arn,
            dag_s3_path="dags",
            requirements_s3_path="requirements.txt",
            network_configuration=mwaa.CfnEnvironment.NetworkConfigurationProperty(
                security_group_ids=[mwaa_sg.security_group_id],
                subnet_ids=private_subnet_ids,
            ),
            logging_configuration=mwaa.CfnEnvironment.LoggingConfigurationProperty(
                dag_processing_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                    enabled=True,
                    log_level="INFO",
                ),
                scheduler_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                    enabled=True,
                    log_level="INFO",
                ),
                task_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                    enabled=True,
                    log_level="INFO",
                ),
                webserver_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                    enabled=True,
                    log_level="INFO",
                ),
                worker_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(
                    enabled=True,
                    log_level="INFO",
                ),
            ),
            airflow_configuration_options={
                "core.load_default_connections": "false",
                "core.load_examples": "false",
            },
            webserver_access_mode="PUBLIC_ONLY",
            weekly_maintenance_window_start="SUN:03:00",
        )

        # Outputs
        CfnOutput(
            self,
            "MwaaEnvironmentName",
            value=self.mwaa_environment.name,
            description="MWAA Environment Name",
        )

        CfnOutput(
            self,
            "MwaaWebserverUrl",
            value=f"https://{self.mwaa_environment.attr_webserver_url}",
            description="MWAA Webserver URL",
        )

        CfnOutput(
            self,
            "DRRegion",
            value=region_name,
            description="DR Region Name",
        )
