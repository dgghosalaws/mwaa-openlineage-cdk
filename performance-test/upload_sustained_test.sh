#!/bin/bash

# Upload sustained load test files to S3
# Usage: ./upload_sustained_test.sh [bucket-name] [region]
# Example: ./upload_sustained_test.sh my-mwaa-bucket us-east-2

BUCKET="${1:-your-mwaa-bucket-name}"
REGION="${2:-us-east-2}"

echo "Uploading sustained load test files..."
echo ""

# Upload generated config
echo "Uploading config..."
aws s3 cp dag_factory_config_sustained.yaml s3://${BUCKET}/dags/ --region ${REGION}

# Upload DAG loader
echo "Uploading DAG loader..."
aws s3 cp dag_factory_sustained.py s3://${BUCKET}/dags/ --region ${REGION}

# Upload trigger DAG
echo "Uploading trigger DAG..."
aws s3 cp trigger_dag_factory_sustained.py s3://${BUCKET}/dags/ --region ${REGION}

# Task functions already uploaded (shared with concurrent test)
echo ""
echo "✅ Files uploaded!"
echo ""
echo "Next steps:"
echo "1. Wait 2-5 minutes for MWAA to parse DAGs"
echo "2. Check Airflow UI for:"
echo "   - 65 DAGs: factory_sustained_dag_000 through factory_sustained_dag_064"
echo "   - 1 Trigger: trigger_dag_factory_sustained_test"
echo "   - Tags: sustained-load, performance"
echo "3. Trigger the test: trigger_dag_factory_sustained_test"
echo "4. Monitor for 40 minutes:"
echo "   - T+0-5 min: Ramp up from 500 → 2000 tasks"
echo "   - T+5-25 min: Sustain 2000 tasks (20 minutes)"
echo "   - T+25-40 min: Ramp down 2000 → 0 tasks"
echo ""
echo "⚠️  This is a 40-minute test - plan accordingly!"
