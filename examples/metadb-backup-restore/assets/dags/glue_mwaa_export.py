"""
MWAA MetaDB Export DAG

Creates a Glue JDBC connection to this MWAA environment's metadata database
and runs a Glue job to export tables to S3.

Works with both Airflow 2.x (SQL_ALCHEMY_CONN) and Airflow 3.x (DB_SECRETS).

This DAG runs inside MWAA and has access to the DB credentials via env vars,
which it uses to create/update the Glue connection with real JDBC credentials.

Configuration (set in MWAA airflow_configuration_options):
  metadb_export.aws_region: AWS region
  metadb_export.glue_role_name: Glue IAM role name
  metadb_export.export_s3_bucket: S3 bucket for backups
  metadb_export.max_age_days: Max age of records to export (default 30)
"""
import json
import os
from datetime import datetime
from airflow.decorators import dag, task
from airflow.configuration import conf
import boto3

AWS_REGION = conf.get('metadb_export', 'aws_region', fallback='us-east-2')
GLUE_ROLE_NAME = conf.get('metadb_export', 'glue_role_name', fallback='')
S3_BUCKET = conf.get('metadb_export', 'export_s3_bucket', fallback='')
MAX_AGE_DAYS = conf.get('metadb_export', 'max_age_days', fallback='30')

ENV_NAME = os.getenv("AIRFLOW_ENV_NAME")


@task()
def create_glue_connection():
    """Create Glue JDBC connection using MWAA's DB credentials.
    
    AF2: reads AIRFLOW__DATABASE__SQL_ALCHEMY_CONN
    AF3: reads DB_SECRETS (JSON) + POSTGRES_HOST env vars
    """
    sql_alchemy_conn = os.getenv("AIRFLOW__CORE__SQL_ALCHEMY_CONN")
    if not sql_alchemy_conn:
        sql_alchemy_conn = os.getenv("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN")

    if not sql_alchemy_conn or sql_alchemy_conn.startswith("airflow-db-not-allowed"):
        # AF3 path
        db_secrets = os.getenv("DB_SECRETS")
        db_host = os.getenv("POSTGRES_HOST")
        db_port = os.getenv("POSTGRES_PORT", "5432")
        db_name = os.getenv("POSTGRES_DB", "AirflowMetadata")
        if not all([db_secrets, db_host]):
            raise ValueError("No DB credentials available (neither SQL_ALCHEMY_CONN nor DB_SECRETS)")
        creds = json.loads(db_secrets)
        username, password = creds["username"], creds["password"]
        jdbc_url = f"jdbc:postgresql://{db_host}:{db_port}/{db_name}"
        print(f"AF3 mode: {db_host}:{db_port}/{db_name}")
    else:
        # AF2 path
        parts = sql_alchemy_conn.split('@')
        host_db = parts[1].split('?')[0]
        jdbc_url = f'jdbc:postgresql://{host_db}'
        cred_parts = parts[0].split('//')[1].split(':')
        username, password = cred_parts[0], cred_parts[1]
        print(f"AF2 mode: {host_db}")

    conn_name = f'{ENV_NAME}_metadb_conn'
    glue = boto3.client('glue', region_name=AWS_REGION)

    # Delete existing if present (credentials may have rotated)
    try:
        glue.get_connection(Name=conn_name)
        glue.delete_connection(ConnectionName=conn_name)
    except glue.exceptions.EntityNotFoundException:
        pass

    # Get MWAA network config
    mwaa = boto3.client('mwaa', region_name=AWS_REGION)
    env_resp = mwaa.get_environment(Name=ENV_NAME)
    sg_ids = env_resp['Environment']['NetworkConfiguration']['SecurityGroupIds']
    subnet_id = env_resp['Environment']['NetworkConfiguration']['SubnetIds'][0]

    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    az = ec2.describe_subnets(SubnetIds=[subnet_id])['Subnets'][0]['AvailabilityZone']

    glue.create_connection(ConnectionInput={
        'Name': conn_name,
        'Description': f'{ENV_NAME} MetaDB connection',
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


@task()
def ensure_glue_job(conn_name):
    """Create or update the Glue export job with the JDBC connection attached."""
    glue = boto3.client('glue', region_name=AWS_REGION)
    job_name = f"{ENV_NAME}_metadb_export"
    job_config = {
        'Role': GLUE_ROLE_NAME,
        'Command': {
            'Name': 'glueetl',
            'ScriptLocation': f"s3://{S3_BUCKET}/scripts/mwaa_metadb_export.py",
            'PythonVersion': '3',
        },
        'Connections': {'Connections': [conn_name]},
        'DefaultArguments': {'--additional-python-modules': 'pg8000', '--enable-metrics': 'true'},
        'GlueVersion': '4.0',
        'NumberOfWorkers': 2,
        'WorkerType': 'G.1X',
    }
    try:
        glue.get_job(JobName=job_name)
        glue.update_job(JobName=job_name, JobUpdate=job_config)
        print(f"Updated Glue job: {job_name} with connection {conn_name}")
    except glue.exceptions.EntityNotFoundException:
        glue.create_job(Name=job_name, **job_config)
        print(f"Created Glue job: {job_name}")
    return job_name


@task()
def run_export_job(job_name, conn_name):
    """Start the Glue export job and wait for completion."""
    import time
    glue = boto3.client('glue', region_name=AWS_REGION)
    run = glue.start_job_run(
        JobName=job_name,
        Arguments={
            '--S3_OUTPUT_PATH': f"s3://{S3_BUCKET}/exports/{ENV_NAME}",
            '--GLUE_CONNECTION_NAME': conn_name,
            '--MAX_AGE_IN_DAYS': MAX_AGE_DAYS,
        },
    )
    run_id = run['JobRunId']
    print(f"Started Glue job: {job_name} run={run_id}")

    while True:
        status = glue.get_job_run(JobName=job_name, RunId=run_id)
        state = status['JobRun']['JobRunState']
        if state == 'SUCCEEDED':
            print("Export completed successfully")
            return
        elif state in ('FAILED', 'STOPPED', 'ERROR', 'TIMEOUT'):
            raise Exception(f"Export failed: {state} - {status['JobRun'].get('ErrorMessage', '')}")
        time.sleep(30)


@dag(dag_id="glue_mwaa_export", schedule="0 */6 * * *", start_date=datetime(2024, 1, 1),
     tags=['dr', 'metadb', 'export'],
     catchup=False,
     description='Export MWAA metadata database to S3 via Glue')
def export_dag():
    conn_name = create_glue_connection()
    job_name = ensure_glue_job(conn_name)
    run_export_job(job_name, conn_name)


export_dag()
