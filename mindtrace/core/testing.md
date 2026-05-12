# Mindtrace Testing — suite plugins

This note describes **`mindtrace.testing`**, shipped in the **`mindtrace-core`** wheel. It provides a **plugin registry** so optional packages (and in-process callers) can **register benchmark-style stress suites** that integrate with Mindtrace tooling.

Goals:

1. **Entry-point discovery** — installed distributions advertise loaders via setuptools **`pyproject.toml`** **`[project.entry-points]`**.
2. **Explicit registration** — embedders, notebooks, and tests call **`TestRunner.register(...)`** without packaging entry points.
3. **Lazy loading** — calling **`import mindtrace.testing`** must not execute third-party workloads; loaders run only during **`discover_plugins()`** (or **`list_suite_ids` / `get_resolved`** / **`run_stress_workload`** after discovery).

YAML manifest dotted-path wiring is **not** implemented here; the in-repo **`tests/stress`** runner merges manifest suites **with** registered plugins when you use its APIs (see “Stress runner integration”).

---

## Concepts

| Term | Meaning |
|------|---------|
| **`SuiteId`** | Stable string ID for a suite. Must match the regex documented on **`validate_suite_id`**. Prefer vendor prefixes (**`mindtrace.registry.*`**, **`chiron.*`**, …) to avoid clashes. |
| **`SuiteContribution`** | Immutable descriptor: ID, **`title`**, **`run`** callable, optional **`tags`**, **`requires`**, manifest-shaped **`parameters`** / **`profiles`**, **`safety`**. |
| **`TestRunner`** | Owns **`SuiteRegistry`** state, merges **explicit** registrations with **plugins**, applies collision rules. |
| **Entry-point group** | Canonical name: **`mindtrace.testing.suite_loader`**. Each entry **`name`** is the **`SuiteId`**; the **`value`** is an import path to a **loader callable**. |

Workload contract (stress runner):

- **`run(config, reporter)`** — same convention as **`tests/stress`** manifest suites: **`config`** is a **`StressSuiteConfig`**, **`reporter`** a **`StressReporter`**, return **`StressResult`** or **`None`** (the runner synthesizes summaries when needed).

The **`mindtrace.testing`** layer types this as **`SuiteRun`** (**`Callable[[Any, Any], Any]`**) so **`mindtrace-core`** does **not** import **`tests.stress`**.

---

## Entry points (primary discovery)

Declare loaders under the group **`mindtrace.testing.suite_loader`**. Install your wheel alongside **`mindtrace-core`**.

 **`pyproject.toml`** example:

```toml
[project.entry-points."mindtrace.testing.suite_loader"]
"mindtrace.example.echo_smoke" = "my_company.stress:load_suites"
```

Loader implementation (**`my_company/stress.py`**):

```python
from __future__ import annotations

from collections.abc import Iterable

from mindtrace.testing import SuiteContribution


def load_suites() -> Iterable[SuiteContribution]:
    """Return suites for this plugin (may be lazily imported inside this function).

    Prefer keeping heavy imports *inside* this function so unrelated environments
    do not pull your dependencies at ``import my_company``.
    """

    def run(config: object, reporter: object) -> object:
        # Implement workload using StressSuiteConfig / StressReporter at runtime.
        reporter.event("operation", payload={"note": "echo_smoke"})
        return None

    return [
        SuiteContribution(
            id="mindtrace.example.echo_smoke",
            title="Example echo workload",
            run=run,
            tags=frozenset({"cpu", "local"}),
            requires=(),
            parameters={},
            profiles={
                "smoke": {"duration": "5s", "warmup": "0s", "cooldown": "0s"},
            },
        )
    ]
```

Notes:

- The **entry-point name** and **`SuiteContribution.id`** should match (**`mindtrace.example.echo_smoke`** above).
- **`profiles`** should include **`smoke`** at minimum if callers use **`--profile smoke`** (matching **`tests/stress`** behavior).

---

## Explicit registration (secondary)

Use when you prototype in a notebook, wrap a downstream app inside another process, or inject fakes in unit tests:

```python
from mindtrace.testing import SuiteContribution, TestRunner


def noop_run(config, reporter) -> None:
    reporter.event("suite_progress", noop=True)


runner = TestRunner()
runner.register(
    SuiteContribution(
        id="local.demo.noop",
        title="Demo",
        run=noop_run,
        profiles={"smoke": {"duration": "2s"}},
    )
)
suite_ids = runner.list_suite_ids()
```

**Globals:** prefer constructing your own **`TestRunner`**. **`default_test_runner()`** returns a shared instance for tooling that genuinely needs one process-wide registry.

---

## API surface

Rough flow:

```text
runner = TestRunner(strict_plugin_duplicates=False)
runner.register(...)                           # explicit
runner.discover_plugins()                      # import entry_points, call loaders (lazy)
runner.list_suite_ids(tags={"mongo"})         # filtered listing
resolved = runner.get_resolved("my.suite.id")  # ResolvedSuite wrapper
runner.run_stress_workload(suite_id, config, reporter)  # invokes contribution.run(...)
```

Important flags:

- **`strict_plugin_duplicates`** — if **True**, two plugins claiming the same **`SuiteId`** raises **`DuplicateSuiteIdError`**.
- **Explicit overrides plugin** — if you **`register`** the same ID as an entry-point suite, the explicit contribution wins; **`discovery_notes`** may record that override.

Diagnostics:

- **`runner.plugin_load_errors`** — **`PluginLoadError`** instances for loaders that threw or produced invalid payloads.
- **`runner.discovery_notes`** — non-fatal messages (skipped duplicate, explicit overriding plugin).

---

## Stress runner integration

The repository stress harness (**`tests/stress/lib/runner.py`**) merges **`SuiteDefinition`** entries from **`manifest.yaml`** with contributions discovered via **`merge_suite_definitions_with_plugins(...)`** (which forwards to **`default_test_runner()`** unless you pass your own **`TestRunner`**).

For full plans:

When building a **`StressPlanRequest`**, **`resolve_stress_plan(..., test_runner=my_runner)`** accepts an isolated **`TestRunner`** for tests.

```python
plan = resolve_stress_plan(request, test_runner=my_runner)
```

**`list_stress_suites()`** unions manifest metadata with plugins for **`ds test --stress --list`**.

---

## Security

Entry points are **trusted like imports**. Installing a hostile wheel may register workloads that execute with your **`StressSuiteConfig`**. Run stress only in isolated environments or with controlled installs.

Future allowlisting (**`MINDTRACE_TESTING_ALLOWED_PREFIXES`**, …) may be added separately.

---

## Versioning

The **loader return shape** (**`Iterable[SuiteContribution]`**) and **`SuiteContribution`** fields are public contracts. Prefer **semver** bumps on incompatible changes to **`mindtrace-core`**.
