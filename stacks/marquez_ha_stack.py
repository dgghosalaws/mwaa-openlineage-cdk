"""
Marquez HA Stack - High Availability setup with RDS, ALB, and Auto Scaling
Fixed version with SSL support and no wait-for-db dependency
"""
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_rds as rds,
    aws_elasticloadbalancingv2 as elbv2,
    aws_autoscaling as autoscaling,
    aws_secretsmanager as secretsmanager,
    CfnOutput,
    Duration,
    RemovalPolicy,
)
from constructs import Construct
import json


class MarquezHAStack(Stack):
    """Creates highly available Marquez lineage server with RDS, ALB, and ASG"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        marquez_sg: ec2.SecurityGroup,
        project_name: str,
        environment: str,
        internet_facing: bool = False,  # Default to internal for security
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ========================================
        # 1. RDS PostgreSQL Database (Multi-AZ)
        # ========================================
        
        # Create a new security group for Marquez instances in HA mode
        # (Don't use the one from network stack to avoid circular dependencies)
        marquez_instance_sg = ec2.SecurityGroup(
            self,
            "MarquezInstanceSG",
            vpc=vpc,
            description="Security group for Marquez instances in ASG",
            allow_all_outbound=True,
        )
        
        # Allow MWAA to access Marquez instances
        marquez_instance_sg.add_ingress_rule(
            peer=marquez_sg,  # MWAA SG from network stack
            connection=ec2.Port.tcp(5000),
            description="Allow MWAA to access Marquez API",
        )
        
        # Security Group for RDS
        rds_sg = ec2.SecurityGroup(
            self,
            "MarquezRdsSG",
            vpc=vpc,
            description="Security group for Marquez RDS database",
            allow_all_outbound=True,
        )
        
        # Allow Marquez instances to connect to RDS
        rds_sg.add_ingress_rule(
            peer=marquez_instance_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow Marquez instances to connect to PostgreSQL",
        )

        # Database credentials in Secrets Manager
        db_credentials = secretsmanager.Secret(
            self,
            "MarquezDbCredentials",
            secret_name=f"{project_name}-marquez-db-{environment}",
            description="Marquez database credentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "marquez"}),
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=32,
            ),
        )

        # RDS PostgreSQL instance (Multi-AZ)
        db_instance = rds.DatabaseInstance(
            self,
            "MarquezDatabase",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.SMALL,
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[rds_sg],
            multi_az=True,  # Enable Multi-AZ for HA
            allocated_storage=20,
            max_allocated_storage=100,  # Enable storage autoscaling
            storage_type=rds.StorageType.GP3,
            database_name="marquez",
            credentials=rds.Credentials.from_secret(db_credentials),
            backup_retention=Duration.days(7),
            deletion_protection=False,  # Set to True for production
            removal_policy=RemovalPolicy.DESTROY,  # Change for production
            publicly_accessible=False,
        )

        # ========================================
        # 2. Application Load Balancer
        # ========================================
        
        # ALB Security Group (created in same stack to avoid circular dependency)
        alb_sg = ec2.SecurityGroup(
            self,
            "MarquezAlbSG",
            vpc=vpc,
            description="Security group for Marquez ALB",
            allow_all_outbound=True,
        )
        
        # Allow HTTP traffic to ALB (API on 5000 and UI on 3000)
        alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(5000),
            description="Allow HTTP traffic to Marquez API",
        )
        
        alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(3000),
            description="Allow HTTP traffic to Marquez UI",
        )

        # Allow ALB to connect to Marquez instances (API and UI)
        marquez_instance_sg.add_ingress_rule(
            peer=alb_sg,
            connection=ec2.Port.tcp(5000),
            description="Allow ALB to connect to Marquez API",
        )
        
        marquez_instance_sg.add_ingress_rule(
            peer=alb_sg,
            connection=ec2.Port.tcp(3000),
            description="Allow ALB to connect to Marquez UI",
        )

        # Application Load Balancer (configurable: internal or internet-facing)
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "MarquezALB",
            vpc=vpc,
            internet_facing=internet_facing,
            load_balancer_name=f"{project_name}-marquez-{environment}",
            security_group=alb_sg,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC if internet_facing else ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
        )

        # Target Group for Marquez API (port 5000)
        api_target_group = elbv2.ApplicationTargetGroup(
            self,
            "MarquezApiTargetGroup",
            vpc=vpc,
            port=5000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(
                path="/api/v1/namespaces",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
            deregistration_delay=Duration.seconds(30),
        )

        # Target Group for Marquez UI (port 3000)
        ui_target_group = elbv2.ApplicationTargetGroup(
            self,
            "MarquezUiTargetGroup",
            vpc=vpc,
            port=3000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(
                path="/",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
            deregistration_delay=Duration.seconds(30),
        )

        # Listener for API (port 5000)
        alb.add_listener(
            "ApiListener",
            port=5000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[api_target_group],
        )

        # Listener for UI (port 3000)
        alb.add_listener(
            "UiListener",
            port=3000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[ui_target_group],
        )

        # ========================================
        # 3. IAM Role for Marquez Instances
        # ========================================
        
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
            description="IAM role for Marquez EC2 instances in ASG",
        )

        # Grant read access to database credentials
        db_credentials.grant_read(marquez_role)

        # ========================================
        # 4. User Data Script
        # ========================================
        
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "#!/bin/bash",
            "",
            "# Update system and clean cache",
            "yum clean all",
            "yum update -y",
            "",
            "# Install Docker, AWS CLI, and gettext (for envsubst) - with retries",
            "for i in {1..3}; do",
            "  yum install -y docker git aws-cli jq gettext && break || sleep 10",
            "done",
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
            "# Get database credentials from Secrets Manager",
            f"DB_SECRET=$(aws secretsmanager get-secret-value --secret-id {db_credentials.secret_name} --region {self.region} --query SecretString --output text)",
            "DB_USER=$(echo $DB_SECRET | jq -r .username)",
            "DB_PASS=$(echo $DB_SECRET | jq -r .password)",
            f"DB_HOST={db_instance.db_instance_endpoint_address}",
            f"DB_PORT={db_instance.db_instance_endpoint_port}",
            "DB_NAME=marquez",
            "",
            "# Note: Using Docker Hub images (no ECR setup required)",
            "# For production with many instances, consider mirroring to ECR to avoid rate limits",
            "",
            "# Create Marquez configuration directory",
            "mkdir -p /opt/marquez",
            "cd /opt/marquez",
            "",
            "# Create Marquez SSL configuration file with actual values (no placeholders)",
            "cat > marquez-ssl.yml << MARQUEZ_CONFIG_EOF",
            "server:",
            "  applicationConnectors:",
            "    - type: http",
            "      port: 5000",
            "  adminConnectors:",
            "    - type: http",
            "      port: 5001",
            "",
            "db:",
            "  driverClass: org.postgresql.Driver",
            f"  url: jdbc:postgresql://{db_instance.db_instance_endpoint_address}:{db_instance.db_instance_endpoint_port}/marquez?ssl=true&sslmode=require",
            "  user: $DB_USER",
            "  password: $DB_PASS",
            "",
            "logging:",
            "  level: INFO",
            "  appenders:",
            "    - type: console",
            "MARQUEZ_CONFIG_EOF",
            "",
            "# Substitute only DB credentials (URL is already complete)",
            "sed -i \"s/\\$DB_USER/$DB_USER/g\" marquez-ssl.yml",
            "sed -i \"s/\\$DB_PASS/$DB_PASS/g\" marquez-ssl.yml",
            "",
            "# Create docker-compose.yml without wait-for-db (Marquez handles retries)",
            "cat > docker-compose.yml << COMPOSE_EOF",
            "version: '3.7'",
            "services:",
            "  marquez-api:",
            "    image: marquezproject/marquez:0.42.0",
            "    container_name: marquez-api",
            "    ports:",
            "      - '5000:5000'",
            "      - '5001:5001'",
            "    environment:",
            "      - MARQUEZ_PORT=5000",
            "      - MARQUEZ_ADMIN_PORT=5001",
            "      - MARQUEZ_CONFIG=/usr/src/app/marquez-ssl.yml",
            "    restart: unless-stopped",
            "    volumes:",
            "      - /opt/marquez/marquez-ssl.yml:/usr/src/app/marquez-ssl.yml:ro",
            "",
            "  marquez-web:",
            "    image: marquezproject/marquez-web:0.42.0",
            "    container_name: marquez-web",
            "    ports:",
            "      - '3000:3000'",
            "    environment:",
            "      - MARQUEZ_HOST=marquez-api",
            "      - MARQUEZ_PORT=5000",
            "    depends_on:",
            "      - marquez-api",
            "    restart: unless-stopped",
            "COMPOSE_EOF",
            "",
            "# Start Marquez",
            "docker compose up -d",
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
            "# Create systemd service for auto-restart",
            "cat > /etc/systemd/system/marquez.service << 'SERVICE_EOF'",
            "[Unit]",
            "Description=Marquez Lineage Server",
            "After=docker.service",
            "Requires=docker.service",
            "",
            "[Service]",
            "Type=oneshot",
            "RemainAfterExit=yes",
            "WorkingDirectory=/opt/marquez",
            "ExecStart=/usr/local/lib/docker/cli-plugins/docker-compose up -d",
            "ExecStop=/usr/local/lib/docker/cli-plugins/docker-compose down",
            "User=root",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "SERVICE_EOF",
            "",
            "systemctl daemon-reload",
            "systemctl enable marquez.service",
            "",
            "echo 'Marquez HA installation complete!'",
        )

        # ========================================
        # 5. Launch Template
        # ========================================
        
        launch_template = ec2.LaunchTemplate(
            self,
            "MarquezLaunchTemplate",
            launch_template_name=f"{project_name}-marquez-{environment}",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MEDIUM,
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=marquez_instance_sg,
            role=marquez_role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=30,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        delete_on_termination=True,
                    ),
                )
            ],
        )

        # ========================================
        # 6. Auto Scaling Group
        # ========================================
        
        asg = autoscaling.AutoScalingGroup(
            self,
            "MarquezASG",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            launch_template=launch_template,
            min_capacity=2,  # Minimum 2 instances for HA
            max_capacity=4,  # Maximum 4 instances
            desired_capacity=2,  # Start with 2 instances
            health_check=autoscaling.HealthCheck.elb(
                grace=Duration.minutes(5),
            ),
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                max_batch_size=1,
                min_instances_in_service=1,
                pause_time=Duration.minutes(5),
            ),
        )

        # Attach ASG to both API and UI target groups
        asg.attach_to_application_target_group(api_target_group)
        asg.attach_to_application_target_group(ui_target_group)

        # CPU-based scaling
        asg.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            cooldown=Duration.minutes(5),
        )

        # ========================================
        # 7. Outputs
        # ========================================
        
        # Store URLs for use by other stacks (using internal ALB DNS)
        self.marquez_api_url = f"http://{alb.load_balancer_dns_name}:5000"

        CfnOutput(
            self,
            "MarquezAlbDnsName",
            value=alb.load_balancer_dns_name,
            description=f"Marquez {'Internet-facing' if internet_facing else 'Internal'} ALB DNS Name",
            export_name=f"{project_name}-marquez-alb-{environment}",
        )

        CfnOutput(
            self,
            "MarquezApiUrl",
            value=self.marquez_api_url,
            description=f"Marquez API URL (via {'Internet-facing' if internet_facing else 'Internal'} ALB)",
            export_name=f"{project_name}-marquez-api-{environment}",
        )

        CfnOutput(
            self,
            "MarquezDbEndpoint",
            value=db_instance.db_instance_endpoint_address,
            description="Marquez RDS Database Endpoint",
        )

        CfnOutput(
            self,
            "MarquezAsgName",
            value=asg.auto_scaling_group_name,
            description="Marquez Auto Scaling Group Name",
        )
