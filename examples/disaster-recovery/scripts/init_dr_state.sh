#!/bin/bash

# Initialize DR State in DynamoDB
# Sets up the initial state with all required fields for Phase 2

set -e

TABLE_NAME="mwaa-openlineage-dr-state-dev"
REGION="us-east-2"
INITIAL_ACTIVE_REGION="${1:-us-east-1}"

echo "=========================================="
echo "Initializing DR State"
echo "=========================================="
echo ""
echo "Table: $TABLE_NAME"
echo "Region: $REGION"
echo "Initial Active Region: $INITIAL_ACTIVE_REGION"
echo ""

# Create initial state with Phase 2 fields
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --region "$REGION" \
    --item '{
        "state_id": {"S": "ACTIVE_REGION"},
        "active_region": {"S": "'$INITIAL_ACTIVE_REGION'"},
        "last_updated": {"S": "'$TIMESTAMP'"},
        "version": {"N": "1"},
        "failover_count": {"N": "0"},
        "last_failover_time": {"S": ""},
        "last_fallback_time": {"S": ""},
        "failover_reason": {"S": ""},
        "health_status_primary": {"S": "HEALTHY"},
        "health_status_secondary": {"S": "HEALTHY"},
        "restore_status": {"S": "NONE"},
        "restore_started_at": {"S": ""},
        "restore_completed_at": {"S": ""},
        "restore_error": {"S": ""},
        "last_backup_time": {"S": ""},
        "backup_s3_key": {"S": ""}
    }'

echo ""
echo "✓ DR state initialized successfully"
echo ""
echo "Current state:"
aws dynamodb get-item \
    --table-name "$TABLE_NAME" \
    --region "$REGION" \
    --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
    --output json | jq '.Item'

echo ""
echo "=========================================="
echo "DR State Fields"
echo "=========================================="
echo ""
echo "Core Fields:"
echo "  - state_id: Always 'ACTIVE_REGION' (partition key)"
echo "  - active_region: Current active region (us-east-1 or us-east-2)"
echo "  - last_updated: Timestamp of last state change"
echo "  - version: Optimistic locking version number"
echo ""
echo "Failover Tracking:"
echo "  - failover_count: Number of failovers performed"
echo "  - last_failover_time: Timestamp of last failover"
echo "  - last_fallback_time: Timestamp of last fallback"
echo "  - failover_reason: Reason for last failover"
echo ""
echo "Health Status:"
echo "  - health_status_primary: Health of primary region"
echo "  - health_status_secondary: Health of secondary region"
echo ""
echo "Restore Status (Phase 2):"
echo "  - restore_status: NONE|IN_PROGRESS|COMPLETED|FAILED"
echo "  - restore_started_at: When restore began"
echo "  - restore_completed_at: When restore finished"
echo "  - restore_error: Error message if restore failed"
echo ""
echo "Backup Status (Phase 2):"
echo "  - last_backup_time: Timestamp of last successful backup"
echo "  - backup_s3_key: S3 key of last backup"
echo ""
