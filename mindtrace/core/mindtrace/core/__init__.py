from mindtrace.core.utils import ifnone, first_not_none
from mindtrace.core.base import Mindtrace, MindtraceABC
from mindtrace.core.logging.logger import setup_logger

setup_logger()  # Initialize the default logger


__all__ = ["first_not_none", "ifnone", "Mindtrace", "MindtraceABC"]
