import logging


def Logger(name: str = "Mindtrace"):
    """Template logger "class"."""
    return logging.getLogger(name)
