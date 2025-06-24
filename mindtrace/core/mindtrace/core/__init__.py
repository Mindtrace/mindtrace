from mindtrace.core.utils import ifnone, first_not_none
from mindtrace.core.base import Mindtrace, MindtraceABC
from mindtrace.core.logging.logger import setup_logger

setup_logger()  # Initialize the default logger

from mindtrace.core.observables.event_bus import EventBus
from mindtrace.core.observables.observable_context import ObservableContext
from mindtrace.core.observables.context_listener import ContextListener

__all__ = [
    "ContextListener", 
    "EventBus", 
    "first_not_none", 
    "ifnone", 
    "Mindtrace", 
    "MindtraceABC", 
    "ObservableContext"
]
