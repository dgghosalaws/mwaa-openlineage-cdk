"""
MWAA Stack - Managed Airflow with OpenLineage integration for Airflow 3.0
Uses native apache-airflow-providers-openlineage (no custom plugins needed)
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
import json


class MwaaStack(Stack):
    """Creates MWAA environment with OpenLineage integration for Airflow 3.0"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        mwaa_sg: ec2.SecurityGroup,
        marquez_url: str,
        project_name: str,
        environment: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 Bucket for MWAA
        mwaa_bucket = s3.Bucket(
            self,
            "MwaaBucket",
            bucket_name=f"{project_name}-mwaa-{environment}-{self.account}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Deploy requirements.txt to bucket root and DAGs to dags/ folder
        # MWAA expects: s3://bucket/requirements.txt and s3://bucket/dags/
        # Deploy requirements.txt from root directory
        requirements_deployment = s3deploy.BucketDeployment(
            self,
            "DeployRequirements",
            sources=[s3deploy.Source.asset("./assets/root")],
            destination_bucket=mwaa_bucket,
            destination_key_prefix="",
            prune=False,
        )

        # Deploy DAGs to dags/ folder
        dags_deployment = s3deploy.BucketDeployment(
            self,
            "DeployDags",
            sources=[s3deploy.Source.asset("./assets/dags")],
            destination_bucket=mwaa_bucket,
            destination_key_prefix="dags",
            prune=False,
        )

        # IAM Role for MWAA
        mwaa_role = iam.Role(
            self,
            "MwaaExecutionRole",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("airflow.amazonaws.com"),
                iam.ServicePrincipal("airflow-env.amazonaws.com"),
            ),
            description="Execution role for MWAA environment",
        )

        # Grant S3 permissions
        mwaa_bucket.grant_read_write(mwaa_role)

        # Additional permissions for MWAA
        mwaa_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "airflow:PublishMetrics",
                ],
                resources=[
                    f"arn:aws:airflow:{self.region}:{self.account}:environment/{project_name}-{environment}",
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
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:airflow-{project_name}-{environment}-*",
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

        # Get private subnets for MWAA
        private_subnet_ids = [subnet.subnet_id for subnet in vpc.private_subnets]

        # MWAA Environment with Airflow 3.0
        # Note: For Airflow 3.0, we use listener approach (not lineage.backend)
        mwaa_environment = mwaa.CfnEnvironment(
            self,
            "MwaaEnvironment",
            name=f"{project_name}-{environment}",
            airflow_version="3.0.6",
            environment_class="mw1.small",
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
                # Airflow 3.0 uses lowercase "false" not "False"
                "core.lazy_load_plugins": "false",
                "core.load_default_connections": "false",
                "core.load_examples": "false",
                # OpenLineage configuration using native provider (Airflow 3.0+)
                # No plugins needed - provider handles everything automatically
                "openlineage.transport": json.dumps({
                    "type": "http",
                    "url": marquez_url,
                    "endpoint": "api/v1/lineage"
                }),
                "openlineage.namespace": f"{project_name}-{environment}",
                "openlineage.disabled": "False",
            },
            webserver_access_mode="PUBLIC_ONLY",
            weekly_maintenance_window_start="SUN:03:00",
        )

        # Ensure S3 files are deployed before MWAA environment is created
        mwaa_environment.node.add_dependency(requirements_deployment)
        mwaa_environment.node.add_dependency(dags_deployment)

        # Outputs
        CfnOutput(
            self,
            "MwaaBucketName",
            value=mwaa_bucket.bucket_name,
            description="S3 bucket for MWAA",
            export_name=f"{project_name}-mwaa-bucket-{environment}",
        )

        CfnOutput(
            self,
            "MwaaEnvironmentName",
            value=mwaa_environment.name,
            description="MWAA Environment Name",
            export_name=f"{project_name}-mwaa-env-{environment}",
        )

        CfnOutput(
            self,
            "MwaaWebserverUrl",
            value=f"https://{mwaa_environment.attr_webserver_url}",
            description="MWAA Webserver URL",
        )

        CfnOutput(
            self,
            "OpenLineageUrl",
            value=marquez_url,
            description="OpenLineage/Marquez URL configured for MWAA",
        )

        CfnOutput(
            self,
            "AirflowVersion",
            value="3.0.6",
            description="Airflow version deployed",
        )
