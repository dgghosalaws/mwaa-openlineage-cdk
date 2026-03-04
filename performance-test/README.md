# MWAA Performance Testing

Two approaches for performance testing your MWAA environment.

## Approaches

### 1. DAG Factory Approach (Recommended)

Uses DAG Factory to dynamically generate test DAGs with real concurrent tasks.

**Advantages:**
- Configurable task count and duration
- Single set of files for multiple test scenarios
- Real concurrent tasks (not simulated)
- Easy to customize

**Test Scenarios:**

#### A. Concurrent Load Test (Quick)
Tests immediate concurrent load capacity.

**Files:**
- `generate_dag_factory_config_real.py` - Configuration generator
- `dag_factory_concurrent_real.py` - DAG loader
- `trigger_dag_factory_concurrent_real.py` - Trigger DAG
- `performance_test_tasks_real.py` - Task functions

**Quick Start:**
```bash
# Generate 2000 concurrent tasks (default)
python3 generate_dag_factory_config_real.py

# Generate 4000 concurrent tasks
python3 generate_dag_factory_config_real.py --tasks 4000

# Upload to S3 and trigger in Airflow UI
```

**Duration:** ~2 minutes

#### B. Sustained Load Test (Long Duration)
Tests sustained load with gradual ramp-up and ramp-down.

**Files:**
- `generate_dag_factory_sustained.py` - Configuration generator
- `dag_factory_sustained.py` - DAG loader
- `trigger_dag_factory_sustained.py` - Trigger DAG
- `performance_test_tasks_real.py` - Task functions (shared)

**Quick Start:**
```bash
# Generate 2000 peak tasks (default)
python3 generate_dag_factory_sustained.py

# Generate 4000 peak tasks
python3 generate_dag_factory_sustained.py --peak-tasks 4000

# Custom peak and duration
python3 generate_dag_factory_sustained.py --peak-tasks 3000 --peak-duration 30

# Upload to S3 and trigger in Airflow UI
```

**Test Pattern (40 minutes):**
- 0-5 min: Ramp up from 500 → peak tasks
- 5-25 min: Sustain peak load (20 minutes)
- 25-40 min: Ramp down peak → 0 tasks

**Duration:** ~40 minutes

**Documentation:** [DAG_FACTORY_USER_GUIDE.md](DAG_FACTORY_USER_GUIDE.md)

### 2. Python DAG Approach (Legacy)

Traditional Python DAGs with predefined test scenarios.

**Test Scenarios:**
- Gradual Load Test (7,000 tasks, 4.5 minutes)
- 5K Load Test (5,000 tasks, 4.5 minutes)
- Sustained Load Test (7,000 tasks, 55 minutes)

**Files:**
- `test_distributed_gradual_load.py` - Gradual load test
- `test_distributed_5k_load.py` - 5K load test
- `test_sustained_load.py` - Sustained load test
- `trigger_master_dag.py` - Trigger for gradual test
- `trigger_5k_test.py` - Trigger for 5K test
- `trigger_sustained_load.py` - Trigger for sustained test

**Documentation:** See main [PERFORMANCE_TESTING.md](../PERFORMANCE_TESTING.md) in parent directory

## Which Approach to Use?

**Use DAG Factory Concurrent Test if:**
- You want quick capacity validation (~2 minutes)
- You need to test different task counts easily
- You want immediate concurrent load
- You're testing maximum burst capacity

**Use DAG Factory Sustained Test if:**
- You need long-duration stability testing (~40 minutes)
- You want to test sustained high load (20+ minutes)
- You need gradual ramp-up/ramp-down patterns
- You're testing for memory leaks or resource degradation
- You want to validate auto-scaling behavior over time

**Use Python DAG Approach if:**
- You need the specific predefined test scenarios
- You're already familiar with these tests
- You need the exact wave-based patterns from legacy tests

## Requirements

Both approaches require:
- MWAA Airflow 3.0.6+
- Appropriate worker capacity
- Pool configuration
- CloudWatch monitoring (optional)

## Support

- DAG Factory Approach: See [DAG_FACTORY_USER_GUIDE.md](DAG_FACTORY_USER_GUIDE.md)
- Python DAG Approach: See [PERFORMANCE_TESTING.md](../PERFORMANCE_TESTING.md)
