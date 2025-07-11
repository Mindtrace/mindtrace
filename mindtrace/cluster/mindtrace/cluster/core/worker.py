from mindtrace.jobs import Consumer
from mindtrace.services import Service
from mindtrace.core import TaskSchema
from mindtrace.cluster.core.types import WorkerRunTaskSchema, ConnectToBackendTaskSchema
import multiprocessing

class Worker(Service, Consumer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_endpoint("/start", self.start, schema=TaskSchema(name="start_worker"))
        self.add_endpoint("/run", self.run, schema=WorkerRunTaskSchema)
        self.add_endpoint("/connect_to_backend", self.connect_to_backend, schema=ConnectToBackendTaskSchema)
        self.consume_process = None

    def start(self):
        pass

    def connect_to_backend(self, payload: dict):
        backend_args = payload["backend_args"]
        queue_name = payload["queue_name"]
        self.start()
        self.connect_to_orchestator_via_backend_args(backend_args, queue_name=queue_name)
        self.consume_process = multiprocessing.Process(target=self.consume)
        self.consume_process.start()
        
    def shutdown(self):
        if self.consume_process is not None:
            self.consume_process.kill()
        super().shutdown() 


