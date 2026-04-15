#!/bin/bash

# Upload throughput test files to S3
# Usage: ./upload_throughput_test.sh <bucket-name> [region]
# Example: ./upload_throughput_test.sh my-mwaa-bucket us-east-2

set -e

BUCKET="${1:?Usage: ./upload_throughput_test.sh <bucket-name> [region]}"
REGION="${2:-us-east-2}"

echo "Uploading throughput test files to s3://${BUCKET}/dags/ ..."
echo ""

# Upload task functions
echo "Uploading task functions..."
aws s3 cp throughput_tasks.py s3://${BUCKET}/dags/ --region ${REGION}

# Upload loaders
LOADER_COUNT=0
for f in throughput_loader_*.py; do
    [ -f "$f" ] || { echo "No loader files found. Run generate_dag_factory_throughput.py first."; exit 1; }
    echo "Uploading ${f}..."
    aws s3 cp "$f" s3://${BUCKET}/dags/ --region ${REGION}
    LOADER_COUNT=$((LOADER_COUNT + 1))
done

# Upload YAML configs
echo "Uploading YAML configs..."
aws s3 sync throughput_configs/ s3://${BUCKET}/dags/throughput_configs/ --region ${REGION}

# Upload trigger DAG
echo "Uploading trigger DAG..."
aws s3 cp trigger_throughput_test.py s3://${BUCKET}/dags/ --region ${REGION}

CONFIG_COUNT=$(find throughput_configs -name '*.yaml' | wc -l | tr -d ' ')

echo ""
echo "✅ Upload complete!"
echo "   - ${CONFIG_COUNT} per-DAG YAML configs"
echo "   - ${LOADER_COUNT} loader(s)"
echo "   - 1 trigger DAG"
echo "   - 1 task functions file"
echo ""
echo "Next steps:"
echo "  1. Wait 2-5 minutes for MWAA to parse DAGs"
echo "  2. In Airflow UI, find trigger_throughput_test (tag: master-trigger)"
echo "  3. Trigger the test"
