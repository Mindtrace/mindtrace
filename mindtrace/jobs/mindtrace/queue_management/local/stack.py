import queue


class LocalStack:
    def __init__(self):
        self.stack = queue.LifoQueue()

    def push(self, item):
        self.stack.put(item)

    def pop(self, block=True, timeout=None):
        return self.stack.get(block=block, timeout=timeout)

    def qsize(self):
        return self.stack.qsize()

    def empty(self):
        return self.stack.empty()

    def clean(self):
        count = 0
        while not self.stack.empty():
            self.stack.get_nowait()
            count += 1
        return count