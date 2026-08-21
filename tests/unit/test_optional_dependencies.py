from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _optional_dependencies(pyproject_path: Path) -> dict[str, list[str]]:
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return payload["project"]["optional-dependencies"]


def _requirement_names(requirements: list[str]) -> set[str]:
    return {re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0] for requirement in requirements}


def test_root_optional_dependencies_namespace_datalake_and_models_extras() -> None:
    extras = _optional_dependencies(REPOSITORY_ROOT / "pyproject.toml")

    assert extras["datalake-import-flowers102"] == ["mindtrace-datalake[import-flowers102]>=0.14.1.dev0"]
    assert extras["datalake-export-huggingface"] == ["mindtrace-datalake[export-huggingface]>=0.14.1.dev0"]
    assert extras["datalake-export-all"] == ["mindtrace-datalake[export-all]>=0.14.1.dev0"]
    assert extras["models-dataloaders"] == ["mindtrace-models[dataloaders]>=0.14.1.dev0"]
    assert {"import-flowers102", "export-huggingface", "export-all", "dataloaders"}.isdisjoint(extras)


def test_models_all_contains_dataloader_dependencies() -> None:
    extras = _optional_dependencies(REPOSITORY_ROOT / "mindtrace" / "models" / "pyproject.toml")

    assert _requirement_names(extras["dataloaders"]) <= _requirement_names(extras["all"])
