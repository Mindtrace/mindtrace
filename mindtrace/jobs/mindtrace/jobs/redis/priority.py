import uuid
from queue import Empty

import redis


class RedisPriorityQueue:
    """A priority message queue backed by Redis.
    This class uses a Redis sorted set to store messages with priorities.
    Higher numerical priority values are retrieved first (higher priority).

    Each member is a unique hexadecimal entry prefix, a colon, and the payload, so identical
    payloads occupy distinct members of the sorted set.
    """

    def __init__(self, name, namespace="priority_queue", **redis_kwargs):
        self.__db = redis.Redis(**redis_kwargs)
        self.key = f"{namespace}:{name}"

    def push(self, item: str, priority=0):
        """Add an item to the priority queue under its own entry prefix.
        Args:
            item: The payload to add to the queue.
            priority: Priority value (higher numbers = higher priority).
        """
        self.__db.zadd(self.key, {f"{uuid.uuid4().hex}:{item}": priority})

    @staticmethod
    def _decode(member) -> str:
        """Return the payload carried by a stored member."""
        if isinstance(member, bytes):
            member = member.decode("utf-8")
        _, separator, payload = member.partition(":")
        if not separator:
            raise ValueError(f"Priority queue member is missing its entry prefix: {member!r}")
        return payload

    def pop(self, block=True, timeout=None):
        """Remove and return the highest priority item from the queue.
        Args:
            block: If True, block until an item is available.
            timeout: Maximum time to block in seconds (if block=True).
        Raises:
            queue.Empty: If no item is available (in non-blocking mode or if the timeout expires).
        """
        if block:
            import time

            start_time = time.time()
            while True:
                items = self.__db.zpopmax(self.key, 1)
                if items:
                    return self._decode(items[0][0])
                if timeout is not None and (time.time() - start_time) > timeout:
                    raise Empty
                time.sleep(0.1)  # Sleep briefly before checking again
        else:
            items = self.__db.zpopmax(self.key, 1)
            if items:
                return self._decode(items[0][0])
            else:
                raise Empty

    def qsize(self):
        """Return the approximate size of the priority queue."""
        return self.__db.zcard(self.key)

    def empty(self):
        """Return True if the priority queue is empty, False otherwise."""
        return self.qsize() == 0
