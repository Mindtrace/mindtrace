import os

from mindtrace.core import Mindtrace
from mindtrace.core.config import Config

#### Accessing Config from Mindtrace

# When inheriting from the Mindtrace base class,
# config is automatically available as self.config / cls.config.

# Example:


class CustomComponent(Mindtrace):
    def show_config(self):
        print(self.config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)
        print(self.config.MINDTRACE_DIR_PATHS.TEMP_DIR)


# Usage
component = CustomComponent()
component.show_config()

#### Environment Variables Override Config

# Environment variables take precedence over config.ini defaults.
# Use the SECTION__KEY delimiter format.

# Step 1: Define environment variable
os.environ["MINDTRACE_DEFAULT_HOST_URLS__SERVICE"] = "http://env-service:8080"

# Step 2: Initialize Mindtrace — config picks up the env var
mt = Mindtrace()
print(mt.config.MINDTRACE_DEFAULT_HOST_URLS.SERVICE)  # http://env-service:8080

#### Class-level Config Access

# Config is also accessible at the class level without instantiation.
print(Mindtrace.config.MINDTRACE_DIR_PATHS.ROOT)

#### Retrieving Secrets

config = Config()
api_key = config.get_secret("MINDTRACE_API_KEYS", "OPENAI")
print(api_key)  # Real secret value (or None if not set)
