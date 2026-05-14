# Testing and benchmarks (`mindtrace.core.testing`)

This document covers **library-embedded benchmark workloads** (timed “stress” style checks) shipped with Mindtrace and **how downstream applications** register and run them—including **adding their own suites** on top.

The integration surface is **`TestRunner`**, **`BenchTestSuite`**, and **`run_registered_benches`**. Discovery is **import-driven** (no separate manifest file in this model).

---

## Registration primitives

- **`TestRunner`**: instantiable suite registry. Use **`runner = TestRunner()`** for isolated application/test registries, or call **`TestRunner.register_test_suite(MySuite)`** / **`TestRunner.register_suite(SuiteContribution(...))`** for the process-global default runner.

- **`TestSuite`**: minimal hook for custom runners; implement **`run(config, reporter)`**.

- **`BenchTestSuite`**: library-embedded timed workloads. Subclasses implement **`execute_bench(config, reporter)`** and receive **`BenchSuiteConfig`** / **`BenchReporter`**. Class-level **`profiles`** maps profile names (typically **`smoke`** and **`stress`**) to **`duration_seconds`**, workload kwargs, and nested **`resources`** merged into the resolved config.

- **`TaskSchema`**: optional class-level input/output contract for a suite. Set **`task_schema = TaskSchema(name=suite_id, input_schema=..., output_schema=...)`** with Pydantic models so REST/UI callers can inspect accepted benchmark parameters and serialized outputs.

- **`resource_schema`**: optional class-level Pydantic model for environment/resource config such as Mongo URIs, MinIO credentials, or GCS settings. Resource schemas are separate from task inputs because resource values often need redaction or secret handling.

- **Tags**: tag suites with **`smoke`** or **`stress`** so **`suite_ids_for_profile("smoke")`** and **`mindtrace-bench --profile …`** can filter them. Additional domain tags (**`api`**, **`ingest`**, etc.) may be useful for future multi-tag selection if the **`TestRunner` API grows.

---

## Mental model for suites and profiles

| Concept | Meaning |
|--------|---------|
| **Suite** | Named workload: stable **`suite_id`**, **`tags`**, **`requires`**, safety text, parameter definitions, **`profiles`**. |
| **Profile** | Named preset (**`smoke`**, **`stress`**, …): **`duration_seconds`**, defaults for parameters, optional nested **`resources`**. |
| **Registry** | Each **`TestRunner`** instance holds **`SuiteContribution`** entries. Class-level calls use the process-global default runner; imports of **`mindtrace.<pkg>.testing`** register suites into that default runner as a side effect. |
| **Execution** | A CLI or script calls **`run_registered_benches(...)`** with **`suite_id`** strings and a **profile tag** (**`smoke`** or **`stress`** for built-in tooling). |

---

## Discovering suite schemas for REST / UI callers

For simple scripts, import package **`testing`** modules to register suites into the process-global default runner. Callers can then inspect one suite or all suites without importing suite classes directly:

```python
from mindtrace.core.testing.runner import TestRunner

import mindtrace.registry.testing  # noqa: F401
import mindtrace.datalake.testing  # noqa: F401

suite_schema = TestRunner.get_suite_schema("registry.stress.write_ceiling")
all_stress_schemas = TestRunner.list_suite_schemas(tags={"stress"})
```

For applications that need isolation from global process state, create a runner and register package suites into that instance explicitly:

```python
from mindtrace.core.testing.runner import TestRunner
import mindtrace.registry.testing
import mindtrace.datalake.testing

runner = TestRunner()
mindtrace.registry.testing.register_benchmark_suites(runner=runner)
mindtrace.datalake.testing.register_benchmark_suites(runner=runner)

suite_schema = runner.get_suite_schema("registry.stress.write_ceiling")
all_stress_schemas = runner.list_suite_schemas(tags={"stress"})
```

The returned **`SuiteSchema`** is a Pydantic model intended to be easy to return from REST endpoints. It includes:

- **`suite_id`**, **`title`**, **`description`**, **`tags`**, **`requires`**, and **`safety`**
- **`profiles`** and legacy/default **`parameters`** metadata
- **`task_schema`**, a JSON-schema payload generated from the suite's **`TaskSchema`** input/output Pydantic models
- **`resource_json_schema`**, generated from the suite's resource Pydantic model

For example, a UI can render form controls from **`suite_schema.task_schema["input_json_schema"]`**, display expected result fields from **`output_json_schema`**, and handle resource configuration separately from **`resource_json_schema`**.

---

## Running Mindtrace shipped benches

After installing **`mindtrace-core`** (and any Mindtrace libraries whose benches you need), import package **`testing`** modules so registrations execute:

```python
import mindtrace.registry.testing  # registers registry benches
import mindtrace.datalake.testing  # registers datalake benches
```

CLI (console script **`mindtrace-bench`** from **`mindtrace-core`**):

```bash
mindtrace-bench registry datalake --profile smoke --list
mindtrace-bench registry datalake --profile smoke
mindtrace-bench registry datalake --profile stress --list
mindtrace-bench datalake --profile stress --run-id "$(date -u +%Y-%m-%dT%H-%M-%SZ)"
```

- **`--profile smoke|stress`** selects suites whose **tags include that literal string**.
- **`--list`** prints matching **`suite_id`** values.

**Programmatic helpers** (`mindtrace.core.testing.driver`): **`suite_ids_for_profile`**, **`run_registered_benches`**. Config building: **`build_bench_suite_config`**, **`expand_param_matrix`**.

Example (run explicit suites after registration):

```python
from mindtrace.core.testing.driver import run_registered_benches, suite_ids_for_profile
from mindtrace.core.testing.runner import TestRunner

runner = TestRunner()
import mindtrace.registry.testing
import mindtrace.datalake.testing

mindtrace.registry.testing.register_benchmark_suites(runner=runner)
mindtrace.datalake.testing.register_benchmark_suites(runner=runner)

# Optional: discovery
print("stress-tagged suites:", suite_ids_for_profile("stress", runner=runner))

bench_results, exec_rows = run_registered_benches(
    ["registry.stress.write_ceiling"],
    profile="stress",
    run_id="dev-run-1",
    resources={},  # optional: e.g. mongo_uri, minio_endpoint from your environment
    runner=runner,
)
for row in bench_results:
    print(row.suite_id, row.status, row.operations, row.failures)
```

Use **`runner = TestRunner()`** in unit tests or applications when you need isolation between cases. **`TestRunner.clear_registry()`** still clears the global default runner for backwards-compatible scripts.

---

## Package layout (Mindtrace wheels)

Each first-party wheel that ships benchmarks exposes **`mindtrace.<pkg>.testing`** with **`register_benchmark_suites()`** invoked on import (idempotent / guarded per package). Workload implementations live beside library code under that package’s **`testing/`** subtree.

---

## Integrating benchmarks in a downstream application

Downstream services that depend on Mindtrace can **reuse** the same **`BenchTestSuite`** model and **`run_registered_benches`** runner.

### Dependencies

- **`mindtrace-core`** (required for **`mindtrace.core.testing`** and **`mindtrace-bench`**).
- Any Mindtrace libraries whose benches you import (e.g. **`mindtrace-registry`**, **`mindtrace-datalake`**), via the meta **`mindtrace`** package or explicit pins aligned with production.

### Registering Mindtrace suites

1. Create **`runner = TestRunner()`** when a clean isolated registry is required (recommended for applications, tests, and repeated runs in one process).
2. **`import mindtrace.<pkg>.testing`** for each subsystem you need.
3. Call **`mindtrace.<pkg>.testing.register_benchmark_suites(runner=runner)`** for isolated registration, or rely on import side effects / class-level **`TestRunner`** calls for the global default runner.
4. Choose **`suite_id`** values to run (static allowlist or **`suite_ids_for_profile`**).

### Adding application-specific suites

1. Subclass **`BenchTestSuite`** from **`mindtrace.core.testing.bench_suite`** (or contribute a **`SuiteContribution`** for non-class implementations).
2. Set:
   - **`suite_id`**: stable, namespaced string (e.g. **`my_service.orders.write_ceiling`**).
   - **`tags`**: include **`smoke`** and/or **`stress`** so **`suite_ids_for_profile`** and **`mindtrace-bench --profile`** can match.
   - **`task_schema`**: a **`TaskSchema`** with Pydantic **`input_schema`** / **`output_schema`** models. The input model documents accepted benchmark parameters; the output model documents serialized results.
   - **`resource_schema`**: optional Pydantic model for externally supplied resource config.
   - **`profiles`**: **`MappingProxyType`** from profile name to **`duration_seconds`**, parameters, and optional **`resources`**.
3. Implement **`execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult`**:
   - Loop until **`reporter.deadline(config.duration_seconds)`**; respect **`reporter.is_cancelled()`**.
   - Record work via **`reporter.record_operation(...)`**.
   - Return **`BenchResult`** with status, operation counts, and **`metrics`**.
4. Register with **`TestRunner.register_test_suite(MySuite)`**, often from **`def register_benchmark_suites(): ...`** in **`your_package.testing`**.

### Example: downstream project with one custom suite

Assume an application package **`example_app`** that depends on **`mindtrace-core`**. Bench code typically lives beside the app code (layout and names are illustrative):

**`example_app/testing/benches.py`** — defines a suite tagged **`smoke`** and **`stress`** so both short and longer runs resolve from **`profiles`**:

```python
# example_app/testing/benches.py
from __future__ import annotations

import time
from types import MappingProxyType

from pydantic import BaseModel, Field

from mindtrace.core.types.task_schema import TaskSchema
from mindtrace.core.testing.bench_framework import (
    BenchReporter,
    BenchResult,
    BenchResultSchema,
    BenchSuiteConfig,
    utc_now_iso,
)
from mindtrace.core.testing.bench_suite import BenchTestSuite


class EchoLoopInput(BaseModel):
    iter_chunk: int = Field(50, ge=1, description="Inner loop iterations per recorded operation.")


class EchoLoopResources(BaseModel):
    """No external resources are required."""


class EchoLoopThroughputSuite(BenchTestSuite):
    """Replace the inner loop with real work (HTTP, queues, persistence, …)."""

    suite_id = "example.echo.loop_throughput"
    title = "Example — iterative throughput"
    description = "Measures how often a bounded chunk of work completes within the allotted window."
    tags = frozenset({"smoke", "stress", "example"})
    requires = ()
    safety = "Synthetic CPU loop only; trivial load."
    task_schema = TaskSchema(name=suite_id, input_schema=EchoLoopInput, output_schema=BenchResultSchema)
    resource_schema = EchoLoopResources
    profiles = MappingProxyType(
        {
            "smoke": {"duration_seconds": 0.75, "iter_chunk": 50},
            "stress": {"duration_seconds": 5.0, "iter_chunk": 2000},
        },
    )

    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        started = utc_now_iso()
        monotonic_start = time.perf_counter()
        chunk = int(config.parameters.get("iter_chunk", 100))
        deadline = reporter.deadline(config.duration_seconds)

        while time.perf_counter() < deadline and not reporter.is_cancelled():
            op_start = time.perf_counter()
            for _ in range(chunk):
                pass  # application work goes here
            latency = time.perf_counter() - op_start
            reporter.record_operation(
                success=True,
                latency_seconds=latency,
                bytes_processed=0,
                inner_iterations=chunk,
            )

        elapsed = time.perf_counter() - monotonic_start
        return BenchResult(
            suite_id=config.suite_id,
            status="passed" if reporter.failures == 0 else "failed",
            started_at=started,
            ended_at=utc_now_iso(),
            duration_seconds=elapsed,
            operations=reporter.operations,
            successes=reporter.successes,
            failures=reporter.failures,
            bytes_processed=reporter.bytes_processed,
            latency_seconds=reporter.latency_seconds,
            error_counts=reporter.error_counts,
            metrics=dict(reporter.metrics, iter_chunk=chunk),
        )
```

**`example_app/testing/__init__.py`** — register on import (same pattern Mindtrace wheels use):

```python
# example_app/testing/__init__.py
from mindtrace.core.testing.runner import TestRunner

from example_app.testing.benches import EchoLoopThroughputSuite


def register_benchmark_suites(*, runner: TestRunner | None = None, replace: bool = True) -> None:
    target = runner or TestRunner.default()
    target.register_test_suite(EchoLoopThroughputSuite, replace=replace)


register_benchmark_suites()
```

**Running it** — create an isolated runner, register your suites and optionally Mindtrace’s, and call **`run_registered_benches`** with the suite ID, **`profile`**, and **`runner`**:

```python
# e.g. example_app/bench_run.py or a small __main__.py CLI
from mindtrace.core.testing.driver import run_registered_benches, suite_ids_for_profile
from mindtrace.core.testing.runner import TestRunner

runner = TestRunner()
import example_app.testing

example_app.testing.register_benchmark_suites(runner=runner)
# Optional: import mindtrace.registry.testing and register into the same runner.

bench_results, exec_rows = run_registered_benches(
    ["example.echo.loop_throughput"],
    profile="smoke",
    run_id="2026-03-09Tbench-local",
    resources={},  # e.g. merge API base URLs / DB URIs from your config here
    runner=runner,
)

for bench in bench_results:
    print(bench.suite_id, bench.status, bench.to_dict())

assert all(row.status == "passed" for row in exec_rows)
```

To list only your **`example.`** suites among those tagged **`stress`**:

```python
print([sid for sid in suite_ids_for_profile("stress", runner=runner) if sid.startswith("example.")])
```

---

### Entry point for operators and CI

Ship a small CLI (e.g. **`python -m your_package.bench`**) that imports Mindtrace and application **`testing`** modules, parses **`--profile`** / **`--list`**, and calls **`run_registered_benches`**, exiting non-zero on failed **`SuiteExecutionResult`** rows. Keep CI non-interactive with fixed suite lists or tag-based discovery.

### Resources and configuration

Pass secrets and service endpoints via your normal config layer; at bench time merge them into **`run_registered_benches(..., resources={...}, runner=runner)`** so **`build_bench_suite_config`** can unify Mindtrace defaults with overrides. Document which **`resources`** keys your suites consume.

### Recommended tagging

| Tag | Typical use |
|-----|--------------|
| **`smoke`** | Short wiring checks; minimal infrastructure; suited to PR gates. |
| **`stress`** | Longer throughput workloads; may need real backends or fuller stacks. |

Domain-specific tags (**`billing`**, **`api`**, …) reserve room for finer filtering if listing APIs evolve.

### Limitations of **`mindtrace-bench`**

The stock CLI only auto-imports a fixed set of first-party shorthand packages (**`registry`**, **`datalake`**). **Application-defined** suites require **your own small CLI** (or a Mindtrace enhancement such as **`--import your_package.testing`**; see backlog below).

---

## Mindtrace maintainers: backlog for downstream ergonomics

Checklist toward stronger third‑party integration (no backward compatibility requirement for superseded orchestration elsewhere in the repo):

### Documentation and API contract

- [ ] Treat **`mindtrace.core.testing`**’s **`run_registered_benches`**, **`BenchTestSuite`**, and **`BenchResult`** as explicitly versioned **public surface** where stability is promised.
- [ ] Document **`resources`** keys read by first-party **`BenchTestSuite`** implementations (Mongo, MinIO, GCS, …).
- [ ] Publish **`suite_id` naming** guidance to reduce collisions across teams and packages.

### CLI

- [ ] Pluggable imports for **`mindtrace-bench`** (e.g. **`--import your_package.testing`** or entry-point discovery) so applications do not fork **`__main__`**.
- [ ] Repeatable **`--suite <id>`** and optional multi-tag filters once **`TestRunner.list_suite_ids`** supports them.
- [ ] Machine-readable listing (JSON) for CI matrix generation.

### Registration and safety

- [ ] Document when to use isolated **`TestRunner()`** instances vs the global default runner and idempotent **`register_benchmark_suites(replace=False)`**.
- [ ] Clarify whether **`requires`** is advisory, validated, or enforced; align implementation with docs.

### Observability

- [ ] Optional hooks or patterns for writing **`BenchResult`** / **`SuiteExecutionResult`** to structured artifacts (JSON) under a stable directory layout.
- [ ] Logging field contract: **`run_id`**, **`suite_id`**, profile, counts, durations, failures.

### Tests and packaging

- [ ] Contract tests that register a **synthetic third-party **`BenchTestSuite`** next to Mindtrace benches and run **`run_registered_benches`** after refactors.
- [ ] Document optional extras for backends (S3, GCS, …) needed for specific benches.
- [ ] Decide whether **`mindtrace-bench`** stays in **`mindtrace-core`** if optional dependencies grow.

---

## Quick reference

| Goal | Action |
|------|--------|
| Run shipped Mindtrace benches | `import mindtrace.<pkg>.testing` → **`run_registered_benches(...)`** |
| Add custom benches | Subclass **`BenchTestSuite`**, tag **`smoke`** / **`stress`**, **`register_test_suite`** |
| CI / ops | Thin app CLI; pass **`resources`** from environment / config |

For high-level context, see the **Stress / benchmark plugins** section in **[README.md](README.md)** (this file is the detailed reference).
