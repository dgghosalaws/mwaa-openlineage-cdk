# DR-Aware DAG Pattern

This directory contains utilities to make any Airflow DAG DR-aware with minimal code changes.

## Quick Start

### Option 1: Use the Helper Function (Recommended)

Add just 4 lines to your existing DAG:

```python
# 1. Import the helper
from dr_utils import check_active_region
from airflow.providers.standard.operators.python import BranchPythonOperator
from airflow.operators.empty import EmptyOperator

# 2. Add DR check operator
check_region = BranchPythonOperator(
    task_id='check_region',
    python_callable=check_active_region,
)

# 3. Add markers
run_tasks = EmptyOperator(task_id='run_tasks')
skip_all = EmptyOperator(task_id='skip_all')

# 4. Wire it up
check_region >> [run_tasks, skip_all]
run_tasks >> your_existing_tasks
```

That's it! Your DAG now:
- Runs in both regions
- Only executes work in the ACTIVE region
- Automatically skips in STANDBY region

### Option 2: Inline Check (For Simple Cases)

For simple DAGs, you can check inline:

```python
from dr_utils import is_active_region

def my_task(**context):
    if not is_active_region():
        print("Skipping - standby region")
        return
    
    # Your actual work here
    print("Doing work in active region")
```

## Files

- `dr_utils.py` - Reusable DR helper functions
- `example_dr_aware_dag.py` - Complete example showing the pattern
- `dr_test_dag.py` - Simple test DAG for verification

## How It Works

1. **check_active_region()** - Queries DynamoDB to check if current region is active
2. **BranchPythonOperator** - Routes to either 'run_tasks' or 'skip_all'
3. **Your tasks** - Execute normally if active, skipped if standby

## Configuration

The helper reads from Airflow configuration (set in MWAA):
- `dr.state_table` - DynamoDB table name
- `dr.table_region` - Region where table is located

No hardcoded values in your DAG code!

## Benefits

✓ Minimal code changes (4 lines)
✓ No changes to existing tasks
✓ Works with any DAG pattern
✓ Reusable across all DAGs
✓ Configuration-driven
✓ Safe defaults (skips on error)

## Example: Converting Existing DAG

### Before (Regular DAG)
```python
with DAG('my_dag', ...) as dag:
    task1 = PythonOperator(...)
    task2 = PythonOperator(...)
    task3 = PythonOperator(...)
    
    task1 >> task2 >> task3
```

### After (DR-Aware DAG)
```python
from dr_utils import check_active_region
from airflow.providers.standard.operators.python import BranchPythonOperator
from airflow.operators.empty import EmptyOperator

with DAG('my_dag', ...) as dag:
    # Add DR check
    check_region = BranchPythonOperator(
        task_id='check_region',
        python_callable=check_active_region,
    )
    run_tasks = EmptyOperator(task_id='run_tasks')
    skip_all = EmptyOperator(task_id='skip_all')
    
    # Your existing tasks (unchanged!)
    task1 = PythonOperator(...)
    task2 = PythonOperator(...)
    task3 = PythonOperator(...)
    
    # Wire it up
    check_region >> [run_tasks, skip_all]
    run_tasks >> task1 >> task2 >> task3
```

## Testing

1. Deploy to both regions
2. Check DynamoDB active_region value
3. Verify DAG runs in active region
4. Verify DAG skips in standby region
5. Test failover by changing active_region

## Best Practices

1. **Always use the helper** - Don't duplicate the check logic
2. **Add early in DAG** - Check region before any expensive operations
3. **Use EmptyOperator markers** - Makes the flow clear
4. **Test failover** - Verify behavior in both regions
5. **Monitor logs** - Check for DR check messages

## Troubleshooting

### DAG runs in both regions
- Check DynamoDB active_region value
- Verify helper function is being called
- Check CloudWatch logs for DR check output

### DAG doesn't run in active region
- Verify region names match exactly
- Check DynamoDB table permissions
- Review error messages in logs

### Configuration not found
- Verify MWAA airflow_configuration_options are set
- Check dr.state_table and dr.table_region values
- Helper falls back to defaults if not found
