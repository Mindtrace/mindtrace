import queue


class LocalQueue:
    def __init__(self):
        self.queue = queue.Queue()

    def push(self, item):
        self.queue.put(item)

    def pop(self, block=True, timeout=None):
        return self.queue.get(block=block, timeout=timeout)

    def qsize(self):
        return self.queue.qsize()

    def empty(self):
        return self.queue.empty()

    def clean(self):
        count = 0
        while not self.queue.empty():
            self.queue.get_nowait()
            count += 1
        return count