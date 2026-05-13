# Testing and benchmarks (`mindtrace.core.testing`)

## Registration

- **`TestRunner`**: global registry (classmethods only). Use **`TestRunner.register_test_suite(MySuite)`** or **`TestRunner.register_suite(SuiteContribution(...))`**.

- **`TestSuite`**: minimal hook for custom runners; implement **`run(config, reporter)`**.

- **`BenchTestSuite`**: library-embedded timed workloads. Subclasses implement **`execute_bench(config, reporter)`** and receive **`BenchSuiteConfig`** / **`BenchReporter`**. Class-level **`profiles`** maps **`smoke`** vs **`stress`** (and optional keys) to **`duration_seconds`**, workload kwargs, and nested **`resources`** merged into the resolved config.

- **Tags**: tag suites with **`smoke`** or **`stress`** so **`suite_ids_for_profile("smoke")`** / **`mindtrace-bench --profile …`** can filter them.

## Running embedded benches

After **`uv sync`**, install **`mindtrace-core`** (or the meta **`mindtrace`** package). Import a package testing module so registrations run:

```python
import mindtrace.registry.testing  # registers registry benches
import mindtrace.datalake.testing  # registers datalake benches
```

CLI (console script from **`mindtrace-core`**):

```bash
mindtrace-bench registry datalake --profile smoke --list
mindtrace-bench registry --profile stress
```

Programmatic driver helpers live on **`mindtrace.core.testing`**: **`run_registered_benches`**, **`build_bench_suite_config`**, **`expand_param_matrix`** (Cartesian kwargs for matrix runs).

## Package layout

Each wheel ships **`mindtrace.<pkg>.testing`** with **`register_benchmark_suites()`** invoked once on import (guarded per package). First-party workloads mirror the legacy **`tests/stress/suites`** implementations but live beside the library code.

Use **`TestRunner.clear_registry()`** in unit tests when isolation is required.
