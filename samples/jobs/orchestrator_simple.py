from mindtrace.core import EchoInput, echo_task
from mindtrace.jobs import LocalClient, Orchestrator, job_from_schema

backend = LocalClient()
orchestrator = Orchestrator(backend)
orchestrator.register(echo_task)

job_id = orchestrator.publish("echo", job_from_schema(echo_task, EchoInput(message="Hello, world!")))

print(orchestrator.backend.queues["echo"].pop())
