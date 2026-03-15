"""
AWS Glue script - Restore MWAA metadata database from S3 backup.

Connects to the TARGET MWAA metadb via Glue JDBC connection and restores
tables using PostgreSQL COPY FROM STDIN command.

Same Glue connection mechanism as export, but writes to the DB instead of reading.

Parameters:
- S3_BACKUP_PATH: S3 path with backup files (e.g. s3://bucket/exports/env/2024/01/15)
- GLUE_CONNECTION_NAME: Glue connection to target MWAA metadb
- RESTORE_TABLES: JSON array of table names to restore
- RESTORE_MODE: 'append' or 'clean' (truncate before restore)
"""
import sys
import json
import gzip
import csv
from datetime import datetime
from io import StringIO
import boto3
import pg8000
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext

sc = SparkContext()
glueContext = GlueContext(sc)
job = Job(glueContext)

args = getResolvedOptions(sys.argv, [
    'JOB_NAME', 'S3_BACKUP_PATH', 'GLUE_CONNECTION_NAME',
    'RESTORE_TABLES', 'RESTORE_MODE'
])
job.init(args['JOB_NAME'], args)

s3_backup_path = args['S3_BACKUP_PATH'].rstrip('/')
glue_connection_name = args['GLUE_CONNECTION_NAME']
restore_tables = json.loads(args['RESTORE_TABLES'])
restore_mode = args.get('RESTORE_MODE', 'append')

s3_client = boto3.client('s3')
glue_client = boto3.client('glue')

BATCH_SIZE = 1000

# FK-safe restore order
RESTORE_ORDER = [
    "variable", "connection", "slot_pool",
    "dag", "dag_code", "dag_version",
    "dag_run", "dag_run_note",
    "task_instance", "task_instance_history", "task_instance_note",
    "xcom", "log", "import_error",
    "job", "trigger",
    "asset", "asset_event",
    "backfill", "backfill_dag_run",
]

print(f"Backup path: {s3_backup_path}")
print(f"Connection: {glue_connection_name}")
print(f"Mode: {restore_mode}")
print(f"Tables: {len(restore_tables)}")


def parse_s3_path(s3_path):
    path = s3_path[5:] if s3_path.startswith('s3://') else s3_path
    parts = path.split('/', 1)
    return parts[0], parts[1] if len(parts) > 1 else ''


def get_db_connection():
    """Get PostgreSQL connection from Glue connection properties."""
    response = glue_client.get_connection(Name=glue_connection_name)
    props = response['Connection']['ConnectionProperties']

    jdbc_url = props['JDBC_CONNECTION_URL']
    username = props['USERNAME']
    password = props['PASSWORD']

    # Parse: jdbc:postgresql://host:port/database
    url_part = jdbc_url.replace('jdbc:postgresql://', '')
    host_port, database = url_part.rsplit('/', 1)
    host, port = (host_port.split(':') + ['5432'])[:2]

    print(f"Connecting to {host}:{port}/{database}")
    return pg8000.connect(
        host=host, port=int(port), database=database,
        user=username, password=password, ssl_context=True
    )


def find_backup_file(bucket, base_key, table_name):
    """Find backup CSV for a table."""
    prefix = f"{base_key}/{table_name}.csv.gz"
    try:
        s3_client.head_object(Bucket=bucket, Key=prefix)
        return prefix
    except Exception:
        # Try with timestamp suffix pattern
        response = s3_client.list_objects_v2(
            Bucket=bucket, Prefix=f"{base_key}/{table_name}_"
        )
        if 'Contents' not in response:
            return None
        files = [o for o in response['Contents'] if o['Key'].endswith('.csv.gz')]
        if not files:
            return None
        files.sort(key=lambda x: x['LastModified'], reverse=True)
        return files[0]['Key']


def get_column_meta(bucket, base_key, table_name):
    """Read column metadata from export."""
    for suffix in ['_meta.json', '_columns.json']:
        try:
            resp = s3_client.get_object(Bucket=bucket, Key=f"{base_key}/{table_name}{suffix}")
            return json.loads(resp['Body'].read().decode('utf-8'))
        except Exception:
            continue
    return None


def read_backup(bucket, s3_key):
    """Read and decompress backup CSV."""
    resp = s3_client.get_object(Bucket=bucket, Key=s3_key)
    return gzip.decompress(resp['Body'].read()).decode('utf-8')


def restore_table_copy(conn, table_name, csv_data, columns=None):
    """Restore using PostgreSQL COPY FROM STDIN (pipe-delimited).
    
    Same approach as mwaa-disaster-recovery reference:
    COPY table (cols) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, DELIMITER '|')
    """
    cursor = conn.cursor()
    try:
        if restore_mode == 'clean':
            print(f"  Truncating {table_name}...")
            cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE")
            conn.commit()

        if columns:
            col_list = ', '.join(columns)
            copy_sql = f"COPY {table_name} ({col_list}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, DELIMITER '|')"
        else:
            copy_sql = f"COPY {table_name} FROM STDIN WITH (FORMAT CSV, HEADER TRUE, DELIMITER '|')"

        print(f"  SQL: {copy_sql}")

        lines = csv_data.split('\n')
        header = lines[0]
        data_lines = [l for l in lines[1:] if l.strip()]

        total = 0
        for i in range(0, len(data_lines), BATCH_SIZE):
            batch = data_lines[i:i + BATCH_SIZE]
            batch_csv = header + '\n' + '\n'.join(batch) + '\n'
            stream = StringIO(batch_csv)
            cursor.execute(copy_sql, stream=stream)
            conn.commit()
            total += len(batch)

        print(f"  COPY inserted {total} rows")
        return total

    except Exception as e:
        conn.rollback()
        print(f"  COPY failed: {e}, trying INSERT fallback...")
        return restore_table_insert(conn, table_name, csv_data, columns)
    finally:
        cursor.close()


def restore_table_insert(conn, table_name, csv_data, columns=None):
    """Fallback: row-by-row INSERT if COPY fails."""
    cursor = conn.cursor()
    try:
        reader = csv.reader(StringIO(csv_data), delimiter='|')
        header = next(reader)
        cols = columns or header
        placeholders = ', '.join(['%s'] * len(cols))
        sql = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})"

        total = 0
        for row in reader:
            if not row or len(row) != len(cols):
                continue
            row = [None if v == '' else v for v in row]
            try:
                cursor.execute(sql, row)
                total += 1
                if total % BATCH_SIZE == 0:
                    conn.commit()
            except Exception as e:
                conn.rollback()
                continue

        conn.commit()
        print(f"  INSERT inserted {total} rows")
        return total
    except Exception as e:
        conn.rollback()
        print(f"  INSERT failed: {e}")
        return 0
    finally:
        cursor.close()


# Main restore
try:
    bucket, base_key = parse_s3_path(s3_backup_path)
    results = {}

    # Order tables for FK safety
    ordered = [t for t in RESTORE_ORDER if t in restore_tables]
    ordered += [t for t in restore_tables if t not in ordered]

    print(f"Restore order: {ordered}")

    conn = get_db_connection()

    # Disable triggers for performance
    cur = conn.cursor()
    try:
        cur.execute("SET session_replication_role = 'replica'")
        conn.commit()
        print("Triggers disabled for session")
    except Exception:
        conn.rollback()
    finally:
        cur.close()

    for table_name in ordered:
        print(f"\nRestoring: {table_name}")

        backup_key = find_backup_file(bucket, base_key, table_name)
        if not backup_key:
            print(f"  No backup found, skipping")
            results[table_name] = 0
            continue

        meta = get_column_meta(bucket, base_key, table_name)
        columns = meta['columns'] if meta else None

        csv_data = read_backup(bucket, backup_key)
        data_lines = len([l for l in csv_data.split('\n') if l.strip()]) - 1
        print(f"  Backup: {data_lines} rows from s3://{bucket}/{backup_key}")

        results[table_name] = restore_table_copy(conn, table_name, csv_data, columns)

    # Re-enable triggers
    cur = conn.cursor()
    try:
        cur.execute("SET session_replication_role = 'origin'")
        conn.commit()
        print("\nTriggers re-enabled")
    except Exception:
        pass
    finally:
        cur.close()

    conn.close()

    print("=" * 60)
    print(f"RESTORE COMPLETE: {sum(results.values())} rows into {len([v for v in results.values() if v > 0])} tables")
    print("=" * 60)

    # Write summary to the LOCAL region's backup bucket (not the source bucket,
    # which may be cross-region and read-only for this role)
    summary = {
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
        "backup_path": s3_backup_path,
        "mode": restore_mode,
        "total_rows": sum(results.values()),
        "tables": results,
    }
    try:
        # Derive local bucket: replace source region with current region in bucket name
        import boto3.session
        local_region = boto3.session.Session().region_name or 'us-east-2'
        local_bucket = f"mwaa-metadb-backups-{bucket.split('-')[-2]}-{local_region}"
        # Fall back to source bucket if local bucket name can't be derived
        if not local_bucket.startswith('mwaa-metadb-backups-'):
            local_bucket = bucket
        summary_key = f"restore-logs/restore_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        s3_client.put_object(
            Bucket=local_bucket,
            Key=summary_key,
            Body=json.dumps(summary, indent=2),
        )
        print(f"Summary written to s3://{local_bucket}/{summary_key}")
    except Exception as e:
        print(f"Could not write restore summary: {e}")
        print(f"Summary: {json.dumps(summary, indent=2)}")

except Exception as e:
    print(f"RESTORE FAILED: {e}")
    raise
finally:
    job.commit()
