"""
DR S3 Stack - S3 Bucket for MWAA Assets
"""
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct


class DRS3Stack(Stack):
    """Creates S3 bucket for MWAA assets (DAGs, plugins, requirements)"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        env_name: str,
        region_name: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 Bucket for MWAA - using default encryption
        self.mwaa_bucket = s3.Bucket(
            self,
            "MwaaBucket",
            bucket_name=f"{project_name}-dr-{region_name}-{env_name}-{self.account}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Outputs
        CfnOutput(
            self,
            "MwaaBucketName",
            value=self.mwaa_bucket.bucket_name,
            description="S3 bucket for MWAA",
            export_name=f"{project_name}-dr-bucket-{region_name}-{env_name}",
        )

        CfnOutput(
            self,
            "MwaaBucketArn",
            value=self.mwaa_bucket.bucket_arn,
            description="S3 bucket ARN",
            export_name=f"{project_name}-dr-bucket-arn-{region_name}-{env_name}",
        )
