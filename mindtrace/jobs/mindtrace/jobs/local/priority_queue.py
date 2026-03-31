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

    def to_dict(self):
        """Convert priority queue contents to a JSON-serializable dictionary."""
        items = []
        # Create a temporary queue to preserve order
        temp_queue = queue.PriorityQueue()

        # Extract all items from the original queue
        while not self.priority_queue.empty():
            neg_priority, item = self.priority_queue.get()
            # Convert back to original priority
            priority = -neg_priority
            items.append({"item": item, "priority": priority})
            temp_queue.put((neg_priority, item))

        # Restore the original queue
        while not temp_queue.empty():
            self.priority_queue.put(temp_queue.get())

        return {"items": items}

    @classmethod
    def from_dict(cls, data):
        """Create a LocalPriorityQueue from a dictionary."""
        queue_obj = cls()
        for item_data in data.get("items", []):
            item = item_data["item"]
            priority = item_data["priority"]
            queue_obj.push(item, priority)
        return queue_obj
