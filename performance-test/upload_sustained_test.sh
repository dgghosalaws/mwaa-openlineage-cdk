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

# Upload DAG loader
echo "Uploading DAG loader..."
aws s3 cp dag_factory_sustained.py s3://${BUCKET}/dags/ --region ${REGION}

# Upload all set config files
CONFIG_COUNT=0
for config_file in dag_factory_config_sustained_set_*.yaml; do
    [ -f "$config_file" ] || { echo "No config files found. Run generate_dag_factory_sustained.py --sets N first."; exit 1; }
    echo "Uploading ${config_file}..."
    aws s3 cp "${config_file}" s3://${BUCKET}/dags/ --region ${REGION}
    CONFIG_COUNT=$((CONFIG_COUNT + 1))
done

# Upload all trigger DAGs
TRIGGER_COUNT=0
for trigger_file in trigger_dag_factory_sustained_set_*.py; do
    [ -f "$trigger_file" ] || { echo "No trigger files found. Run generate_dag_factory_sustained.py --sets N first."; exit 1; }
    echo "Uploading ${trigger_file}..."
    aws s3 cp "${trigger_file}" s3://${BUCKET}/dags/ --region ${REGION}
    TRIGGER_COUNT=$((TRIGGER_COUNT + 1))
done

echo ""
echo "✅ Upload complete!"
echo "   - ${CONFIG_COUNT} config file(s)"
echo "   - ${TRIGGER_COUNT} trigger DAG(s)"
echo "   - 1 DAG loader (dag_factory_sustained.py)"
echo "   - 1 task functions file (performance_test_tasks_real.py)"
echo ""
echo "Next steps:"
echo "  1. Wait 2-5 minutes for MWAA to parse DAGs"
echo "  2. In Airflow UI, look for:"
echo "     - ${CONFIG_COUNT} set(s) × 65 DAGs each (tags: sustained-load, set-NN)"
echo "     - ${TRIGGER_COUNT} master trigger DAG(s): trigger_dag_factory_sustained_test_set_NN"
echo "  3. Trigger all sets in parallel for maximum concurrent load"
echo "  4. Monitor for ~40 minutes per set"
