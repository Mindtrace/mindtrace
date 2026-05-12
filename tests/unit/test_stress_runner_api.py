from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.stress.lib.models import StressPlanRequest
from tests.stress.lib.runner import (
    DEFAULT_MANIFEST,
    load_stress_events,
    list_stress_suites,
    resolve_stress_plan,
    safe_run_dir,
)


def test_list_stress_suites_exposes_metadata() -> None:
    suites = {suite.suite_id: suite for suite in list_stress_suites(DEFAULT_MANIFEST)}

    payload_suite = suites["datalake.payload-write-ceiling"]
    assert payload_suite.label == "Datalake / payload write ceiling"
    assert payload_suite.parameters["payload_size"].aliases == ["object_size"]
    assert payload_suite.parameters["backend"].choices == ["local", "minio", "gcs"]


def test_resolve_stress_plan_normalizes_alias_and_expands_matrix(tmp_path: Path) -> None:
    plan = resolve_stress_plan(
        StressPlanRequest(
            manifest_path=DEFAULT_MANIFEST,
            run_id="unit-plan",
            suites=["datalake.payload-write-ceiling"],
            params={"object_size": ["1KiB", "1MiB"], "backend": ["local", "minio"]},
            output_dir=tmp_path / "unit-plan",
            no_menu=True,
        )
    )

    assert plan.run_id == "unit-plan"
    assert len(plan.cases) == 4
    assert {case.parameters["payload_size"] for case in plan.cases} == {"1KiB", "1MiB"}
    assert all("object_size" not in case.parameters for case in plan.cases)
    assert all(case.variant_id.startswith("datalake.payload-write-ceiling[") for case in plan.cases)


def test_resolve_stress_plan_reports_resource_warnings(tmp_path: Path) -> None:
    plan = resolve_stress_plan(
        StressPlanRequest(
            manifest_path=DEFAULT_MANIFEST,
            run_id="unit-gcs",
            suites=["datalake.payload-write-ceiling"],
            params={"backend": ["gcs"]},
            external_resources=True,
            config_payload={"resources": {}},
            output_dir=tmp_path / "unit-gcs",
            no_menu=True,
        )
    )

    assert any("gcs_project_id" in warning for warning in plan.warnings)
    assert any("gcs_bucket_name" in warning for warning in plan.warnings)
    assert plan.resource_config_redacted == {"resources": {}}


def test_invalid_run_id_cannot_escape_results_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        safe_run_dir("../escape", tmp_path)

    with pytest.raises(ValueError):
        safe_run_dir("/tmp/escape", tmp_path)


def test_load_stress_events_filters_by_sequence(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "t1", "run_id": "run-1", "event": "run_started", "sequence": 1, "payload": {}}),
                json.dumps({"timestamp": "t2", "run_id": "run-1", "event": "run_completed", "sequence": 2, "payload": {}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    events = load_stress_events("run-1", since_sequence=1, results_root=tmp_path)

    assert [event.sequence for event in events] == [2]
    assert events[0].event == "run_completed"
