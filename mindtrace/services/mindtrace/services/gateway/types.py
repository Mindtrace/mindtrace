from pydantic import BaseModel

from mindtrace.core import TaskSchema


class AppConfig(BaseModel):
    name: str
    url: str


class RegisterAppTaskSchema(TaskSchema):
    name: str = "register_app"
    input_schema: type[AppConfig] = AppConfig
