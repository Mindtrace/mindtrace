import logging

from mindtrace.core import ContextListener, ObservableContext


@ObservableContext(vars={"gpu_utilization": float, "failed_login_attempts": int})
class InferenceService:
    def __init__(self):
        self.gpu_utilization = 0.0
        self.failed_login_attempts = 0

    def failed_login(self):
        self.failed_login_attempts += 1

    def use_more_gpu(self):
        self.gpu_utilization += 0.1


class SecurityMonitor(ContextListener):
    def failed_login_attempts_changed(self, source, old, new):
        if new >= 3:
            self.logger.warning(f"[SECURITY] {source} too many failed logins: {new}. Alert sent.")


svc = InferenceService()
svc.subscribe(ContextListener(autolog=["failed_login_attempts", "gpu_utilization"], log_level=logging.WARNING))
svc.subscribe(SecurityMonitor())

for i in range(3):
    svc.failed_login()
    svc.use_more_gpu()


# Output:
# [InferenceService] failed_login_attempts changed: 0 → 1
# [InferenceService] gpu_utilization changed: 0.0 → 0.1
# [InferenceService] failed_login_attempts changed: 1 → 2
# [InferenceService] gpu_utilization changed: 0.1 → 0.2
# [InferenceService] failed_login_attempts changed: 2 → 3
# [SECURITY] InferenceService too many failed logins: 3. Alert sent.
# [InferenceService] gpu_utilization changed: 0.2 → 0.3
