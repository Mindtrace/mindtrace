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
