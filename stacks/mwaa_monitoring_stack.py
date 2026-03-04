"""
MWAA Monitoring Stack - CloudWatch Dashboard for Performance Testing

Creates a comprehensive CloudWatch dashboard to monitor MWAA environment
performance during capacity and load testing.

Metrics monitored:
- Cluster (Scheduler, Workers, WebServer): CPU, Memory
- Database (Reader, Writer): CPU, Connections, Memory
- Queue: Queued Tasks, Running Tasks, Age of Oldest Task
"""

from aws_cdk import (
    Stack,
    aws_cloudwatch as cloudwatch,
    CfnOutput,
)
from constructs import Construct


class MwaaMonitoringStack(Stack):
    """Creates CloudWatch dashboard for MWAA performance monitoring"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        mwaa_environment_name: str,
        project_name: str,
        environment: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ========================================
        # CloudWatch Dashboard
        # ========================================
        
        dashboard = cloudwatch.Dashboard(
            self,
            "MwaaPerformanceDashboard",
            dashboard_name=f"{project_name}-mwaa-performance-{environment}",
        )

        # ========================================
        # Row 1: Worker Metrics
        # ========================================
        
        # Worker CPU Utilization
        worker_cpu_widget = cloudwatch.GraphWidget(
            title="Worker CPU Utilization",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="CPUUtilization",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Cluster": "BaseWorker"
                    },
                    statistic="Average",
                    label="BaseWorker CPU",
                    color=cloudwatch.Color.BLUE,
                ),
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="CPUUtilization",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Cluster": "AdditionalWorker"
                    },
                    statistic="Average",
                    label="AdditionalWorker CPU",
                    color=cloudwatch.Color.GREEN,
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Percent",
                min=0,
                max=100,
            ),
            width=12,
            height=6,
        )

        # Worker Memory Utilization
        worker_memory_widget = cloudwatch.GraphWidget(
            title="Worker Memory Utilization",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="MemoryUtilization",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Cluster": "BaseWorker"
                    },
                    statistic="Average",
                    label="BaseWorker Memory",
                    color=cloudwatch.Color.BLUE,
                ),
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="MemoryUtilization",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Cluster": "AdditionalWorker"
                    },
                    statistic="Average",
                    label="AdditionalWorker Memory",
                    color=cloudwatch.Color.GREEN,
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Percent",
                min=0,
                max=100,
            ),
            width=12,
            height=6,
        )

        dashboard.add_widgets(worker_cpu_widget, worker_memory_widget)

        # ========================================
        # Row 2: Queue Metrics
        # ========================================
        
        # Queue Depth (Queued and Running Tasks)
        queue_depth_widget = cloudwatch.GraphWidget(
            title="Queue Depth - Queued vs Running Tasks",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="QueuedTasks",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                    },
                    statistic="Average",
                    label="Queued Tasks",
                    color=cloudwatch.Color.ORANGE,
                ),
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="RunningTasks",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                    },
                    statistic="Average",
                    label="Running Tasks",
                    color=cloudwatch.Color.GREEN,
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Task Count",
                min=0,
            ),
            width=12,
            height=6,
        )

        # Queue Age
        queue_age_widget = cloudwatch.GraphWidget(
            title="Age of Oldest Queued Task",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="ApproximateAgeOfOldestTask",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                    },
                    statistic="Maximum",
                    label="Oldest Task Age",
                    color=cloudwatch.Color.RED,
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Seconds",
                min=0,
            ),
            width=12,
            height=6,
        )

        dashboard.add_widgets(queue_depth_widget, queue_age_widget)

        # ========================================
        # Row 3: Scheduler Metrics
        # ========================================
        
        # Scheduler CPU
        scheduler_cpu_widget = cloudwatch.GraphWidget(
            title="Scheduler CPU Utilization",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="CPUUtilization",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Cluster": "Scheduler"
                    },
                    statistic="Average",
                    label="Scheduler CPU",
                    color=cloudwatch.Color.PURPLE,
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Percent",
                min=0,
                max=100,
            ),
            width=12,
            height=6,
        )

        # Scheduler Memory
        scheduler_memory_widget = cloudwatch.GraphWidget(
            title="Scheduler Memory Utilization",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="MemoryUtilization",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Cluster": "Scheduler"
                    },
                    statistic="Average",
                    label="Scheduler Memory",
                    color=cloudwatch.Color.PURPLE,
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Percent",
                min=0,
                max=100,
            ),
            width=12,
            height=6,
        )

        dashboard.add_widgets(scheduler_cpu_widget, scheduler_memory_widget)

        # ========================================
        # Row 4: Database Metrics
        # ========================================
        
        # Database CPU
        database_cpu_widget = cloudwatch.GraphWidget(
            title="Database CPU Utilization",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="CPUUtilization",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Database": "WRITER"
                    },
                    statistic="Average",
                    label="Writer CPU",
                    color=cloudwatch.Color.RED,
                ),
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="CPUUtilization",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Database": "READER"
                    },
                    statistic="Average",
                    label="Reader CPU",
                    color=cloudwatch.Color.BLUE,
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Percent",
                min=0,
                max=100,
            ),
            width=12,
            height=6,
        )

        # Database Connections
        database_connections_widget = cloudwatch.GraphWidget(
            title="Database Connections",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="DatabaseConnections",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Database": "WRITER"
                    },
                    statistic="Average",
                    label="Writer Connections",
                    color=cloudwatch.Color.RED,
                ),
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="DatabaseConnections",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Database": "READER"
                    },
                    statistic="Average",
                    label="Reader Connections",
                    color=cloudwatch.Color.BLUE,
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Connection Count",
                min=0,
            ),
            width=12,
            height=6,
        )

        dashboard.add_widgets(database_cpu_widget, database_connections_widget)

        # ========================================
        # Row 5: WebServer Metrics
        # ========================================
        
        # WebServer CPU
        webserver_cpu_widget = cloudwatch.GraphWidget(
            title="WebServer CPU Utilization",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="CPUUtilization",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Cluster": "WebServer"
                    },
                    statistic="Average",
                    label="WebServer CPU",
                    color=cloudwatch.Color.ORANGE,
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Percent",
                min=0,
                max=100,
            ),
            width=12,
            height=6,
        )

        # WebServer Memory
        webserver_memory_widget = cloudwatch.GraphWidget(
            title="WebServer Memory Utilization",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/MWAA",
                    metric_name="MemoryUtilization",
                    dimensions_map={
                        "Environment": mwaa_environment_name,
                        "Cluster": "WebServer"
                    },
                    statistic="Average",
                    label="WebServer Memory",
                    color=cloudwatch.Color.ORANGE,
                ),
            ],
            left_y_axis=cloudwatch.YAxisProps(
                label="Percent",
                min=0,
                max=100,
            ),
            width=12,
            height=6,
        )

        dashboard.add_widgets(webserver_cpu_widget, webserver_memory_widget)

        # ========================================
        # Outputs
        # ========================================
        
        CfnOutput(
            self,
            "DashboardUrl",
            value=f"https://console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:name={dashboard.dashboard_name}",
            description="CloudWatch Dashboard URL for MWAA Performance Monitoring",
            export_name=f"{project_name}-dashboard-url-{environment}",
        )

        CfnOutput(
            self,
            "DashboardName",
            value=dashboard.dashboard_name,
            description="CloudWatch Dashboard Name",
            export_name=f"{project_name}-dashboard-name-{environment}",
        )
