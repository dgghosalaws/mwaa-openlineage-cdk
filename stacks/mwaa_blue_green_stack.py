"""
MWAA Blue-Green Stack - Dual MWAA environments for zero-downtime maintenance
Supports weekly rotation between Blue and Green environments
"""
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_iam as iam,
    aws_mwaa as mwaa,
    aws_kms as kms,
    aws_ssm as ssm,
    aws_route53 as route53,
    CfnOutput,
    RemovalPolicy,
    Duration,
)
from constructs import Construct
import json
from datetime import datetime, timezone


class MwaaBlueGreenStack(Stack):
    """Creates Blue and Green MWAA environments with OpenLineage integration"""

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

        # Shared KMS Key for both environments
        shared_kms_key = kms.Key(
            self,
            "SharedS3Key",
            description=f"Shared KMS key for {project_name} Blue-Green MWAA S3 buckets",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Parameter Store for zero-downtime switching
        # This parameter controls which environment is active
        active_env_parameter = ssm.StringParameter(
            self,
            "ActiveEnvironmentParameter",
            parameter_name="/mwaa/blue-green/active-environment",
            string_value="blue",  # Blue starts as active
            description="Active MWAA environment for zero-downtime blue-green switching",
            tier=ssm.ParameterTier.STANDARD,
        )

        # Create Blue and Green environments
        self.blue_env = self._create_mwaa_environment(
            color="blue",
            vpc=vpc,
            mwaa_sg=mwaa_sg,
            marquez_url=marquez_url,
            project_name=project_name,
            environment=environment,
            kms_key=shared_kms_key,
            is_active=True,  # Blue starts as active
        )

        self.green_env = self._create_mwaa_environment(
            color="green",
            vpc=vpc,
            mwaa_sg=mwaa_sg,
            marquez_url=marquez_url,
            project_name=project_name,
            environment=environment,
            kms_key=shared_kms_key,
            is_active=False,  # Green starts as standby
        )

        # Note: Blue and Green environments can be created in parallel
        # MWAA API handles concurrent environment creation without conflicts

        # Outputs for both environments
        CfnOutput(
            self,
            "BlueEnvironmentName",
            value=self.blue_env["environment"].name,
            description="Blue MWAA Environment Name",
        )

        CfnOutput(
            self,
            "BlueWebserverUrl",
            value=f"https://{self.blue_env['environment'].attr_webserver_url}",
            description="Blue MWAA Webserver URL",
        )

        CfnOutput(
            self,
            "GreenEnvironmentName",
            value=self.green_env["environment"].name,
            description="Green MWAA Environment Name",
        )

        CfnOutput(
            self,
            "GreenWebserverUrl",
            value=f"https://{self.green_env['environment'].attr_webserver_url}",
            description="Green MWAA Webserver URL",
        )

        CfnOutput(
            self,
            "SwitchInstructions",
            value="Use switch_mwaa_environment.py script to switch between Blue and Green",
            description="How to switch environments",
        )

    def _create_mwaa_environment(
        self,
        color: str,
        vpc: ec2.Vpc,
        mwaa_sg: ec2.SecurityGroup,
        marquez_url: str,
        project_name: str,
        environment: str,
        kms_key: kms.Key,
        is_active: bool,
    ) -> dict:
        """Create a single MWAA environment (Blue or Green)"""

        # S3 Bucket for this environment with S3-managed encryption
        # Using S3_MANAGED instead of KMS to avoid VPC endpoint requirements
        bucket = s3.Bucket(
            self,
            f"{color.capitalize()}Bucket",
            bucket_name=f"{project_name}-mwaa-{color}-{environment}-{self.region}-{self.account}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Deploy requirements.txt
        requirements_deployment = s3deploy.BucketDeployment(
            self,
            f"Deploy{color.capitalize()}Requirements",
            sources=[s3deploy.Source.asset("./assets/root")],
            destination_bucket=bucket,
            destination_key_prefix="",
            prune=False,
        )

        # Deploy DAGs
        dags_deployment = s3deploy.BucketDeployment(
            self,
            f"Deploy{color.capitalize()}Dags",
            sources=[s3deploy.Source.asset("./assets/dags")],
            destination_bucket=bucket,
            destination_key_prefix="dags",
            prune=False,
        )

        # IAM Role
        role = iam.Role(
            self,
            f"{color.capitalize()}ExecutionRole",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("airflow.amazonaws.com"),
                iam.ServicePrincipal("airflow-env.amazonaws.com"),
            ),
            description=f"Execution role for {color.capitalize()} MWAA environment",
        )

        # Grant S3 permissions
        bucket.grant_read_write(role)

        # Additional MWAA permissions
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["airflow:PublishMetrics"],
                resources=[
                    f"arn:aws:airflow:{self.region}:{self.account}:environment/{project_name}-{color}-{environment}",
                ],
            )
        )

        role.add_to_policy(
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
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:airflow-{project_name}-{color}-{environment}-*",
                ],
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:DescribeLogGroups"],
                resources=["*"],
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
            )
        )

        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sqs:ChangeMessageVisibility",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                    "sqs:ReceiveMessage",
                    "sqs:SendMessage",
                ],
                resources=[f"arn:aws:sqs:{self.region}:*:airflow-celery-*"],
            )
        )

        role.add_to_policy(
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
                        "kms:ViaService": [f"sqs.{self.region}.amazonaws.com"]
                    }
                },
            )
        )

        # Add SSM Parameter Store permissions for zero-downtime switching
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                ],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/mwaa/blue-green/*"
                ],
            )
        )

        # Get private subnets
        private_subnet_ids = [subnet.subnet_id for subnet in vpc.private_subnets]

        # Set environment variables based on active/standby status
        # Active environment: no end date (runs indefinitely)
        # Standby environment: has start date set to future (ready to take over)
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if is_active:
            # Active environment - no end date
            airflow_config = {
                "core.lazy_load_plugins": "false",
                "core.load_default_connections": "false",
                "core.load_examples": "false",
                "openlineage.transport": json.dumps({
                    "type": "http",
                    "url": marquez_url,
                    "endpoint": "api/v1/lineage"
                }),
                "openlineage.namespace": f"{project_name}-{color}-{environment}",
                "openlineage.disabled": "False",
                # Custom environment variables for Blue-Green switching
                "custom.environment_color": color,
                "custom.environment_status": "active",
                "custom.start_date": "2025-01-01",  # Default start date
                # No end_date for active environment
            }
        else:
            # Standby environment - ready to take over
            airflow_config = {
                "core.lazy_load_plugins": "false",
                "core.load_default_connections": "false",
                "core.load_examples": "false",
                "openlineage.transport": json.dumps({
                    "type": "http",
                    "url": marquez_url,
                    "endpoint": "api/v1/lineage"
                }),
                "openlineage.namespace": f"{project_name}-{color}-{environment}",
                "openlineage.disabled": "False",
                # Custom environment variables for Blue-Green switching
                "custom.environment_color": color,
                "custom.environment_status": "standby",
                "custom.start_date": current_time,  # Will be updated during switch
                # No end_date for standby (will be set when it becomes active)
            }

        # MWAA Environment (no KMS encryption to match original working stack)
        mwaa_environment = mwaa.CfnEnvironment(
            self,
            f"{color.capitalize()}Environment",
            name=f"{project_name}-{color}-{environment}",
            airflow_version="3.0.6",
            environment_class="mw1.small",
            execution_role_arn=role.role_arn,
            source_bucket_arn=bucket.bucket_arn,
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
            airflow_configuration_options=airflow_config,
            webserver_access_mode="PUBLIC_ONLY",
            weekly_maintenance_window_start="SUN:03:00",
            tags={
                "Environment": color,
                "Status": "active" if is_active else "standby",
                "Project": project_name,
            },
        )

        # Ensure S3 files are deployed before MWAA environment
        mwaa_environment.node.add_dependency(requirements_deployment)
        mwaa_environment.node.add_dependency(dags_deployment)

        return {
            "environment": mwaa_environment,
            "bucket": bucket,
            "role": role,
            "color": color,
        }
