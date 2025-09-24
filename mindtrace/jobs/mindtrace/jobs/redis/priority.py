import pickle
from queue import Empty

import redis


class RedisPriorityQueue:
    """A priority message queue backed by Redis.
    This class uses a Redis sorted set to store messages with priorities.
    Higher numerical priority values are retrieved first (higher priority).
    """

    def __init__(self, name, namespace="priority_queue", **redis_kwargs):
        self.__db = redis.Redis(**redis_kwargs)
        self.key = f"{namespace}:{name}"

    def push(self, item, priority=0):
        """Serialize and add an item to the priority queue.
        Args:
            item: The item to add to the queue.
            priority: Priority value (higher numbers = higher priority).
        """
        import random

        random.seed(hash(str(item)) % 2147483647)  # Deterministic seed based on item content
        tie_breaker = random.random() * 1e-10  # Very small tie breaker
        score = priority + tie_breaker
        self.__db.zadd(self.key, {pickle.dumps(item): score})

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
                    return pickle.loads(items[0][0])
                if timeout is not None and (time.time() - start_time) > timeout:
                    raise Empty
                time.sleep(0.1)  # Sleep briefly before checking again
        else:
            items = self.__db.zpopmax(self.key, 1)
            if items:
                return pickle.loads(items[0][0])
            else:
                raise Empty

    def qsize(self):
        """Return the approximate size of the priority queue."""
        return self.__db.zcard(self.key)

    def empty(self):
        """Return True if the priority queue is empty, False otherwise."""
        return self.qsize() == 0
