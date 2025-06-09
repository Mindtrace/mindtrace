"""
Default logging configuration for the Mindtrace logging system.

This configuration defines a dictionary compatible with Python's
``logging.config.dictConfig`` format. It sets up two primary handlers:
a console handler for displaying error messages and a rotating file handler
for writing debug-level logs to disk. The formatters ensure logs are timestamped
and follow a standard layout for clarity.

This file is typically imported by logging setup utilities to initialize
consistent logging across services and jobs.

Logging Structure:
------------------
- Formatters:
    - **standard**: Format includes timestamp, log level, logger name, and message.

- Handlers:
    - **console**: Logs errors to standard output.
    - **file**: Logs all levels (DEBUG+) to a rotating log file (max 10MB, 5 backups).

- Root Logger:
    - Configured with both handlers and logging level set to DEBUG.
"""

default_logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "[%(asctime)s] %(levelname)s: %(name)s: %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "ERROR"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",  
            "formatter": "standard",
            "filename": None,  
            "level": "DEBUG",
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5
        }
    },
    "loggers": {
        "": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False
        }
    }
}