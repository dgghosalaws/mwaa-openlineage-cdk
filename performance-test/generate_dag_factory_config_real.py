"""
Generate DAG Factory YAML Configuration with REAL concurrent tasks

This generates configs where each DAG has REAL Airflow tasks (not simulated).
This creates actual load on the MWAA environment.

Usage:
    # Generate 2000 concurrent tasks (default)
    python generate_dag_factory_config_real.py
    
    # Generate 4000 concurrent tasks
    python generate_dag_factory_config_real.py --tasks 4000
    
    # Generate custom task count
    python generate_dag_factory_config_real.py --tasks 3000
"""

import yaml
import argparse
from typing import Dict, List


def get_config(target_tasks: int = 2000) -> Dict:
    """Get configuration parameters
    
    Args:
        target_tasks: Target number of concurrent tasks (default: 2000)
    
    Returns:
        Configuration dictionary with num_dags, tasks_per_dag, etc.
    """
    # Based on observed scheduler throughput: ~65 DAGs can start concurrently
    num_dags = 65
    tasks_per_dag = target_tasks // num_dags
    actual_tasks = num_dags * tasks_per_dag
    
    return {
        'num_dags': num_dags,
        'tasks_per_dag': tasks_per_dag,
        'task_duration': 120,  # 2 minutes
        'actual_tasks': actual_tasks,
        'description': f'Concurrent Load Test - REAL {actual_tasks} concurrent tasks'
    }


def generate_dag_config(
    dag_num: int,
    num_tasks: int,
    task_duration: int,
) -> Dict:
    """
    Generate configuration for a single DAG with REAL tasks.
    
    Creates 1 wave_delay task + num_tasks real load tasks.
    """
    dag_id = f"factory_concurrent_real_dag_{dag_num:03d}"
    
    # Build tasks list
    tasks_list = [
        {
            'task_id': 'wave_delay',
            'operator': 'airflow.operators.python.PythonOperator',
            'python_callable_name': 'wave_delay_task',
            'python_callable_file': '/usr/local/airflow/dags/performance_test_tasks_real.py',
            'op_kwargs': {
                'wave_num': 1,
                'delay_seconds': 0,
            }
        }
    ]
    
    # Add real load tasks
    for task_id in range(num_tasks):
        task = {
            'task_id': f'load_task_{task_id:02d}',
            'operator': 'airflow.operators.python.PythonOperator',
            'python_callable_name': 'real_load_task',
            'python_callable_file': '/usr/local/airflow/dags/performance_test_tasks_real.py',
            'op_kwargs': {
                'task_id': task_id,
                'duration': task_duration,
                'wave_num': 1,
                'dag_num': dag_num,
            },
            'dependencies': ['wave_delay']
        }
        tasks_list.append(task)
    
    return {
        dag_id: {
            'default_args': {
                'owner': 'airflow',
                'depends_on_past': False,
                'email_on_failure': False,
                'email_on_retry': False,
                'retries': 0,
                'execution_timeout': {'minutes': 10},
            },
            'description': f'DAG Factory Concurrent Test REAL - DAG {dag_num:03d} - {num_tasks} REAL tasks',
            'schedule': None,
            'catchup': False,
            'max_active_runs': 1,
            'max_active_tasks': num_tasks + 5,  # Allow all tasks to run concurrently
            'dagrun_timeout': {'minutes': 15},
            'is_paused_upon_creation': False,
            'tags': ['dag-factory-test', 'concurrent-test-real', 'performance', 'real-load', f'dag-{dag_num}'],
            'tasks': tasks_list
        }
    }


def generate_full_config(target_tasks: int = 2000) -> tuple:
    """Generate complete YAML configuration for all DAGs with REAL tasks"""
    config_dict = {}
    params = get_config(target_tasks)
    
    num_dags = params['num_dags']
    tasks_per_dag = params['tasks_per_dag']
    task_duration = params['task_duration']
    actual_tasks = params['actual_tasks']
    
    # Generate DAGs
    for dag_num in range(num_dags):
        dag_config = generate_dag_config(
            dag_num=dag_num,
            num_tasks=tasks_per_dag,
            task_duration=task_duration,
        )
        config_dict.update(dag_config)
    
    return config_dict, params


def main():
    """Generate and save YAML configuration"""
    parser = argparse.ArgumentParser(
        description='Generate DAG Factory performance test configuration with REAL tasks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 2000 concurrent tasks (default)
  python generate_dag_factory_config_real.py
  
  # Generate 4000 concurrent tasks
  python generate_dag_factory_config_real.py --tasks 4000
  
  # Generate custom task count
  python generate_dag_factory_config_real.py --tasks 3000
        """
    )
    parser.add_argument(
        '--tasks',
        type=int,
        default=2000,
        help='Target number of concurrent tasks (default: 2000)'
    )
    args = parser.parse_args()
    
    target_tasks = args.tasks
    print(f"Generating DAG Factory configuration for {target_tasks} concurrent tasks...")
    
    # Generate configuration
    config, params = generate_full_config(target_tasks)
    
    # Save to YAML file
    output_file = 'dag_factory_config_concurrent_real.yaml'
    
    num_dags = params['num_dags']
    tasks_per_dag = params['tasks_per_dag']
    task_duration = params['task_duration']
    actual_tasks = params['actual_tasks']
    
    with open(output_file, 'w') as f:
        # Write header comment
        f.write("# DAG Factory Performance Test Configuration - REAL TASKS\n")
        f.write("# Auto-generated configuration file\n")
        f.write("#\n")
        f.write(f"# {params['description']}\n")
        f.write("#\n")
        f.write(f"# Configuration:\n")
        f.write(f"# - {num_dags} DAGs × {tasks_per_dag} REAL tasks = {actual_tasks} ACTUAL task instances\n")
        f.write(f"# - Task duration: {task_duration} seconds ({task_duration/60:.1f} minutes)\n")
        f.write(f"# - All DAGs start simultaneously (no wave delays)\n")
        f.write(f"# - Total test duration: ~{task_duration/60:.1f} minutes\n")
        f.write("#\n")
        f.write("# ⚠️  WARNING: This creates REAL concurrent tasks!\n")
        f.write(f"# - Each DAG has {tasks_per_dag + 1} actual Airflow tasks (1 delay + {tasks_per_dag} load)\n")
        f.write(f"# - Total Airflow task instances: {actual_tasks + num_dags}\n")
        f.write(f"# - Worker slots needed: {actual_tasks}\n")
        f.write(f"# - max_active_tasks per DAG: {tasks_per_dag + 5}\n")
        f.write("#\n\n")
        
        # Write YAML configuration
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    print(f"✅ Configuration saved to {output_file}")
    print(f"   - {num_dags} DAGs generated")
    print(f"   - {tasks_per_dag} REAL tasks per DAG")
    print(f"   - {actual_tasks} total REAL task instances")
    print(f"   - {task_duration/60:.1f} minute task duration")
    print(f"   - ~{task_duration/60:.1f} minute total test duration")
    print(f"\n⚠️  WARNING: This will create {actual_tasks} actual concurrent tasks!")
    print(f"   Make sure your MWAA environment can handle this load.")


if __name__ == '__main__':
    main()
