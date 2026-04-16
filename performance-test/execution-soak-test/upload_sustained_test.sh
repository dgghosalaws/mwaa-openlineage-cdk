#!/bin/bash

# Upload sustained load test files to S3
# Usage: ./upload_sustained_test.sh <bucket-name> [region]
# Example: ./upload_sustained_test.sh my-mwaa-bucket us-east-2

set -e

BUCKET="${1:?Usage: ./upload_sustained_test.sh <bucket-name> [region]}"
REGION="${2:-us-east-2}"

echo "Uploading sustained load test files to s3://${BUCKET}/dags/ ..."
echo ""

# Upload task functions
echo "Uploading task functions..."
aws s3 cp performance_test_tasks_real.py s3://${BUCKET}/dags/ --region ${REGION}

# Upload report DAG
echo "Uploading report DAG..."
aws s3 cp soak_test_report_dag.py s3://${BUCKET}/dags/ --region ${REGION}

# Upload per-set DAG loaders
LOADER_COUNT=0
for loader_file in dag_factory_sustained_set_*.py; do
    [ -f "$loader_file" ] || { echo "No loader files found. Run generate_dag_factory_sustained.py --sets N first."; exit 1; }
    echo "Uploading ${loader_file}..."
    aws s3 cp "${loader_file}" s3://${BUCKET}/dags/ --region ${REGION}
    LOADER_COUNT=$((LOADER_COUNT + 1))
done

# Upload per-DAG YAML configs
echo "Uploading per-DAG YAML configs..."
aws s3 sync configs/ s3://${BUCKET}/dags/configs/ --region ${REGION}

# Upload trigger DAGs
TRIGGER_COUNT=0
for trigger_file in trigger_dag_factory_sustained_set_*.py; do
    [ -f "$trigger_file" ] || { echo "No trigger files found. Run generate_dag_factory_sustained.py --sets N first."; exit 1; }
    echo "Uploading ${trigger_file}..."
    aws s3 cp "${trigger_file}" s3://${BUCKET}/dags/ --region ${REGION}
    TRIGGER_COUNT=$((TRIGGER_COUNT + 1))
done

CONFIG_COUNT=$(find configs -name '*.yaml' | wc -l | tr -d ' ')

echo ""
echo "✅ Upload complete!"
echo "   - ${CONFIG_COUNT} per-DAG YAML config(s)"
echo "   - ${LOADER_COUNT} DAG loader(s)"
echo "   - ${TRIGGER_COUNT} trigger DAG(s)"
echo "   - 1 task functions file"
echo ""
echo "Next steps:"
echo "  1. Wait 2-5 minutes for MWAA to parse DAGs"
echo "  2. In Airflow UI, look for trigger DAGs (tag: master-trigger)"
echo "  3. Trigger all sets in parallel for maximum concurrent load"
echo "  4. Monitor for ~40 minutes per set"
