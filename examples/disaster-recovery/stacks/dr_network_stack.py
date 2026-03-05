"""
DR Network Stack - Minimal VPC for MWAA DR Example
"""
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
)
from constructs import Construct


class DRNetworkStack(Stack):
    """Creates minimal network infrastructure for MWAA DR example"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        env_name: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC with public and private subnets
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            vpc_name=f"{project_name}-dr-vpc-{env_name}",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # Security Group for MWAA
        self.mwaa_sg = ec2.SecurityGroup(
            self,
            "MwaaSecurityGroup",
            vpc=self.vpc,
            description="Security group for MWAA DR environment",
            allow_all_outbound=True,
        )

        # MWAA requires self-referencing rule
        self.mwaa_sg.add_ingress_rule(
            peer=self.mwaa_sg,
            connection=ec2.Port.all_traffic(),
            description="Allow all traffic within MWAA security group",
        )

        # Outputs
        CfnOutput(
            self,
            "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID",
            export_name=f"{project_name}-dr-vpc-id-{env_name}",
        )

        CfnOutput(
            self,
            "MwaaSecurityGroupId",
            value=self.mwaa_sg.security_group_id,
            description="MWAA Security Group ID",
            export_name=f"{project_name}-dr-mwaa-sg-{env_name}",
        )
