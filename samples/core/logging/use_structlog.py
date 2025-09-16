"""
Sample: Enable structured logging with Mindtrace and structlog.

- Demonstrates enabling structlog via get_logger(use_structlog=True)
- Binds request-scoped context using structlog.contextvars (e.g., request_id)
- Shows positional formatting, and exception/stack rendering
- Logs are written to the configured MINDTRACE_LOGGER_DIR under modules/{logger_name}.log
  with a stdlib-style prefix and a structured JSON body.
"""

from mindtrace.core.logging.logger import get_logger
import structlog

logger = get_logger("services.api", use_structlog=True)

# Bind per-request/task context. These values will be merged into every event.
structlog.contextvars.bind_contextvars(request_id="abc123", user_id="u42")

# Simple event (will include request_id and user_id in the JSON body)
logger.info("hello")

# Positional formatting compatibility (rendered by PositionalArgumentsFormatter)
logger.info("user %s performed %s", "u42", "login")

# Exception and stack rendering
try:
    1 / 0
except ZeroDivisionError:
    logger.error("division failed", exc_info=True, stack_info=True)  