from enum import StrEnum


class ConsumerFailurePolicy(StrEnum):
    """Action to take when a consumer fails to process a message."""

    DEAD_LETTER = "dead_letter"
    REQUEUE = "requeue"  # RabbitMQ only: retry once, then dead-letter.
    DISCARD = "discard"
