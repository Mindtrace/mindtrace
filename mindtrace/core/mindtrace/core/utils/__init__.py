from mindtrace.core.utils.checks import check_libs, first_not_none, ifnone, ifnone_url
from mindtrace.core.utils.cropping import CropExtractor
from mindtrace.core.utils.download import download_and_extract_tarball, download_and_extract_zip
from mindtrace.core.utils.dynamic import instantiate_target
from mindtrace.core.utils.ini import load_ini_as_dict
from mindtrace.core.utils.lambdas import named_lambda
from mindtrace.core.utils.letterbox import LetterBox
from mindtrace.core.utils.masks import MaskProcessor
from mindtrace.core.utils.network import (
    LocalIPError,
    NetworkError,
    NoFreePortError,
    PortInUseError,
    ServiceTimeoutError,
    check_port_available,
    get_free_port,
    get_local_ip,
    get_local_ip_safe,
    is_port_available,
    wait_for_service,
)
from mindtrace.core.utils.paths import expand_tilde, expand_tilde_str
from mindtrace.core.utils.system_metrics_collector import SystemMetricsCollector


def __getattr__(name: str):
    # Lazy import to break circular dependency:
    # image_io.py -> mindtrace.core.base -> config -> utils.__init__ -> image_io.py
    if name == "ImageLoader":
        from mindtrace.core.utils.image_io import ImageLoader  # noqa: PLC0415
        return ImageLoader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "check_libs",
    "check_port_available",
    "CropExtractor",
    "first_not_none",
    "get_free_port",
    "get_local_ip",
    "get_local_ip_safe",
    "ifnone",
    "ifnone_url",
    "ImageLoader",
    "instantiate_target",
    "is_port_available",
    "LetterBox",
    "LocalIPError",
    "MaskProcessor",
    "named_lambda",
    "download_and_extract_zip",
    "download_and_extract_tarball",
    "expand_tilde",
    "expand_tilde_str",
    "load_ini_as_dict",
    "NetworkError",
    "NoFreePortError",
    "PortInUseError",
    "ServiceTimeoutError",
    "SystemMetricsCollector",
    "wait_for_service",
]
