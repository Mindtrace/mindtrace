from mindtrace.core import EchoInput, echo_task
from mindtrace.jobs import Orchestrator

orchestrator = Orchestrator()
orchestrator.register(echo_task)

job_id = orchestrator.publish("echo", EchoInput(message="Hello, world!"))

print(orchestrator.backend.receive_message("echo"))
