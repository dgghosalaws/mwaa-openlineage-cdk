#!/bin/bash

# Failover with DAG Pause/Unpause Control
# This script performs failover and manages DAG pause state via Airflow API

set -e

TARGET_REGION="$1"
REASON="${2:-Manual failover}"

if [ -z "$TARGET_REGION" ]; then
    echo "Usage: $0 <target-region> [reason]"
    echo ""
    echo "Examples:"
    echo "  $0 us-east-2 'Primary region failure'"
    echo "  $0 us-east-1 'Failback after testing'"
    exit 1
fi

TABLE_NAME="mwaa-openlineage-dr-state-dev"
PRIMARY_REGION="us-east-2"
SECONDARY_REGION="us-east-1"

# Determine environment names
if [ "$TARGET_REGION" = "$PRIMARY_REGION" ]; then
    TARGET_ENV="mwaa-openlineage-dev"
    SOURCE_ENV="mwaa-openlineage-minimal-dev"
    SOURCE_REGION="$SECONDARY_REGION"
else
    TARGET_ENV="mwaa-openlineage-minimal-dev"
    SOURCE_ENV="mwaa-openlineage-dev"
    SOURCE_REGION="$PRIMARY_REGION"
fi

echo "=========================================="
echo "DR Failover with DAG Control"
echo "=========================================="
echo ""
echo "Target Region: $TARGET_REGION ($TARGET_ENV)"
echo "Source Region: $SOURCE_REGION ($SOURCE_ENV)"
echo "Reason: $REASON"
echo ""
echo "This will:"
echo "  1. Update DynamoDB active region"
echo "  2. Pause all DAGs in $SOURCE_REGION"
echo "  3. Unpause all DAGs in $TARGET_REGION"
echo "  4. Sensor provides safety net"
echo ""
read -p "Continue with failover? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Function to get Airflow CLI token and webserver URL
get_airflow_access() {
    local env_name=$1
    local region=$2
    
    TOKEN=$(aws mwaa create-cli-token \
        --name "$env_name" \
        --region "$region" \
        --query CliToken \
        --output text)
    
    WEBSERVER=$(aws mwaa get-environment \
        --name "$env_name" \
        --region "$region" \
        --query 'Environment.WebserverUrl' \
        --output text)
    
    echo "$TOKEN|$WEBSERVER"
}

# Function to pause/unpause all DAGs
control_dags() {
    local env_name=$1
    local region=$2
    local is_paused=$3  # true or false
    local action=$4     # "Pausing" or "Unpausing"
    
    echo "$action all DAGs in $env_name ($region)..."
    
    # Get access
    ACCESS=$(get_airflow_access "$env_name" "$region")
    TOKEN=$(echo "$ACCESS" | cut -d'|' -f1)
    WEBSERVER=$(echo "$ACCESS" | cut -d'|' -f2)
    
    # Get list of all DAGs (Airflow 3.x: use /aws_mwaa/cli/ with trailing slash, decode base64)
    DAGS_LIST=$(curl -s --request POST "https://$WEBSERVER/aws_mwaa/cli/" \
        --header "Authorization: Bearer $TOKEN" \
        --header "Content-Type: text/plain" \
        --data "dags list" | jq -r '.stdout' | base64 -d)
    
    # Parse DAG IDs (skip header, exclude DR DAGs)
    DAG_IDS=$(echo "$DAGS_LIST" | tail -n +3 | awk '{print $1}' | grep -v "^dr_" | grep -v "^==")
    
    if [ -z "$DAG_IDS" ]; then
        echo "  No DAGs found (or error getting DAG list)"
        return
    fi
    
    # Pause/unpause each DAG
    COUNT=0
    for dag_id in $DAG_IDS; do
        # Skip empty lines
        [ -z "$dag_id" ] && continue
        
        # Use Airflow CLI to pause/unpause
        if [ "$is_paused" = "true" ]; then
            CMD="dags pause $dag_id"
        else
            CMD="dags unpause $dag_id"
        fi
        
        RESULT=$(curl -s --request POST "https://$WEBSERVER/aws_mwaa/cli/" \
            --header "Authorization: Bearer $TOKEN" \
            --header "Content-Type: text/plain" \
            --data "$CMD" | jq -r '.stdout' | base64 -d)
        
        if echo "$RESULT" | grep -q "True\|False"; then
            COUNT=$((COUNT + 1))
        fi
    done
    
    echo "  ✓ $action $COUNT DAGs"
}

# Step 1: Update DynamoDB
echo ""
echo "Step 1: Updating DynamoDB state..."
echo ""

aws dynamodb update-item \
    --table-name "$TABLE_NAME" \
    --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
    --update-expression "SET active_region = :region, last_updated = :timestamp, version = version + :inc, failover_count = failover_count + :inc, last_failover_time = :timestamp, failover_reason = :reason" \
    --expression-attribute-values '{
        ":region": {"S": "'$TARGET_REGION'"},
        ":timestamp": {"S": "'$TIMESTAMP'"},
        ":inc": {"N": "1"},
        ":reason": {"S": "'$REASON'"}
    }' \
    --region "$PRIMARY_REGION" \
    > /dev/null

echo "✓ DynamoDB updated"
echo "  - Active region: $TARGET_REGION"
echo ""

# Step 2: Pause DAGs in source region
echo "Step 2: Pausing DAGs in source region..."
echo ""

control_dags "$SOURCE_ENV" "$SOURCE_REGION" "true" "Pausing"

echo ""

# Step 3: Unpause DAGs in target region
echo "Step 3: Unpausing DAGs in target region..."
echo ""

control_dags "$TARGET_ENV" "$TARGET_REGION" "false" "Unpausing"

echo ""

# Step 4: Verify state
echo "Step 4: Verifying failover..."
echo ""

CURRENT_STATE=$(aws dynamodb get-item \
    --table-name "$TABLE_NAME" \
    --key '{"state_id": {"S": "ACTIVE_REGION"}}' \
    --region "$PRIMARY_REGION" \
    --output json | jq '.Item')

echo "Current DR state:"
echo "$CURRENT_STATE" | jq '{
    active_region: .active_region.S,
    failover_count: .failover_count.N,
    last_failover_time: .last_failover_time.S,
    failover_reason: .failover_reason.S
}'

echo ""
echo "=========================================="
echo "Failover Complete"
echo "=========================================="
echo ""
echo "✓ Active region: $TARGET_REGION"
echo "✓ DAGs paused in: $SOURCE_REGION"
echo "✓ DAGs unpaused in: $TARGET_REGION"
echo "✓ Sensor provides safety net in both regions"
echo ""
echo "Total failover time: ~15-20 seconds"
echo ""
echo "Next steps:"
echo "  1. Verify DAGs are running in $TARGET_REGION"
echo "  2. Check Airflow UI - no skipped runs in $SOURCE_REGION"
echo "  3. Monitor for any issues"
echo ""
echo "To failback to $SOURCE_REGION:"
echo "  ./failover_with_dag_control.sh $SOURCE_REGION 'Failback after testing'"
echo ""
