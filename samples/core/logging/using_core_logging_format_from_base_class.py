from mindtrace.core import Mindtrace


class MyClass(Mindtrace):
    def __init__(self):
        super().__init__()

    def instance_method(self):
        self.logger.info(
            f"Find this log in `.cache/mindtrace/mindtrace.log`. Using instance logger: {self.logger.name}"
        )  # Using logger: mindtrace.my_module.MyClass

    @classmethod
    def class_method(cls):
        cls.logger.info(
            f"Find this log in `.cache/mindtrace/mindtrace.log`. Using cls logger: {cls.logger.name}"
        )  # Using logger: mindtrace.my_module.MyClass


if __name__ == "__main__":
    cls_instance = MyClass()
    cls_instance.instance_method()
    cls_instance.class_method()
