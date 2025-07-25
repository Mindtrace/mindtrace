from pydantic import BaseModel
from urllib3.util.url import Url

from mindtrace.core import TaskSchema


class AppConfig(BaseModel):
    name: str
    url: str | Url


class RegisterAppTaskSchema(TaskSchema):
    name: str = "register_app"
    input_schema: type[AppConfig] = AppConfig
