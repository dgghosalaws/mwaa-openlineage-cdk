"""
MWAA stack for performance testing.
Stripped-down MWAA environment — no Marquez/OpenLineage.
Configured for high DAG count and sustained load testing.
"""
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_iam as iam,
    aws_mwaa as mwaa,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct


class MwaaPerfStack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        mwaa_sg: ec2.SecurityGroup,
        env_name: str,
        environment_class: str = "mw1.2xlarge",
        min_workers: int = 20,
        max_workers: int = 50,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket for DAGs and requirements
        self.bucket = s3.Bucket(
            self, "MwaaBucket",
            bucket_name=f"{env_name}-{self.account}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # MWAA execution role
        role = iam.Role(
            self, "MwaaRole",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("airflow.amazonaws.com"),
                iam.ServicePrincipal("airflow-env.amazonaws.com"),
            ),
        )

        self.bucket.grant_read_write(role)

        # Deploy requirements.txt to bucket root
        req_deployment = s3deploy.BucketDeployment(
            self, "DeployRequirements",
            sources=[s3deploy.Source.asset("../", exclude=["*", "!requirements.txt"])],
            destination_bucket=self.bucket,
            destination_key_prefix="",
            prune=False,
        )

        role.add_to_policy(iam.PolicyStatement(
            actions=["airflow:PublishMetrics"],
            resources=[f"arn:aws:airflow:{self.region}:{self.account}:environment/{env_name}"],
        ))

        role.add_to_policy(iam.PolicyStatement(
            actions=[
                "logs:CreateLogStream", "logs:CreateLogGroup",
                "logs:PutLogEvents", "logs:GetLogEvents",
                "logs:GetLogRecord", "logs:GetLogGroupFields",
                "logs:GetQueryResults",
            ],
            resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:airflow-{env_name}-*"],
        ))

        role.add_to_policy(iam.PolicyStatement(
            actions=["logs:DescribeLogGroups", "cloudwatch:PutMetricData"],
            resources=["*"],
        ))

        role.add_to_policy(iam.PolicyStatement(
            actions=[
                "sqs:ChangeMessageVisibility", "sqs:DeleteMessage",
                "sqs:GetQueueAttributes", "sqs:GetQueueUrl",
                "sqs:ReceiveMessage", "sqs:SendMessage",
            ],
            resources=[f"arn:aws:sqs:{self.region}:*:airflow-celery-*"],
        ))

        # KMS permissions for SQS (MWAA Celery broker uses KMS-encrypted SQS)
        role.add_to_policy(iam.PolicyStatement(
            actions=["kms:Decrypt", "kms:DescribeKey", "kms:GenerateDataKey*", "kms:Encrypt"],
            resources=["*"],
            conditions={"StringLike": {"kms:ViaService": [f"sqs.{self.region}.amazonaws.com"]}},
        ))

        private_subnet_ids = [subnet.subnet_id for subnet in vpc.private_subnets]

        self.mwaa_env = mwaa.CfnEnvironment(
            self, "MwaaEnv",
            name=env_name,
            airflow_version="3.0.6",
            environment_class=environment_class,
            min_workers=min_workers,
            max_workers=max_workers,
            schedulers=3,
            execution_role_arn=role.role_arn,
            source_bucket_arn=self.bucket.bucket_arn,
            dag_s3_path="dags",
            requirements_s3_path="requirements.txt",
            network_configuration=mwaa.CfnEnvironment.NetworkConfigurationProperty(
                security_group_ids=[mwaa_sg.security_group_id],
                subnet_ids=private_subnet_ids,
            ),
            logging_configuration=mwaa.CfnEnvironment.LoggingConfigurationProperty(
                dag_processing_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(enabled=True, log_level="INFO"),
                scheduler_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(enabled=True, log_level="INFO"),
                task_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(enabled=True, log_level="INFO"),
                webserver_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(enabled=True, log_level="INFO"),
                worker_logs=mwaa.CfnEnvironment.ModuleLoggingConfigurationProperty(enabled=True, log_level="INFO"),
            ),
            airflow_configuration_options={
                "core.lazy_load_plugins": "false",
                "core.load_default_connections": "false",
                "core.load_examples": "false",
                # High import timeout for large DAG sets (hit 30s default with dag-factory YAMLs)
                "core.dagbag_import_timeout": "600",
                # Concurrency for performance testing
                "core.default_pool_task_slot_count": "5000",
                "core.max_active_tasks_per_dag": "5000",
                # Prevent premature task failures during sustained load
                "scheduler.task_queued_timeout": "3600",
            },
            webserver_access_mode="PUBLIC_ONLY",
            weekly_maintenance_window_start="SUN:03:00",
        )

        # Ensure requirements.txt is uploaded before MWAA tries to read it
        self.mwaa_env.node.add_dependency(req_deployment)

        CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
        CfnOutput(self, "EnvironmentName", value=self.mwaa_env.name)
        CfnOutput(self, "WebserverUrl", value=f"https://{self.mwaa_env.attr_webserver_url}")
