from mindtrace.core.config import Config
from mindtrace.core.logging import Logger


class Mindtrace:
    """Base class for Mindtrace components."""

    def __init__(self):
        self.config = Config()
        self.logger = Logger()
