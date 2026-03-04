"""
MWAA DR State Management Stack

This stack creates a DynamoDB table to track the active region
for disaster recovery purposes.
"""
from aws_cdk import (
    Stack,
    aws_dynamodb as dynamodb,
    RemovalPolicy,
    CfnOutput,
)
from constructs import Construct


class MwaaDRStateStack(Stack):
    """
    Stack for DR state management using DynamoDB
    
    This stack creates:
    - DynamoDB table for active region tracking
    - Outputs for cross-stack references
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str = "mwaa-openlineage",
        env_name: str = "dev",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.project_name = project_name
        self.env_name = env_name

        # Create DynamoDB table for DR state
        self.dr_state_table = self._create_dr_state_table()

        # Outputs
        self._create_outputs()

    def _create_dr_state_table(self) -> dynamodb.Table:
        """
        Create DynamoDB table for DR state management
        
        Table schema:
        - state_id (PK): Always "ACTIVE_REGION" (single row table)
        - active_region: Current active region (e.g., "us-east-2" or "us-east-1")
        - last_updated: Timestamp of last state change
        - failover_count: Number of failovers
        - last_failover_time: Timestamp of last failover
        - last_fallback_time: Timestamp of last fallback
        - failover_reason: Reason for last failover
        - version: Optimistic locking version number
        """
        table = dynamodb.Table(
            self,
            "DRStateTable",
            table_name=f"{self.project_name}-dr-state-{self.env_name}",
            partition_key=dynamodb.Attribute(
                name="state_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,  # Retain state data
            point_in_time_recovery=True,
        )

        return table

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs"""
        CfnOutput(
            self,
            "DRStateTableName",
            value=self.dr_state_table.table_name,
            description="DynamoDB table name for DR state",
            export_name=f"{self.project_name}-dr-state-table-{self.env_name}"
        )

        CfnOutput(
            self,
            "DRStateTableArn",
            value=self.dr_state_table.table_arn,
            description="DynamoDB table ARN for DR state",
            export_name=f"{self.project_name}-dr-state-table-arn-{self.env_name}"
        )
