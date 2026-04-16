"""
Minimal network stack for MWAA performance testing.
VPC with private subnets, NAT gateway, and MWAA security group.
"""
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
)
from constructs import Construct


class PerfTestNetworkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, env_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self, "VPC",
            vpc_name=f"{env_name}-vpc",
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

        self.mwaa_sg = ec2.SecurityGroup(
            self, "MwaaSG",
            vpc=self.vpc,
            description=f"Security group for {env_name} MWAA",
            allow_all_outbound=True,
        )

        # MWAA requires self-referencing rule
        self.mwaa_sg.add_ingress_rule(
            peer=self.mwaa_sg,
            connection=ec2.Port.all_traffic(),
            description="MWAA self-referencing rule",
        )

        CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
        CfnOutput(self, "MwaaSGId", value=self.mwaa_sg.security_group_id)
