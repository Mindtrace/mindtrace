"""Discover and merge stress suite plugins (entry points + explicit registration)."""

from __future__ import annotations

import traceback
from collections.abc import Iterable, Iterator
from importlib.metadata import PackageNotFoundError, entry_points
from typing import Any

from mindtrace.testing.registry import SuiteRegistry
from mindtrace.testing.types import (
    DuplicateSuiteIdError,
    PluginLoadError,
    ResolvedSuite,
    SuiteContribution,
    SuiteRun,
    UnknownSuiteIdError,
    validate_suite_id,
)

ENTRY_POINT_GROUP = "mindtrace.testing.suite_loader"

_default_runner_singleton: TestRunner | None = None


def default_test_runner() -> TestRunner:
    """Shared process-global runner used by tooling (for example ``tests/stress``)."""

    global _default_runner_singleton
    if _default_runner_singleton is None:
        _default_runner_singleton = TestRunner(auto_discover=True)
    return _default_runner_singleton


def reset_default_test_runner() -> None:
    """Discard the singleton; intended for isolated tests."""

    global _default_runner_singleton
    _default_runner_singleton = None


def _distribution_meta(dist_ep: Any) -> tuple[str | None, str | None]:
    dist = getattr(dist_ep, "dist", None)
    if dist is None:
        return None, None
    try:
        name = dist.metadata["Name"]
    except Exception:
        name = getattr(dist, "name", None)
    version = None
    try:
        version = dist.version
    except Exception:
        try:
            from importlib.metadata import version as pkg_version

            if name:
                version = pkg_version(name)
        except PackageNotFoundError:
            version = None
    return name, version


class TestRunner:
    """Merge explicit ``register`` contributions with setuptools entry-point plugins."""

    ENTRY_POINT_GROUP = ENTRY_POINT_GROUP

    def __init__(
        self,
        *,
        strict_plugin_duplicates: bool = False,
        auto_discover: bool = True,
    ) -> None:
        self.strict_plugin_duplicates = strict_plugin_duplicates
        self.auto_discover = auto_discover
        self._registry = SuiteRegistry()
        self.plugin_load_errors: list[PluginLoadError] = []
        self.discovery_notes: list[str] = []
        self._discovery_done = False

    # --- explicit API ---

    def register(self, contribution: SuiteContribution) -> None:
        """Attach a caller-supplied workload (implicitly overrides duplicate plugin IDs later)."""

        self._registry.explicit[contribution.id] = contribution

    def unregister(self, suite_id: str) -> None:
        sid = validate_suite_id(suite_id)
        self._registry.explicit.pop(sid, None)

    def clear_explicit(self) -> None:
        self._registry.clear_explicit()

    # --- plugins ---

    def discover_plugins(self, *, reload: bool = False) -> int:
        """Load setuptools entry-point callables once (unless ``reload`` repopulates plugins).

        Returns how many loader callables were *attempted*, including loaders that crashed.
        Successful loads surface through ``effective_suite_map``; failures populate
        ``plugin_load_errors``.
        """

        if reload:
            self._registry.replace_plugins({})
            self.plugin_load_errors.clear()
            self.discovery_notes.clear()
            self._discovery_done = False
        elif self._discovery_done:
            return 0

        eps = tuple(entry_points(group=self.ENTRY_POINT_GROUP))
        staged: dict[str, SuiteContribution] = {}
        loaders_invoked = 0

        for ep in eps:
            loaders_invoked += 1

            try:
                validate_suite_id(ep.name)
            except ValueError as exc:
                self.plugin_load_errors.append(
                    PluginLoadError(
                        entry_name=ep.name,
                        message=f"entry-point name must be a valid SuiteId: {exc}",
                        distribution_name=None,
                        distribution_version=None,
                        exc_type=type(exc).__name__,
                    ),
                )
                continue

            dist_name, dist_version = _distribution_meta(ep)

            try:
                loader = ep.load()
            except Exception as exc:  # noqa: BLE001 - surface as PluginLoadError
                self.plugin_load_errors.append(
                    PluginLoadError(
                        entry_name=ep.name,
                        message=f"failed to load entry point: {exc}",
                        distribution_name=dist_name,
                        distribution_version=dist_version,
                        exc_type=type(exc).__name__,
                    ),
                )
                continue
            if not callable(loader):  # pragma: no cover - unlikely static misconfig
                self.plugin_load_errors.append(
                    PluginLoadError(
                        entry_name=ep.name,
                        message="entry-point target is not callable",
                        distribution_name=dist_name,
                        distribution_version=dist_version,
                    ),
                )
                continue

            raw: object | None
            try:
                raw = loader()
            except Exception as exc:  # noqa: BLE001
                tb = traceback.format_exc()
                self.plugin_load_errors.append(
                    PluginLoadError(
                        entry_name=ep.name,
                        message=f"loader raised: {exc}\n{tb}",
                        distribution_name=dist_name,
                        distribution_version=dist_version,
                        exc_type=type(exc).__name__,
                    ),
                )
                continue

            contributions = normalize_loader_payload(raw)

            for contrib in contributions:
                if not isinstance(contrib, SuiteContribution):
                    self.plugin_load_errors.append(
                        PluginLoadError(
                            entry_name=ep.name,
                            message=f"yielded non-contribution payload: {contrib!r}",
                            distribution_name=dist_name,
                            distribution_version=dist_version,
                        ),
                    )
                    continue
                if contrib.id != ep.name:
                    self.plugin_load_errors.append(
                        PluginLoadError(
                            entry_name=ep.name,
                            message=(
                                f"contribution.id {contrib.id!r} does not match entry-point name;"
                                " loaders must emit matching IDs."
                            ),
                            distribution_name=dist_name,
                            distribution_version=dist_version,
                        ),
                    )
                    continue
                if contrib.id in staged:
                    if self.strict_plugin_duplicates:
                        raise DuplicateSuiteIdError(
                            f"Duplicate suite contribution {contrib.id!r}; "
                            f"already registered by another loader in {ENTRY_POINT_GROUP}.",
                        )
                    self.discovery_notes.append(
                        f"Skipping duplicate plugin suite {contrib.id!r}; first registration wins.",
                    )
                    continue
                staged[contrib.id] = contrib

            if not contributions:
                self.discovery_notes.append(f"loader {ep.name!r} returned no contributions.")

        self._registry.replace_plugins(staged)
        self._apply_explicit_override_notes(previous_plugins=staged)
        self._discovery_done = True
        return loaders_invoked

    def _ensure_discovered(self) -> None:
        if self._discovery_done:
            return
        if self.auto_discover:
            self.discover_plugins()

    def _apply_explicit_override_notes(self, *, previous_plugins: dict[str, SuiteContribution]) -> None:
        overlapping = sorted(set(previous_plugins) & set(self._registry.explicit))
        for sid in overlapping:
            self.discovery_notes.append(
                f"Suite {sid!r} overridden by explicit TestRunner.register; plugin ignored.",
            )

    # --- resolution ---

    def effective_suite_map(self) -> dict[str, SuiteContribution]:
        """Return merged suites (explicit overlays plugins)."""

        self._ensure_discovered()
        merged = dict(self._registry.plugins)
        merged.update(self._registry.explicit)
        return merged

    def iter_resolved(self) -> Iterator[ResolvedSuite]:
        """Yield ``ResolvedSuite`` sorted by suite ID."""

        self._ensure_discovered()
        for sid in sorted(self.effective_suite_map()):
            if sid in self._registry.explicit:
                yield ResolvedSuite(self._registry.explicit[sid], source="explicit")
            else:
                yield ResolvedSuite(self._registry.plugins[sid], source="plugin")

    def list_suite_ids(self, *, tags: set[str] | None = None) -> list[str]:
        """Enumerate suite identifiers, optionally constrained by contribution tags."""

        self._ensure_discovered()
        results: list[str] = []
        for resolved in self.iter_resolved():
            if tags and not tags.intersection(set(resolved.contribution.tags)):
                continue
            results.append(resolved.contribution.id)
        return results

    def get_resolved(self, suite_id: str) -> ResolvedSuite:
        """Return the effective ``ResolvedSuite`` for ``suite_id``."""

        sid = validate_suite_id(suite_id)
        self._ensure_discovered()
        if sid in self._registry.explicit:
            return ResolvedSuite(self._registry.explicit[sid], source="explicit")
        if sid in self._registry.plugins:
            return ResolvedSuite(self._registry.plugins[sid], source="plugin")
        raise UnknownSuiteIdError(sid)

    def run_stress_workload(self, suite_id: str, config: object, reporter: object) -> object:
        """Invoke ``contribution.run`` for the resolved suite (after discovery)."""

        resolved = self.get_resolved(suite_id)
        run: SuiteRun = resolved.contribution.run
        return run(config, reporter)


def normalize_loader_payload(raw: object | None) -> list[SuiteContribution]:
    if raw is None:
        return []
    if isinstance(raw, SuiteContribution):
        return [raw]
    if isinstance(raw, dict):
        return []
    if isinstance(raw, str | bytes):
        return []
    if isinstance(raw, Iterable):
        return [item for item in raw if isinstance(item, SuiteContribution)]
    return []
