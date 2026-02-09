"""
Network Stack - VPC, Subnets, Security Groups
"""
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
)
from constructs import Construct


class NetworkStack(Stack):
    """Creates network infrastructure for MWAA and Marquez"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        environment: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC with public and private subnets
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            vpc_name=f"{project_name}-vpc-{environment}",
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

        # Security Group for Marquez
        self.marquez_sg = ec2.SecurityGroup(
            self,
            "MarquezSecurityGroup",
            vpc=self.vpc,
            description="Security group for Marquez server",
            allow_all_outbound=True,
        )

        # Allow HTTP access to Marquez API (port 5000)
        self.marquez_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5000),
            description="Allow Marquez API access from VPC",
        )

        # Allow HTTP access to Marquez UI (port 3000)
        self.marquez_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(3000),
            description="Allow Marquez UI access from VPC",
        )

        # Allow SSH for management (optional - can be removed for production)
        self.marquez_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(22),
            description="Allow SSH access",
        )

        # Security Group for MWAA
        self.mwaa_sg = ec2.SecurityGroup(
            self,
            "MwaaSecurityGroup",
            vpc=self.vpc,
            description="Security group for MWAA environment",
            allow_all_outbound=True,
        )

        # MWAA requires self-referencing rule
        self.mwaa_sg.add_ingress_rule(
            peer=self.mwaa_sg,
            connection=ec2.Port.all_traffic(),
            description="Allow all traffic within MWAA security group",
        )

        # Allow MWAA to access Marquez
        self.marquez_sg.add_ingress_rule(
            peer=self.mwaa_sg,
            connection=ec2.Port.tcp(5000),
            description="Allow MWAA to access Marquez API",
        )

        # Outputs
        CfnOutput(
            self,
            "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID",
            export_name=f"{project_name}-vpc-id-{environment}",
        )

        CfnOutput(
            self,
            "MarquezSecurityGroupId",
            value=self.marquez_sg.security_group_id,
            description="Marquez Security Group ID",
            export_name=f"{project_name}-marquez-sg-{environment}",
        )

        CfnOutput(
            self,
            "MwaaSecurityGroupId",
            value=self.mwaa_sg.security_group_id,
            description="MWAA Security Group ID",
            export_name=f"{project_name}-mwaa-sg-{environment}",
        )
