import queue


class LocalPriorityQueue:
    def __init__(self):
        self.priority_queue = queue.PriorityQueue()
    def push(self, item, priority: int = 0):
        inverted_priority = -priority
        self.priority_queue.put((inverted_priority, item))
    def pop(self, block=True, timeout=None):
        neg_priority, item = self.priority_queue.get(block=block, timeout=timeout)
        return item
    def qsize(self):
        return self.priority_queue.qsize()
    def empty(self):
        return self.priority_queue.empty()
    def clean(self):
        count = 0
        while not self.priority_queue.empty():
            self.priority_queue.get_nowait()
            count += 1
        return count
