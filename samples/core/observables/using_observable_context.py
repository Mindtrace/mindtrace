from mindtrace.core import ObservableContext


@ObservableContext(vars={"gpu_utilization": float, "failed_login_attempts": int})
class InferenceService:
    def __init__(self):
        self.gpu_utilization = 0.0
        self.failed_login_attempts = 0

    def failed_login(self):
        self.failed_login_attempts += 1

    def use_more_gpu(self):
        self.gpu_utilization += 0.25

class Logger:
    # May use `context_updated` to handle all events, or use specific event handlers
    def context_updated(self, source, var, old, new):
        if var == "failed_login_attempts":
            print(f"[CLASS LOGGER]\t{source} {var} changed from {old} to {new}")

class SecurityMonitor:
    # May use `{var}_changed` to handle specific events
    def failed_login_attempts_changed(self, source, old, new):
        if new >= 3:
            print(f"[SECURITY]\t{source} too many failed logins: {new}. Alert sent.")

def log_change(source, var, old, new):
    if var == "gpu_utilization":
        print(f"[FUNC LOGGER]\t{source} {var} changed from {old} to {new}")

def resource_alert(source, old, new):
    if new >= 0.7:
        print(f"[RESOURCE]\tWarning: {source} GPU usage high: {new*100:.1f}%")


# Initialize the service and add listeners
svc = InferenceService()
svc.add_listener(SecurityMonitor())  # Use `add_listener` for class-based listeners
svc.add_listener(Logger())
svc.subscribe("context_updated", log_change)  # Use `subscribe` for function-based listeners
svc.subscribe("gpu_utilization_changed", resource_alert)  

# Simulate some activity
for i in range(3):
    svc.failed_login()
    svc.use_more_gpu()


# Output:
# [CLASS LOGGER]    InferenceService failed_login_attempts changed from 0 to 1
# [FUNC LOGGER]     InferenceService gpu_utilization changed from 0.0 to 0.25
# [CLASS LOGGER]    InferenceService failed_login_attempts changed from 1 to 2
# [FUNC LOGGER]     InferenceService gpu_utilization changed from 0.25 to 0.5
# [CLASS LOGGER]    InferenceService failed_login_attempts changed from 2 to 3
# [SECURITY]        InferenceService too many failed logins: 3. Alert sent.
# [FUNC LOGGER]     InferenceService gpu_utilization changed from 0.5 to 0.75
# [RESOURCE]        Warning: InferenceService GPU usage high: 75.0%
