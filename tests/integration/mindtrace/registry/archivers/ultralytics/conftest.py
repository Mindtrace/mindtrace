"""Conftest for ultralytics archiver tests."""
import importlib.util
import sys
from pathlib import Path

import pytest

# Import MockAssets class from the top-level conftest
# Use path-based import to avoid conflicts with site-packages tests module
tests_dir = Path(__file__).parents[5]  # Go up to tests/ directory
conftest_path = tests_dir / "conftest.py"
spec = importlib.util.spec_from_file_location("tests_conftest", conftest_path)
tests_conftest = importlib.util.module_from_spec(spec)
sys.modules["tests_conftest"] = tests_conftest
spec.loader.exec_module(tests_conftest)
MockAssets = tests_conftest.MockAssets


@pytest.fixture(scope="session")
def mock_assets():
    """Fixture providing the MockAssets instance for ultralytics tests."""
    return MockAssets()

