"""
Marquez Stack - EC2 instance running Marquez in Docker
"""
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_kms as kms,
    CfnOutput,
    Duration,
)
from constructs import Construct


class MarquezStack(Stack):
    """Creates Marquez lineage server on EC2"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        marquez_sg: ec2.SecurityGroup,
        project_name: str,
        environment: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # IAM Role for Marquez EC2 instance
        marquez_role = iam.Role(
            self,
            "MarquezInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchAgentServerPolicy"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
            description="IAM role for Marquez EC2 instance",
        )

        # User data script to install and run Marquez
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "#!/bin/bash",
            "set -e",
            "",
            "# Update system",
            "yum update -y",
            "",
            "# Install Docker",
            "yum install -y docker git",
            "systemctl enable docker",
            "systemctl start docker",
            "",
            "# Install Docker Compose",
            "mkdir -p /usr/local/lib/docker/cli-plugins/",
            "curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose",
            "chmod +x /usr/local/lib/docker/cli-plugins/docker-compose",
            "",
            "# Add ec2-user to docker group",
            "usermod -aG docker ec2-user",
            "",
            "# Clone Marquez",
            "cd /home/ec2-user",
            "sudo -u ec2-user git clone https://github.com/MarquezProject/marquez.git",
            "cd marquez",
            "",
            "# Start Marquez (using latest stable version)",
            "sudo -u ec2-user ./docker/up.sh --tag 0.42.0 --detach",
            "",
            "# Wait for Marquez to be ready",
            "echo 'Waiting for Marquez to start...'",
            "for i in {1..30}; do",
            "  if curl -s http://localhost:5000/api/v1/namespaces > /dev/null 2>&1; then",
            "    echo 'Marquez is ready!'",
            "    break",
            "  fi",
            "  echo 'Waiting...'",
            "  sleep 10",
            "done",
            "",
            "# Create systemd service for auto-restart on reboot",
            "cat > /etc/systemd/system/marquez.service << 'EOF'",
            "[Unit]",
            "Description=Marquez Lineage Server",
            "After=docker.service",
            "Requires=docker.service",
            "",
            "[Service]",
            "Type=oneshot",
            "RemainAfterExit=yes",
            "WorkingDirectory=/home/ec2-user/marquez",
            "ExecStart=/bin/bash -c 'cd /home/ec2-user/marquez && sudo -u ec2-user ./docker/up.sh --tag 0.42.0 --detach'",
            "ExecStop=/bin/bash -c 'cd /home/ec2-user/marquez && sudo -u ec2-user docker compose down'",
            "User=root",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "EOF",
            "",
            "systemctl daemon-reload",
            "systemctl enable marquez.service",
            "",
            "echo 'Marquez installation complete!'",
        )

        # EC2 Instance for Marquez (in private subnet)
        marquez_instance = ec2.Instance(
            self,
            "MarquezInstance",
            instance_name=f"{project_name}-marquez-{environment}",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MEDIUM,
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_group=marquez_sg,
            role=marquez_role,
            user_data=user_data,
            user_data_causes_replacement=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=30,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        delete_on_termination=True,
                        encrypted=True,  # Explicit EBS encryption
                    ),
                )
            ],
        )

        # Store URLs for use by other stacks
        self.marquez_api_url = f"http://{marquez_instance.instance_private_dns_name}:5000"
        self.marquez_ui_url = f"http://{marquez_instance.instance_private_dns_name}:3000"

        # Outputs
        CfnOutput(
            self,
            "MarquezInstanceId",
            value=marquez_instance.instance_id,
            description="Marquez EC2 Instance ID",
            export_name=f"{project_name}-marquez-instance-{environment}",
        )

        CfnOutput(
            self,
            "MarquezPrivateIp",
            value=marquez_instance.instance_private_ip,
            description="Marquez Private IP",
        )

        CfnOutput(
            self,
            "MarquezApiUrl",
            value=self.marquez_api_url,
            description="Marquez API URL (private)",
            export_name=f"{project_name}-marquez-api-{environment}",
        )

        CfnOutput(
            self,
            "MarquezUiUrl",
            value=self.marquez_ui_url,
            description="Marquez UI URL (private - access via SSM or VPN)",
            export_name=f"{project_name}-marquez-ui-{environment}",
        )
