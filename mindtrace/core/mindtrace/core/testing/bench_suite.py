"""Base :class:`BenchTestSuite` and helpers to resolve :class:`BenchSuiteConfig`."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mindtrace.core.testing.bench_framework import BenchReporter, BenchResult, BenchSuiteConfig, CancellationToken
from mindtrace.core.testing.test_suite import TestSuite
from mindtrace.core.testing.types import SuiteContribution

_RESERVED_PROFILE_KEYS = frozenset({"duration_seconds", "warmup_seconds", "cooldown_seconds", "resources"})


def build_bench_suite_config(
    contrib: SuiteContribution,
    *,
    profile: str,
    run_id: str,
    label: str | None = None,
    resources: Mapping[str, Any] | None = None,
    extra_parameters: Mapping[str, Any] | None = None,
    output_dir: Path | None = None,
    keep_resources: bool = False,
    cancellation_token: CancellationToken | None = None,
) -> BenchSuiteConfig:
    """Merge contribution defaults with a named profile overlay."""

    overlay = dict(contrib.profiles.get(profile, contrib.profiles.get("stress", {})))

    duration_seconds = float(
        overlay.pop("duration_seconds", 10.0 if profile == "stress" else 1.5),
    )
    warmup_seconds = float(overlay.pop("warmup_seconds", 0.0))
    cooldown_seconds = float(overlay.pop("cooldown_seconds", 0.0))

    nested_resources = overlay.pop("resources", {})
    if nested_resources is None:
        nested_resources = {}
    if not isinstance(nested_resources, Mapping):  # pragma: no cover - defensive
        nested_resources = {}

    params = dict(contrib.parameters)
    for key, value in overlay.items():
        if key in _RESERVED_PROFILE_KEYS:
            continue
        params[key] = value

    if extra_parameters:
        params.update(dict(extra_parameters))

    merged_resources: dict[str, Any] = dict(nested_resources)
    merged_resources.update(dict(resources or {}))

    return BenchSuiteConfig(
        suite_id=contrib.id,
        label=label or contrib.title,
        profile=profile,
        duration_seconds=duration_seconds,
        warmup_seconds=warmup_seconds,
        cooldown_seconds=cooldown_seconds,
        parameters=params,
        resources=merged_resources,
        output_dir=output_dir or Path(".stress-results"),
        run_id=run_id,
        keep_resources=keep_resources,
        variant_id=None,
        base_suite_id=contrib.id,
        requires=list(contrib.requires),
        safety=contrib.safety,
        cancellation_token=cancellation_token,
    )


def coerce_bench_reporter(reporter: Any, config: BenchSuiteConfig) -> BenchReporter:
    if isinstance(reporter, BenchReporter):
        return reporter
    return BenchReporter(
        suite_id=config.suite_id,
        run_id=config.run_id,
        cancellation_token=config.cancellation_token,
    )


def coerce_bench_config(config: Any, *, suite_cls: type[BenchTestSuite]) -> BenchSuiteConfig:
    if isinstance(config, BenchSuiteConfig):
        return config
    contrib = suite_cls.as_contribution()
    if isinstance(config, dict):
        profile = str(config.get("profile", "stress"))
        return build_bench_suite_config(
            contrib,
            profile=profile,
            run_id=str(config.get("run_id", "local")),
            label=config.get("label") if config.get("label") is not None else None,
            resources=config.get("resources") if isinstance(config.get("resources"), Mapping) else {},
            extra_parameters=config.get("parameters") if isinstance(config.get("parameters"), Mapping) else None,
            output_dir=Path(config["output_dir"]) if config.get("output_dir") else None,
            keep_resources=bool(config.get("keep_resources", False)),
            cancellation_token=config.get("cancellation_token"),
        )
    raise TypeError(f"Expected BenchSuiteConfig or dict for bench config, got {type(config)!r}")


class BenchTestSuite(TestSuite):
    """Library-embedded timed suite using :class:`BenchSuiteConfig` / :class:`BenchReporter`.

    Subclasses implement :meth:`execute_bench`. Class-level :attr:`profiles` should define at least
    ``smoke`` (short wiring / install checks) and ``stress`` (~10s sustained workloads by default).
    """

    def run(self, config: object, reporter: object) -> BenchResult:
        bc = coerce_bench_config(config, suite_cls=type(self))
        br = coerce_bench_reporter(reporter, bc)
        return self.execute_bench(bc, br)

    @abstractmethod
    def execute_bench(self, config: BenchSuiteConfig, reporter: BenchReporter) -> BenchResult:
        """Run one invocation under resolved bench configuration."""
