"""
AWS Glue script - Export MWAA metadata database tables to S3.

Connects to the Airflow metadata database via Glue JDBC connection and exports
tables to S3 as pipe-delimited CSV files (compatible with PostgreSQL COPY).

Parameters:
- S3_OUTPUT_PATH: S3 path for exported files
- GLUE_CONNECTION_NAME: Glue connection name
- MAX_AGE_IN_DAYS: Max age of records to export
"""
import sys
import json
import gzip
import csv
from datetime import datetime, timedelta
from io import StringIO
import boto3
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql.functions import col, to_date, to_timestamp

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)

args = getResolvedOptions(sys.argv, [
    'JOB_NAME', 'S3_OUTPUT_PATH', 'GLUE_CONNECTION_NAME', 'MAX_AGE_IN_DAYS'
])
job.init(args['JOB_NAME'], args)

s3_output_path = args['S3_OUTPUT_PATH'].rstrip('/')
glue_connection_name = args['GLUE_CONNECTION_NAME']
max_age_days = int(args['MAX_AGE_IN_DAYS'])

# Append date path
export_date = datetime.now()
s3_output_path = f"{s3_output_path}/{export_date.strftime('%Y/%m/%d')}"
cutoff_date_str = (datetime.now() - timedelta(days=max_age_days)).strftime('%Y-%m-%d')

s3_client = boto3.client('s3')

# Tables to export - prioritized by importance for DR
EXPORT_TABLES = [
    {"table": "dag_run", "date_field": "execution_date"},
    {"table": "task_instance", "date_field": "start_date"},
    {"table": "xcom", "date_field": "execution_date"},
    {"table": "task_instance_history", "date_field": "start_date"},
    {"table": "log", "date_field": "dttm"},
    {"table": "import_error", "date_field": "timestamp"},
    {"table": "dag", "date_field": "last_parsed_time"},
    {"table": "dag_code", "date_field": "last_updated"},
    {"table": "dag_version", "date_field": "created_at"},
    {"table": "variable", "date_field": None},
    {"table": "connection", "date_field": None},
    {"table": "slot_pool", "date_field": None},
    {"table": "dag_run_note", "date_field": "created_at"},
    {"table": "task_instance_note", "date_field": "created_at"},
    {"table": "asset_event", "date_field": "timestamp"},
    {"table": "asset", "date_field": "created_at"},
    {"table": "job", "date_field": "start_date"},
    {"table": "trigger", "date_field": "created_date"},
    {"table": "backfill", "date_field": "created_at"},
    {"table": "backfill_dag_run", "date_field": None},
]

print(f"Export path: {s3_output_path}")
print(f"Cutoff: {cutoff_date_str} ({max_age_days} days)")
print(f"Connection: {glue_connection_name}")


def parse_s3_path(s3_path):
    path = s3_path[5:] if s3_path.startswith('s3://') else s3_path
    parts = path.split('/', 1)
    return parts[0], parts[1] if len(parts) > 1 else ''


def get_jdbc_url_and_props():
    """Get JDBC URL and properties from the Glue connection."""
    glue_client = boto3.client('glue')
    resp = glue_client.get_connection(Name=glue_connection_name)
    props = resp['Connection']['ConnectionProperties']
    url = props['JDBC_CONNECTION_URL']
    jdbc_props = {"user": props['USERNAME'], "password": props['PASSWORD'], "driver": "org.postgresql.Driver"}
    return url, jdbc_props


def list_available_tables():
    """List tables in the database for debugging."""
    try:
        url, props = get_jdbc_url_and_props()
        df = spark.read.jdbc(
            url=url, table="information_schema.tables", properties=props
        ).filter("table_type = 'BASE TABLE' AND table_schema NOT IN ('information_schema', 'pg_catalog')")
        print("Available tables:")
        for row in df.select("table_schema", "table_name").collect():
            print(f"  {row.table_schema}.{row.table_name}")
    except Exception as e:
        print(f"Could not list tables: {e}")


def export_table(table_name, date_field, s3_path):
    """Export a single table to S3 as pipe-delimited compressed CSV."""
    try:
        url, props = get_jdbc_url_and_props()
        df = None
        for variant in [f"public.{table_name}", table_name]:
            try:
                df = spark.read.jdbc(url=url, table=variant, properties=props)
                break
            except Exception:
                continue

        if df is None:
            print(f"  {table_name}: NOT FOUND, skipping")
            return 0

        # Apply date filter
        if date_field:
            try:
                df = df.filter(col(date_field) >= cutoff_date_str)
            except Exception:
                try:
                    df = df.filter(to_date(col(date_field)) >= cutoff_date_str)
                except Exception:
                    pass
            try:
                df = df.orderBy(col(date_field).desc())
            except Exception:
                pass

        row_count = df.count()
        if row_count == 0:
            print(f"  {table_name}: 0 rows, skipping")
            return 0

        # Export as pipe-delimited CSV (matches COPY format)
        pandas_df = df.toPandas()
        csv_buffer = StringIO()
        pandas_df.to_csv(csv_buffer, index=False, sep='|', quoting=csv.QUOTE_MINIMAL)
        compressed = gzip.compress(csv_buffer.getvalue().encode('utf-8'))

        bucket, base_key = parse_s3_path(s3_path)
        s3_key = f"{base_key}/{table_name}.csv.gz"
        s3_client.put_object(Bucket=bucket, Key=s3_key, Body=compressed)

        # Write column metadata for restore
        meta = {"table": table_name, "columns": list(pandas_df.columns), "row_count": row_count}
        s3_client.put_object(
            Bucket=bucket,
            Key=f"{base_key}/{table_name}_meta.json",
            Body=json.dumps(meta),
        )

        print(f"  {table_name}: {row_count} rows -> s3://{bucket}/{s3_key}")
        return row_count

    except Exception as e:
        print(f"  {table_name}: ERROR - {e}")
        return 0


# Main export
try:
    results = {}
    list_available_tables()

    for tc in EXPORT_TABLES:
        results[tc['table']] = export_table(tc['table'], tc['date_field'], s3_output_path)

    # Write summary
    bucket, base_key = parse_s3_path(s3_output_path)
    summary = {
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
        "cutoff_date": cutoff_date_str,
        "total_rows": sum(results.values()),
        "tables": results,
    }
    s3_client.put_object(
        Bucket=bucket,
        Key=f"{base_key}/export_summary.json",
        Body=json.dumps(summary, indent=2),
    )

    print("=" * 60)
    print(f"EXPORT COMPLETE: {sum(results.values())} rows from {len([v for v in results.values() if v > 0])} tables")
    print(f"Location: {s3_output_path}")
    print("=" * 60)

except Exception as e:
    print(f"EXPORT FAILED: {e}")
    raise
finally:
    job.commit()
