"""
Soak Test Report DAG

Trigger after the soak test to get an execution summary.
Uses MWAA InvokeRestApi to query DAG run and task instance states.

Pass config: {"num_dags": 65, "sets": 1, "env_name": "perf-test"}
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from collections import defaultdict
import logging
import boto3
import json
import os


def _invoke_api(client, env_name, method, path, query_params=None):
    """Call Airflow REST API via MWAA InvokeRestApi."""
    try:
        kwargs = {
            "Name": env_name,
            "Method": method,
            "Path": path,
        }
        if query_params:
            kwargs["QueryParameters"] = query_params
        resp = client.invoke_rest_api(**kwargs)
        return resp.get("RestApiResponse", {})
    except Exception as e:
        logging.getLogger(__name__).warning(f"API call failed: {path}: {e}")
        return None


def _fmt(seconds: float) -> str:
    if seconds <= 0:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


def _parse_duration(start_str, end_str):
    if not start_str or not end_str:
        return 0
    try:
        start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        return (end - start).total_seconds()
    except (ValueError, TypeError):
        return 0


def generate_report(**context):
    logger = logging.getLogger(__name__)
    conf = context.get("dag_run").conf or {}
    num_dags = conf.get("num_dags", 65)
    num_sets = conf.get("sets", 1)
    env_name = conf.get("env_name", os.environ.get("MWAA_ENV_NAME", "perf-test"))

    region = os.environ.get("AWS_REGION", "us-east-2")
    client = boto3.client("mwaa", region_name=region)

    report = []

    def log(msg=""):
        logger.info(msg)
        report.append(msg)

    for set_num in range(1, num_sets + 1):
        log("=" * 60)
        log(f"Execution Soak Test Report - Set {set_num:02d}")
        log("=" * 60)

        dag_states = defaultdict(int)
        failed_tasks = []
        durations = []
        task_stats = defaultdict(int)
        total_task_count = 0

        for dag_num in range(num_dags):
            dag_id = f"factory_sustained_set_{set_num:02d}_dag_{dag_num:03d}"

            data = _invoke_api(client, env_name, "GET",
                               f"/dags/{dag_id}/dagRuns",
                               {"limit": "1", "order_by": "-start_date"})
            if not data or not data.get("dag_runs"):
                dag_states["no_runs"] += 1
                continue

            run = data["dag_runs"][0]
            state = run.get("state", "unknown")
            dag_states[state] += 1

            dur = _parse_duration(run.get("start_date"), run.get("end_date"))
            if dur > 0:
                durations.append(dur)

            run_id = run.get("dag_run_id")
            if run_id and state in ("success", "failed"):
                ti_data = _invoke_api(client, env_name, "GET",
                                      f"/dags/{dag_id}/dagRuns/{run_id}/taskInstances",
                                      {"limit": "200"})
                if ti_data and "task_instances" in ti_data:
                    for ti in ti_data["task_instances"]:
                        t_state = ti.get("state", "unknown")
                        task_stats[t_state] += 1
                        total_task_count += 1
                        if t_state == "failed":
                            failed_tasks.append({
                                "dag_id": dag_id,
                                "task_id": ti.get("task_id"),
                                "try_number": ti.get("try_number"),
                            })

        log(f"\nDAG Runs ({num_dags} DAGs):")
        for state, count in sorted(dag_states.items()):
            log(f"  {state}: {count}")

        if total_task_count > 0:
            log(f"\nTask Instances ({total_task_count} total):")
            for state, count in sorted(task_stats.items()):
                log(f"  {state}: {count}")

        if failed_tasks:
            log(f"\nFailed Tasks ({len(failed_tasks)}):")
            for f in failed_tasks[:50]:
                log(f"  - {f['dag_id']}: {f['task_id']} (attempt {f['try_number']})")
            if len(failed_tasks) > 50:
                log(f"  ... and {len(failed_tasks) - 50} more")
        else:
            log("\nNo failed tasks.")

        if durations:
            log(f"\nDuration Stats:")
            log(f"  Shortest: {_fmt(min(durations))}")
            log(f"  Longest:  {_fmt(max(durations))}")
            log(f"  Average:  {_fmt(sum(durations) / len(durations))}")

        # Trigger DAG status
        log(f"\nTrigger DAG:")
        trigger_id = f"trigger_dag_factory_sustained_test_set_{set_num:02d}"
        t_data = _invoke_api(client, env_name, "GET",
                             f"/dags/{trigger_id}/dagRuns",
                             {"limit": "1", "order_by": "-start_date"})
        if t_data and t_data.get("dag_runs"):
            t_run = t_data["dag_runs"][0]
            t_state = t_run.get("state", "unknown")
            t_dur = _parse_duration(t_run.get("start_date"), t_run.get("end_date"))
            t_dur_str = f" ({_fmt(t_dur)})" if t_dur > 0 else ""
            log(f"  {trigger_id}: {t_state}{t_dur_str}")
        else:
            log(f"  {trigger_id}: no runs")

        log()

    return "\n".join(report)


default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
}

dag = DAG(
    'soak_test_report',
    default_args=default_args,
    description='Soak test report. Pass {"num_dags": 65, "sets": 1, "env_name": "perf-test"}',
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=['soak-test', 'report', 'performance'],
)

PythonOperator(
    task_id='generate_report',
    python_callable=generate_report,
    dag=dag,
)
