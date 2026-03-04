"""
Generate DAG Factory YAML Configuration for Sustained Load Testing

This generates a sustained load test with gradual ramp-up, sustained peak, and ramp-down.

Test Pattern (40 minutes total):
- 0-5 min: Ramp up from 500 → peak tasks
- 5-25 min: Sustain peak load (20 minutes)
- 25-40 min: Ramp down peak → 0 tasks

Usage:
    # Generate 2000 peak tasks (default)
    python generate_dag_factory_sustained.py
    
    # Generate 4000 peak tasks
    python generate_dag_factory_sustained.py --peak-tasks 4000
    
    # Custom peak and duration
    python generate_dag_factory_sustained.py --peak-tasks 3000 --peak-duration 30
"""

import yaml
import argparse
from typing import Dict, List


def calculate_wave_config(peak_tasks: int, peak_duration: int = 20) -> Dict:
    """
    Calculate wave configuration for sustained load test.
    
    Args:
        peak_tasks: Target peak concurrent tasks
        peak_duration: How long to sustain peak (minutes)
    
    Returns:
        Configuration with wave timings and task counts
    """
    # Use 65 DAGs (scheduler throughput limit)
    num_dags = 65
    
    # Calculate tasks per DAG at peak
    tasks_per_dag_peak = peak_tasks // num_dags
    
    # Wave configuration
    # Wave 1: 500 tasks (baseline)
    # Wave 2: 1000 tasks (50% to peak)
    # Wave 3: 1500 tasks (75% to peak)
    # Wave 4-N: Peak tasks (sustained)
    # Wave N+1: Ramp down
    
    tasks_wave1 = 500
    tasks_wave2 = peak_tasks // 2
    tasks_wave3 = int(peak_tasks * 0.75)
    
    # Calculate how many DAGs needed for each wave
    dags_wave1 = tasks_wave1 // tasks_per_dag_peak or 1
    dags_wave2 = tasks_wave2 // tasks_per_dag_peak or 1
    dags_wave3 = tasks_wave3 // tasks_per_dag_peak or 1
    
    # Remaining DAGs for peak
    dags_peak = num_dags - dags_wave3
    
    # Calculate number of peak waves (one every 5 minutes)
    num_peak_waves = peak_duration // 5
    
    waves = []
    
    # Calculate task durations to achieve proper ramp-down
    # Goal: All tasks overlap during peak (T+5 to T+25), then finish gradually (T+25 to T+40)
    # 
    # Wave 1: starts T+0, finishes T+25 (25 min) - first to finish
    # Wave 2: starts T+2, finishes T+30 (28 min) - ramp-down continues
    # Wave 3: starts T+4, finishes T+35 (31 min) - ramp-down continues
    # Wave 4+: start T+5-20, finish T+40 (35 min) - last to finish
    
    # Ramp up waves with staggered finish times for ramp-down
    waves.append({
        'wave': 1,
        'dag_start': 0,
        'dag_count': dags_wave1,
        'delay_minutes': 0,
        'task_duration': 25,  # Finish at T+25 (start of ramp-down)
        'description': f'Baseline - {tasks_wave1} tasks'
    })
    
    waves.append({
        'wave': 2,
        'dag_start': dags_wave1,
        'dag_count': dags_wave2 - dags_wave1,
        'delay_minutes': 2,
        'task_duration': 28,  # Finish at T+30 (mid ramp-down)
        'description': f'Ramp to 50% - {tasks_wave2} tasks'
    })
    
    waves.append({
        'wave': 3,
        'dag_start': dags_wave2,
        'dag_count': dags_wave3 - dags_wave2,
        'delay_minutes': 4,
        'task_duration': 31,  # Finish at T+35 (late ramp-down)
        'description': f'Ramp to 75% - {tasks_wave3} tasks'
    })
    
    # Peak waves - longest tasks to finish last (creating final ramp-down)
    current_dag = dags_wave3
    for i in range(num_peak_waves):
        wave_num = 4 + i
        dags_this_wave = min(dags_peak // num_peak_waves, num_dags - current_dag)
        
        waves.append({
            'wave': wave_num,
            'dag_start': current_dag,
            'dag_count': dags_this_wave,
            'delay_minutes': 5 + (i * 5),
            'task_duration': 35,  # Finish at T+40 (end of test)
            'description': f'Peak sustained - {peak_tasks} tasks'
        })
        current_dag += dags_this_wave
    
    return {
        'num_dags': num_dags,
        'tasks_per_dag': tasks_per_dag_peak,
        'peak_tasks': peak_tasks,
        'peak_duration': peak_duration,
        'waves': waves,
        'total_duration': 40
    }


def generate_dag_config(
    dag_num: int,
    wave_config: Dict,
    tasks_per_dag: int,
) -> Dict:
    """
    Generate configuration for a single DAG.
    
    Args:
        dag_num: DAG number (0-based)
        wave_config: Wave configuration for this DAG
        tasks_per_dag: Number of tasks per DAG
    """
    dag_id = f"factory_sustained_dag_{dag_num:03d}"
    wave_num = wave_config['wave']
    delay_seconds = wave_config['delay_minutes'] * 60
    task_duration = wave_config['task_duration'] * 60  # Convert to seconds
    
    # Build tasks list
    tasks_list = [
        {
            'task_id': 'wave_delay',
            'operator': 'airflow.operators.python.PythonOperator',
            'python_callable_name': 'wave_delay_task',
            'python_callable_file': '/usr/local/airflow/dags/performance_test_tasks_real.py',
            'op_kwargs': {
                'wave_num': wave_num,
                'delay_seconds': delay_seconds,
            }
        }
    ]
    
    # Add real load tasks
    for task_id in range(tasks_per_dag):
        task = {
            'task_id': f'load_task_{task_id:02d}',
            'operator': 'airflow.operators.python.PythonOperator',
            'python_callable_name': 'real_load_task',
            'python_callable_file': '/usr/local/airflow/dags/performance_test_tasks_real.py',
            'op_kwargs': {
                'task_id': task_id,
                'duration': task_duration,
                'wave_num': wave_num,
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
                'execution_timeout': {'minutes': 45},
            },
            'description': f'Sustained Load Test - DAG {dag_num:03d} - Wave {wave_num} - {wave_config["description"]}',
            'schedule': None,
            'catchup': False,
            'max_active_runs': 1,
            'max_active_tasks': tasks_per_dag + 5,
            'dagrun_timeout': {'minutes': 50},
            'is_paused_upon_creation': False,
            'tags': ['dag-factory-test', 'sustained-load', 'performance', f'wave-{wave_num}', f'dag-{dag_num}'],
            'tasks': tasks_list
        }
    }


def generate_full_config(peak_tasks: int = 2000, peak_duration: int = 20) -> tuple:
    """Generate complete YAML configuration for sustained load test"""
    config_dict = {}
    
    # Calculate wave configuration
    wave_params = calculate_wave_config(peak_tasks, peak_duration)
    
    num_dags = wave_params['num_dags']
    tasks_per_dag = wave_params['tasks_per_dag']
    waves = wave_params['waves']
    
    # Generate DAGs according to wave configuration
    for wave in waves:
        wave_num = wave['wave']
        dag_start = wave['dag_start']
        dag_count = wave['dag_count']
        
        for i in range(dag_count):
            dag_num = dag_start + i
            if dag_num >= num_dags:
                break
                
            dag_config = generate_dag_config(
                dag_num=dag_num,
                wave_config=wave,
                tasks_per_dag=tasks_per_dag,
            )
            config_dict.update(dag_config)
    
    return config_dict, wave_params


def main():
    """Generate and save YAML configuration"""
    parser = argparse.ArgumentParser(
        description='Generate DAG Factory sustained load test configuration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 2000 peak tasks (default)
  python generate_dag_factory_sustained.py
  
  # Generate 4000 peak tasks
  python generate_dag_factory_sustained.py --peak-tasks 4000
  
  # Custom peak and duration
  python generate_dag_factory_sustained.py --peak-tasks 3000 --peak-duration 30
        """
    )
    parser.add_argument(
        '--peak-tasks',
        type=int,
        default=2000,
        help='Peak number of concurrent tasks (default: 2000)'
    )
    parser.add_argument(
        '--peak-duration',
        type=int,
        default=20,
        help='Duration to sustain peak load in minutes (default: 20)'
    )
    args = parser.parse_args()
    
    peak_tasks = args.peak_tasks
    peak_duration = args.peak_duration
    
    print(f"Generating sustained load test configuration...")
    print(f"  Peak tasks: {peak_tasks}")
    print(f"  Peak duration: {peak_duration} minutes")
    
    # Generate configuration
    config, params = generate_full_config(peak_tasks, peak_duration)
    
    # Save to YAML file
    output_file = 'dag_factory_config_sustained.yaml'
    
    num_dags = params['num_dags']
    tasks_per_dag = params['tasks_per_dag']
    total_duration = params['total_duration']
    
    with open(output_file, 'w') as f:
        # Write header comment
        f.write("# DAG Factory Sustained Load Test Configuration\n")
        f.write("# Auto-generated configuration file\n")
        f.write("#\n")
        f.write(f"# Sustained Load Test - {peak_tasks} peak tasks\n")
        f.write("#\n")
        f.write(f"# Test Pattern ({total_duration} minutes total):\n")
        f.write(f"# - 0-5 min: Ramp up from 500 → {peak_tasks} tasks\n")
        f.write(f"# - 5-{5+peak_duration} min: Sustain peak load ({peak_duration} minutes)\n")
        f.write(f"# - {5+peak_duration}-{total_duration} min: Ramp down {peak_tasks} → 0 tasks\n")
        f.write("#\n")
        f.write(f"# Configuration:\n")
        f.write(f"# - {num_dags} DAGs × {tasks_per_dag} tasks = {num_dags * tasks_per_dag} peak capacity\n")
        f.write(f"# - Task duration: 20 minutes\n")
        f.write(f"# - Peak sustained: {peak_duration} minutes\n")
        f.write(f"# - Total test duration: ~{total_duration} minutes\n")
        f.write("#\n")
        f.write("# Wave Pattern:\n")
        for wave in params['waves']:
            f.write(f"# - Wave {wave['wave']}: T+{wave['delay_minutes']}min - {wave['description']}\n")
        f.write("#\n\n")
        
        # Write YAML configuration
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    print(f"✅ Configuration saved to {output_file}")
    print(f"   - {num_dags} DAGs generated")
    print(f"   - {tasks_per_dag} tasks per DAG")
    print(f"   - {peak_tasks} peak concurrent tasks")
    print(f"   - {peak_duration} minute peak duration")
    print(f"   - ~{total_duration} minute total test duration")
    print(f"\n⚠️  WARNING: This is a long-running test ({total_duration} minutes)!")
    print(f"   Make sure your MWAA environment can handle sustained load.")


if __name__ == '__main__':
    main()
