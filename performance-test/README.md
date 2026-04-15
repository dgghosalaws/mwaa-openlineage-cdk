# Performance Tests

MWAA performance tests using [dag-factory](https://astronomer.github.io/dag-factory/latest/).

## Prerequisites

- MWAA environment running Airflow 3.0+
- `dag-factory==1.0.0` and `pyyaml` in your MWAA `requirements.txt` (see `requirements.txt`)

## Tests

| Test | Description |
|------|-------------|
| [execution-soak-test/](execution-soak-test/) | Sustained load test with wave-based ramp-up/down. Generates N sets of 65 DAGs, each with parallel tasks that loop for the wave duration. Tests worker auto-scaling and sustained task execution. |
| [scheduler-capacity-test/](scheduler-capacity-test/) | Scheduler parsing capacity test. Generates 4000 DAGs with 2 dummy tasks each. Tests whether MWAA can parse and display all DAGs without errors or timeouts. |
