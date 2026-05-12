# Test suite runner (`mindtrace.core`)

Bench / workload suites register on **`TestRunner`** (classmethods only—do not instantiate the class). Typical pattern:

```python
from mindtrace.core import TestRunner, TestSuite


class PayloadSuite(TestSuite):
    suite_id = "acme.registry.payload_smoke"
    title = "Payload smoke"
    tags = frozenset({"registry", "io"})
    profiles = {"smoke": {"duration": "10s"}}

    def run(self, config, reporter):
        ...


TestRunner.register_test_suite(PayloadSuite)
```

`TestSuite` subclasses carry **metadata as class attributes** (`suite_id`, `title`, tags, profiles, …). **`TestRunner.register_test_suite(MySuite)`** builds a stored contribution with a **fresh `MySuite()` instance per `run`**. For ad-hoc callables, use **`TestRunner.register_suite(SuiteContribution(...))`**.

Import from the public core surface:

```python
from mindtrace.core import TestRunner, TestSuite, SuiteContribution, RunOutcome
```

Each optional package can expose `mindtrace.<pkg>.testing` modules that call **`TestRunner.register_test_suite(...)`** when explicitly imported by the user or CLI bootstrap.

The in-repo stress harness merges **`manifest.yaml`** with **`TestRunner.registered_suites()`** when listing or resolving plans (`tests/stress`).

## Plan (unchanged intent)

1. Packages implement **`TestSuite`** subclasses and register from their `testing` submodules.
2. **`tests/stress`** stays the CLI/manifest layer; manifest wins on duplicate suite IDs.
3. Use **`TestRunner.clear_registry()`** in unit tests when isolation is required.
