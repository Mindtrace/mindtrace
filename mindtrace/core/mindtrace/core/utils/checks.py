from typing import Iterable

from urllib3.util.url import Url, parse_url


def ifnone[T1, T2](val: T1 | None, default: T2) -> T1 | T2:
    """Return the given value if it is not None, else return the default."""
    return val if val is not None else default


def first_not_none[T1, T2](vals: Iterable[T1 | None], default: T2 = None) -> T1 | T2:
    """Returns the first not-None value in the given iterable, else returns the default."""
    return next((item for item in vals if item is not None), default)


def ifnone_url(url: str | Url | None, default: str | Url) -> Url:
    """Wraps ifnone to always return a URL.

    Args:
        url: The Url to return. If none, the default value will be returned instead.
        default: The default URL to use if url is None.

    Returns:
        The Url object.
    """
    return ifnone(
        parse_url(url) if isinstance(url, str) else url, parse_url(default) if isinstance(default, str) else default
    )


def check_libs(required_libs: str | list[str]) -> list[str]:
    """Check if all required libraries are available.

    Args:
        required_libs: A list of library names to check.

    Returns:
        A list of missing libraries.
    """
    if isinstance(required_libs, str):
        required_libs = [required_libs]
    missing_libs = []
    for lib in required_libs:
        try:
            __import__(lib)
        except ImportError:
            missing_libs.append(lib)
    return missing_libs
