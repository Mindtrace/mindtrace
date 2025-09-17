import pickle
from queue import Empty

import redis


class RedisQueue:
    """A FIFO (first-in, first-out) message queue backed by Redis.
    This class uses a Redis list to store serialized messages. The `put` method pushes items to the tail of the list,
    while the `get` method pops from the head. Blocking retrieval is implemented using Redis' BLPOP command.
    """

    def __init__(self, name, namespace="queue", **redis_kwargs):
        """Initialize a RedisQueue object.
        Args:
            name: Name of the queue.
            namespace: Namespace prefix for the Redis key.
            redis_kwargs: Additional keyword arguments for redis.Redis.
        """
        self.__db = redis.Redis(**redis_kwargs)
        self.key = f"{namespace}:{name}"

    def push(self, item):
        """Serialize and add an item to the queue."""
        self.__db.rpush(self.key, pickle.dumps(item))

    def pop(self, block=True, timeout=None):
        """Remove and return an item from the queue.
        Args:
            block: If True, block until an item is available.
            timeout: Maximum time to block in seconds (if block=True).
        Raises:
            queue.Empty: If no item is available (in non-blocking mode or if the timeout expires).
        """
        if block:
            item = self.__db.blpop(self.key, timeout=timeout)
            if item:
                return pickle.loads(item[1])
            else:
                raise Empty
        else:
            item = self.__db.lpop(self.key)
            if item:
                return pickle.loads(item)
            else:
                raise Empty

    def qsize(self):
        """Return the approximate size of the queue."""
        return self.__db.llen(self.key)

    def empty(self):
        """Return True if the queue is empty, False otherwise."""
        return self.qsize() == 0
