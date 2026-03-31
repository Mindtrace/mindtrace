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

    def to_dict(self):
        """Convert queue contents to a JSON-serializable dictionary."""
        items = []
        # Create a temporary queue to preserve order
        temp_queue = queue.Queue()

        # Extract all items from the original queue
        while not self.queue.empty():
            item = self.queue.get()
            items.append(item)
            temp_queue.put(item)

        # Restore the original queue
        while not temp_queue.empty():
            self.queue.put(temp_queue.get())

        return {"items": items}

    @classmethod
    def from_dict(cls, data):
        """Create a LocalQueue from a dictionary."""
        queue_obj = cls()
        for item in data.get("items", []):
            queue_obj.push(item)
        return queue_obj
