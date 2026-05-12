# Mindtrace Testing — suite registry (`mindtrace.testing`)

Design doc for **`mindtrace.testing`**, shipped in **`mindtrace-core`**. It provides a **process-global registry** of test suites (workloads you can invoke with.harness-specific `(config, reporter)` objects), patterned after **class-level Mindtrace Registry registration**—not setuptools entry points and not instantiable runner objects.

---

## Plan (migration summary)

1. Suites register explicitly via **`TestRunner.register_suite(SuiteContribution)`** (typically from library import/bootstrap modules).
2. Callers optionally batch-execute registered IDs with **`TestRunner.run`** (progress callbacks + **`RunOutcome`**) or invoke one suite with **`TestRunner.invoke_suite`**.
3. The in-repo **`tests/stress`** harness unions **`manifest.yaml`** with **`TestRunner.registered_suites()`** when **`merge_registered=True`**—manifest wins on duplicate IDs.
4. **No entry-point discovery**, no singleton **`TestRunner()`** instances, no YAML inside **`mindtrace-core`**.

---

## Concepts

| Term | Meaning |
|------|---------|
| **`SuiteId`** | Stable suite key; validated by **`validate_suite_id`**. |
| **`SuiteContribution`** | Frozen payload: **`id`**, **`title`**, **`run(config, reporter)`**, optional **`tags`**, **`requires`**, **`parameters`**, **`profiles`**, **`safety`**. |
| **`TestRunner`** | Namespace of **classmethods only** (`__new__` raises). Mirrors **`Registry.register_default_materializer`**: register once per process / test isolation via **`clear_registry`**. |

The **`tests/stress`** harness still uses **`StressSuiteConfig`** / **`StressReporter`** (`tests/stress/lib/benchmark.py`). **`mindtrace-core`** stays decoupled: **`SuiteRun = Callable[[Any, Any], Any]`**.

---

## Registration (primary API)

Packages or bootstrap modules execute at import:

```python
from mindtrace.testing import SuiteContribution, TestRunner


def run_payload_ceiling(config: object, reporter: object) -> object:
    # Stress harness passes StressSuiteConfig + StressReporter
    reporter.event("operation", note="warmup")
    return None


TestRunner.register_suite(
    SuiteContribution(
        id="mindtrace.my_module.payload_ceiling.smoke",
        title="Payload write ceiling",
        run=run_payload_ceiling,
        tags=frozenset({"io", "local"}),
        profiles={"smoke": {"duration": "5s", "warmup": "0s", "cooldown": "0s"}},
    ),
)
```

Duplicates: second **`register_suite`** raises **`ValueError`** unless **`replace=True`**.

---

## Execution

**Single suite (delegate to callable):**

```python
result = TestRunner.invoke_suite(suite_id, config, reporter)
```

**Batch (unified envelope + optional progress):**

```python
from mindtrace.testing import SuiteExecutionResult, TestRunner


def exec_one(contrib: SuiteContribution) -> SuiteExecutionResult:
    try:
        # Build config/reporter from your orchestrator …
        return SuiteExecutionResult(suite_id=contrib.id, status="passed")
    except Exception as exc:
        return SuiteExecutionResult(suite_id=contrib.id, status="failed", error=exc)


outcome = TestRunner.run(
    ["vendor.suite.a", "vendor.suite.b"],
    execute=exec_one,
    progress=lambda ev: print(ev.kind, ev.suite_id),
)
```

**`suite_ids`** **`None`** runs **every** registered suite (sorted IDs). An empty registry yields **`overall="empty"`**.

---

## Test isolation

`TestRunner.clear_registry()` wipes all registrations—use **`pytest`** fixtures (**`autouse`**) **only when no other concurrent tests share the interpreter**.

Prefer **`unregister_suite(id)`** for surgical cleanup.

---

## Stress runner integration

`tests/stress/lib/runner.py` merges manifest definitions with **`TestRunner.registered_suites()`** via **`merge_suite_definitions_with_plugins(..., merge_registered=True)`**.

`list_stress_suites(..., merge_registered=False)` lists manifest suites only—useful for deterministic unit tests without registry pollution.

---

## Security

Registration mutates global state; callers can register arbitrary callables equivalent to **`import`**. Isolate environments appropriately.
