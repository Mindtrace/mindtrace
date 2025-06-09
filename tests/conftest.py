from _pytest.mark import Mark


empty_mark = Mark('', [], {})


def by_slow_marker(item):
    return 0 if item.get_closest_marker("slow") is None else 1


def pytest_addoption(parser):
    parser.addoption('--slow-last', action='store_true', default=False)


def pytest_collection_modifyitems(items, config):
    if config.getoption('--slow-last'):
        items.sort(key=by_slow_marker, reverse=True)
