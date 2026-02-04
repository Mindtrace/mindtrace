#!/usr/bin/env python3
"""
Bump version across all mindtrace packages in the monorepo.

Usage:
    uv run scripts/bump_version.py 0.7.1
"""

import argparse
import re
import sys
from pathlib import Path

import tomlkit

PACKAGE_PREFIX = "mindtrace-"


def update_dependency(dep: str, new_version: str) -> str:
    """
    Update a PACKAGE_PREFIX* dependency string to include >=new_version.

    Examples:
        "mindtrace-core" -> "mindtrace-core>=0.7.1"
        "mindtrace-core>=0.5.0" -> "mindtrace-core>=0.7.1"
        "mindtrace-hardware[cameras-basler]>=0.5.0" -> "mindtrace-hardware[cameras-basler]>=0.7.1"
    """
    # Match package name with optional extras, strip any existing version
    pattern = rf"^({re.escape(PACKAGE_PREFIX)}[a-z]+(?:\[[^\]]+\])?)(?:>=?.*)?$"
    match = re.match(pattern, dep)
    if match:
        return f"{match.group(1)}>={new_version}"
    return dep


def update_dependency_list(deps: list, new_version: str) -> bool:
    """Update PACKAGE_PREFIX* dependencies in a list. Returns True if any changed."""
    changed = False
    for i, dep in enumerate(deps):
        if isinstance(dep, str) and dep.startswith(PACKAGE_PREFIX):
            new_dep = update_dependency(dep, new_version)
            if new_dep != dep:
                deps[i] = new_dep
                changed = True
    return changed


def bump_version_in_file(filepath: Path, new_version: str) -> bool:
    """
    Update version and PACKAGE_PREFIX* dependencies in a pyproject.toml file.

    Args:
        filepath: Path to the pyproject.toml file
        new_version: The new version string (e.g., "0.7.1")

    Returns:
        True if changes were made, False otherwise
    """
    content = filepath.read_text()
    data = tomlkit.parse(content)
    changed = False

    project = data.get("project", {})

    # 1. Update the package version in [project] section
    if "version" in project and project["version"] != new_version:
        project["version"] = new_version
        changed = True

    # 2. Update PACKAGE_PREFIX* in project.dependencies
    changed |= update_dependency_list(project.get("dependencies", []), new_version)

    # 3. Update PACKAGE_PREFIX* in all [project.optional-dependencies] groups
    for deps in project.get("optional-dependencies", {}).values():
        changed |= update_dependency_list(deps, new_version)

    # 4. Update PACKAGE_PREFIX* in all [dependency-groups] groups (PEP 735)
    for deps in data.get("dependency-groups", {}).values():
        changed |= update_dependency_list(deps, new_version)

    if changed:
        filepath.write_text(tomlkit.dumps(data))
    return changed


def find_subpackage_pyprojects(root: Path) -> list[Path]:
    """Find all pyproject.toml files in mindtrace subdirectories."""
    return sorted((root / "mindtrace").glob("*/pyproject.toml"))


def main():
    parser = argparse.ArgumentParser(description="Bump version across all mindtrace packages")
    parser.add_argument("version", help="New version (e.g., 0.7.1 or v0.7.1)")

    args = parser.parse_args()
    new_version = args.version.lstrip("vV")

    # Validate version format
    if not re.match(r"^\d+\.\d+\.\d+$", new_version):
        parser.error(f"Invalid version format: {new_version}. Expected: X.Y.Z")

    # Find project root (where this script is in scripts/)
    script_dir = Path(__file__).parent
    root = script_dir.parent

    root_pyproject = root / "pyproject.toml"
    if not root_pyproject.exists():
        print(f"Error: {root_pyproject} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Bumping all packages to version {new_version}\n")

    # Update root pyproject.toml
    if bump_version_in_file(root_pyproject, new_version):
        print(f"✓ Updated {root_pyproject.relative_to(root)}")
    else:
        print(f"- No changes: {root_pyproject.relative_to(root)}")

    # Update all subpackage pyproject.toml files
    subpackages = find_subpackage_pyprojects(root)

    for pyproject in subpackages:
        if bump_version_in_file(pyproject, new_version):
            print(f"✓ Updated {pyproject.relative_to(root)}")
        else:
            print(f"- No changes: {pyproject.relative_to(root)}")

    print(f"\nDone! {len(subpackages) + 1} files bumped to version {new_version}")


if __name__ == "__main__":
    main()
