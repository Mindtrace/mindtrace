import pickle
from queue import Empty

import redis


class RedisStack:
    """A LIFO (last-in, first-out) message stack backed by Redis.
    This class uses a Redis list to store serialized messages. The `push` method pushes items to the head of the list,
    while the `pop` method pops from the head. Blocking retrieval is implemented using Redis' BLPOP command.
    """

    def __init__(self, name, namespace="stack", **redis_kwargs):
        self.__db = redis.Redis(**redis_kwargs)
        self.key = f"{namespace}:{name}"

    def push(self, item):
        """Serialize and add an item to the stack."""
        self.__db.lpush(self.key, pickle.dumps(item))

    def pop(self, block=True, timeout=None):
        """Remove and return the top item from the stack.
        Args:
            block: If True, block until an item is available.
            timeout: Maximum time to block in seconds (if block=True).
        Raises:
             queue.Empty: If no item is available (non-blocking or timeout reached).
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
        """Return the approximate size of the stack."""
        return self.__db.llen(self.key)

    def empty(self):
        """Return True if the stack is empty, False otherwise."""
        return self.qsize() == 0
