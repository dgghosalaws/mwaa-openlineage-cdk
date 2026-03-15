"""
MWAA MetaDB Restore DAG

Creates a Glue JDBC connection to THIS MWAA environment's metadata database
and starts a Glue job to restore tables from S3 backup. Returns immediately
after starting the job — monitoring is handled by Step Functions.

Trigger with config:
{
    "backup_path": "s3://bucket/exports/source-env/2024/01/15",
    "restore_mode": "append",
    "tables": ["variable", "connection", "dag_run", "task_instance"]
}

- backup_path: S3 path containing the backup files (required)
- restore_mode: 'append' (default) or 'clean' (truncate before restore)
- tables: list of tables to restore (optional, defaults to all)
"""
import json
import os
from datetime import datetime
from airflow.decorators import dag, task
from airflow.configuration import conf
import boto3

AWS_REGION = conf.get('metadb_restore', 'aws_region',
                      fallback=conf.get('metadb_export', 'aws_region', fallback='us-east-2'))
GLUE_ROLE_NAME = conf.get('metadb_restore', 'glue_role_name',
                          fallback=conf.get('metadb_export', 'glue_role_name', fallback=''))
S3_BUCKET = conf.get('metadb_restore', 'export_s3_bucket',
                     fallback=conf.get('metadb_export', 'export_s3_bucket', fallback=''))

ENV_NAME = os.getenv("AIRFLOW_ENV_NAME")

ALL_TABLES = [
    "variable", "connection", "slot_pool",
    "dag", "dag_code", "dag_version",
    "dag_run", "dag_run_note",
    "task_instance", "task_instance_history", "task_instance_note",
    "xcom", "log", "import_error",
    "job", "trigger", "asset", "asset_event",
    "backfill", "backfill_dag_run",
]


@task()
def create_glue_connection():
    """Create Glue JDBC connection using MWAA's DB credentials."""
    sql_alchemy_conn = os.getenv("AIRFLOW__CORE__SQL_ALCHEMY_CONN")
    if not sql_alchemy_conn:
        sql_alchemy_conn = os.getenv("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN")

    if not sql_alchemy_conn or sql_alchemy_conn.startswith("airflow-db-not-allowed"):
        db_secrets = os.getenv("DB_SECRETS")
        db_host = os.getenv("POSTGRES_HOST")
        db_port = os.getenv("POSTGRES_PORT", "5432")
        db_name = os.getenv("POSTGRES_DB", "AirflowMetadata")
        if not all([db_secrets, db_host]):
            raise ValueError("No DB credentials available")
        creds = json.loads(db_secrets)
        username, password = creds["username"], creds["password"]
        jdbc_url = f"jdbc:postgresql://{db_host}:{db_port}/{db_name}"
    else:
        parts = sql_alchemy_conn.split('@')
        host_db = parts[1].split('?')[0]
        jdbc_url = f'jdbc:postgresql://{host_db}'
        cred_parts = parts[0].split('//')[1].split(':')
        username, password = cred_parts[0], cred_parts[1]

    conn_name = f'{ENV_NAME}_metadb_restore_conn'
    glue = boto3.client('glue', region_name=AWS_REGION)

    try:
        glue.get_connection(Name=conn_name)
        glue.delete_connection(ConnectionName=conn_name)
    except glue.exceptions.EntityNotFoundException:
        pass

    mwaa = boto3.client('mwaa', region_name=AWS_REGION)
    env_resp = mwaa.get_environment(Name=ENV_NAME)
    sg_ids = env_resp['Environment']['NetworkConfiguration']['SecurityGroupIds']
    subnet_id = env_resp['Environment']['NetworkConfiguration']['SubnetIds'][0]

    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    az = ec2.describe_subnets(SubnetIds=[subnet_id])['Subnets'][0]['AvailabilityZone']

    glue.create_connection(ConnectionInput={
        'Name': conn_name,
        'Description': f'{ENV_NAME} MetaDB restore connection',
        'ConnectionType': 'JDBC',
        'ConnectionProperties': {
            'JDBC_ENFORCE_SSL': 'false',
            'JDBC_CONNECTION_URL': jdbc_url,
            'PASSWORD': password,
            'USERNAME': username,
            'KAFKA_SSL_ENABLED': 'false',
        },
        'PhysicalConnectionRequirements': {
            'SubnetId': subnet_id,
            'SecurityGroupIdList': sg_ids,
            'AvailabilityZone': az,
        },
    })
    print(f"Created Glue connection: {conn_name}")
    return conn_name


@dag(dag_id="glue_mwaa_restore", schedule=None, start_date=datetime(2024, 1, 1),
     tags=['dr', 'metadb', 'restore'],
     description='Start MWAA metadata restore via Glue (fire-and-forget)')
def restore_dag():
    conn_name = create_glue_connection()

    @task()
    def start_restore(glue_conn, **context):
        """Create/update the Glue restore job and start it. Returns immediately."""
        dag_run = context.get('dag_run')
        config = dag_run.conf if dag_run and dag_run.conf else {}

        backup_path = config.get('backup_path', '')
        if not backup_path:
            raise ValueError("backup_path required in DAG config")

        restore_mode = config.get('restore_mode', 'append')
        tables = config.get('tables', ALL_TABLES)

        glue = boto3.client('glue', region_name=AWS_REGION)
        job_name = f"{ENV_NAME}_metadb_restore"
        script_loc = f"s3://{S3_BUCKET}/scripts/mwaa_metadb_restore.py"

        job_config = {
            'Role': GLUE_ROLE_NAME,
            'Command': {'Name': 'glueetl', 'ScriptLocation': script_loc, 'PythonVersion': '3'},
            'DefaultArguments': {'--additional-python-modules': 'pg8000'},
            'GlueVersion': '4.0',
            'NumberOfWorkers': 2,
            'WorkerType': 'G.1X',
            'Connections': {'Connections': [glue_conn]},
        }
        try:
            glue.get_job(JobName=job_name)
            glue.update_job(JobName=job_name, JobUpdate=job_config)
        except glue.exceptions.EntityNotFoundException:
            glue.create_job(Name=job_name, **job_config)

        run = glue.start_job_run(
            JobName=job_name,
            Arguments={
                '--S3_BACKUP_PATH': backup_path,
                '--GLUE_CONNECTION_NAME': glue_conn,
                '--RESTORE_TABLES': json.dumps(tables),
                '--RESTORE_MODE': restore_mode,
            },
        )
        run_id = run['JobRunId']
        print(f"Started restore job: {job_name} run={run_id}")
        print(f"Glue job submitted — monitoring handled by Step Functions")
        return {"job_name": job_name, "run_id": run_id}

    start_restore(conn_name)


restore_dag()
