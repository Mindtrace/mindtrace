import logging

import pytest
from _pytest.mark import Mark

empty_mark = Mark('', [], {})


def by_slow_marker(item):
    # Check if test is marked as slow
    is_slow = 0 if item.get_closest_marker("slow") is None else 1
    
    # Check if test is integration test
    is_integration = 1 if "integration" in str(item.fspath) else 0
    
    # Return tuple for sorting: (is_integration, is_slow)
    # This will sort unit tests first, then slow unit tests,
    # then integration tests, then slow integration tests
    return (is_integration, is_slow)


def pytest_addoption(parser):
    parser.addoption('--slow-last', action='store_true', default=False)


def pytest_collection_modifyitems(items, config):
    if config.getoption('--slow-last'):
        items.sort(key=by_slow_marker)


@pytest.fixture(autouse=True)
def configure_logging_for_tests(caplog):
    """Configure logging to work properly with caplog fixture.
    
    This fixture ensures that all Mindtrace loggers propagate their messages to the root logger so that caplog can 
    capture them properly.
    """
    # Set caplog to capture all levels
    caplog.set_level(logging.DEBUG)
    
    # Configure the root logger to ensure proper propagation
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)
    
    # Ensure mindtrace loggers propagate to root
    mindtrace_logger = logging.getLogger('mindtrace')
    original_propagate = mindtrace_logger.propagate
    mindtrace_logger.propagate = True
        
    yield
    
    # Restore original settings
    root_logger.setLevel(original_level)
    mindtrace_logger.propagate = original_propagate
