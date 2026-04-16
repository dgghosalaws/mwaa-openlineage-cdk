"""
Soak Test Report DAG

Trigger this DAG after the soak test completes to generate an execution report.
Queries the Airflow metadata DB for DAG run and task instance states.

Pass the number of sets via DAG config:
  {"sets": 2}

Default: 2 sets.
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sdk import Session
from airflow.models.dagrun import DagRun
from airflow.models.taskinstance import TaskInstance
from datetime import datetime
from collections import defaultdict
import logging


def generate_report(**context):
    logger = logging.getLogger(__name__)
    conf = context.get("dag_run").conf or {}
    num_sets = conf.get("sets", 2)

    report_lines = []

    def log(msg=""):
        logger.info(msg)
        report_lines.append(msg)

    with Session() as session:
        for set_num in range(1, num_sets + 1):
            log("=" * 60)
            log(f"Execution Soak Test Report - Set {set_num:02d}")
            log("=" * 60)

            dag_states = defaultdict(int)
            failed_tasks = []
            durations = []
            task_stats = defaultdict(int)
            total_task_count = 0

            for dag_num in range(65):
                dag_id = f"factory_sustained_set_{set_num:02d}_dag_{dag_num:03d}"

                # Get most recent DAG run
                run = (
                    session.query(DagRun)
                    .filter(DagRun.dag_id == dag_id)
                    .order_by(DagRun.start_date.desc())
                    .first()
                )

                if not run:
                    dag_states["no_runs"] += 1
                    continue

                state = str(run.state) if run.state else "unknown"
                dag_states[state] += 1

                if run.start_date and run.end_date:
                    duration = (run.end_date - run.start_date).total_seconds()
                    durations.append(duration)

                # Get task instances
                task_instances = (
                    session.query(TaskInstance)
                    .filter(
                        TaskInstance.dag_id == dag_id,
                        TaskInstance.run_id == run.run_id,
                    )
                    .all()
                )

                for ti in task_instances:
                    t_state = str(ti.state) if ti.state else "unknown"
                    task_stats[t_state] += 1
                    total_task_count += 1

                    if t_state == "failed":
                        failed_tasks.append({
                            "dag_id": dag_id,
                            "task_id": ti.task_id,
                            "try_number": ti.try_number,
                        })

            # DAG run summary
            log(f"\nDAG Runs (65 DAGs):")
            for state, count in sorted(dag_states.items()):
                log(f"  {state}: {count}")

            # Task summary
            if total_task_count > 0:
                log(f"\nTask Instances ({total_task_count} total):")
                for state, count in sorted(task_stats.items()):
                    log(f"  {state}: {count}")

            # Failures
            if failed_tasks:
                log(f"\nFailed Tasks:")
                for f in failed_tasks:
                    log(f"  - {f['dag_id']}: {f['task_id']} (attempt {f['try_number']})")
            else:
                log(f"\nNo failed tasks.")

            # Duration stats
            if durations:
                avg = sum(durations) / len(durations)
                log(f"\nDuration Stats:")
                log(f"  Shortest: {_fmt(min(durations))}")
                log(f"  Longest:  {_fmt(max(durations))}")
                log(f"  Average:  {_fmt(avg)}")

            if not durations and dag_states.get("no_runs", 0) == 65:
                log("\n  No DAG runs found. Test may not have been triggered yet.")

            log()

        # Trigger DAG status
        log("=" * 60)
        log("Trigger DAG Status")
        log("=" * 60)
        for set_num in range(1, num_sets + 1):
            trigger_id = f"trigger_dag_factory_sustained_test_set_{set_num:02d}"
            run = (
                session.query(DagRun)
                .filter(DagRun.dag_id == trigger_id)
                .order_by(DagRun.start_date.desc())
                .first()
            )
            if run:
                state = str(run.state) if run.state else "unknown"
                dur = ""
                if run.start_date and run.end_date:
                    dur = f" ({_fmt((run.end_date - run.start_date).total_seconds())})"
                log(f"  Set {set_num:02d}: {state}{dur}")
            else:
                log(f"  Set {set_num:02d}: no runs")

    return "\n".join(report_lines)


def _fmt(seconds: float) -> str:
    if seconds <= 0:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


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
    description='Generate execution report for soak test. Pass {"sets": N} in config.',
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=['soak-test', 'report', 'performance'],
)

report_task = PythonOperator(
    task_id='generate_report',
    python_callable=generate_report,
    dag=dag,
)
