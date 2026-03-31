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

    def to_dict(self):
        """Convert stack contents to a JSON-serializable dictionary."""
        items = []
        while not self.stack.empty():
            item = self.stack.get()
            items.append(item)

        lifo_items = items  # items are already in LIFO order from popping
        for item in reversed(items):
            self.stack.put(item)

        return {"items": lifo_items}

    @classmethod
    def from_dict(cls, data):
        """Create a LocalStack from a dictionary."""
        stack_obj = cls()
        for item in reversed(data.get("items", [])):
            stack_obj.push(item)
        return stack_obj
