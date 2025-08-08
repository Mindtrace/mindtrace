from pydantic import BaseModel
from urllib3.util.url import Url

from mindtrace.core import TaskSchema


class AppConfig(BaseModel):
    name: str
    url: str | Url


RegisterAppTaskSchema = TaskSchema(name="register_app", input_schema=AppConfig)
