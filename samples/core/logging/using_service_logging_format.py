from mindtrace.core.base.mindtrace_base import Mindtrace
from mindtrace.services.logging.logger import ServiceLogMixin

class MindtraceService(Mindtrace, ServiceLogMixin):
    def __init__(self):
        super().__init__()
        self.logger = self.setup_struct_logger(service_name="my_service")

    def run(self):
        self.logger.info("Service started", component="my_service")




service_obj = MindtraceService()
service_obj.run()