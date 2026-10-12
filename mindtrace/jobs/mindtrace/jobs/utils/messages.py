import json


class InvalidMessageError(ValueError):
    """Raised when a delivery body cannot be decoded as a JSON object."""


def decode_message(body: str | bytes) -> dict:
    """Decode a job body, reserving ``None`` for an empty queue.

    Args:
        body: JSON text or UTF-8 encoded bytes from a delivery.

    Returns:
        The decoded job dictionary.

    Raises:
        InvalidMessageError: If the body is not valid UTF-8 JSON or is not an object.
    """
    try:
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        message = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidMessageError(f"Invalid job body: {exc}") from exc
    if not isinstance(message, dict):
        raise InvalidMessageError(f"Expected a JSON object, received {type(message).__name__}.")
    return message
