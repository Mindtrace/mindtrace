from typing import Callable


def named_lambda(name: str, lambda_func: Callable) -> Callable:
    """Assigns a name to the given lambda function.

    This method is useful when passing lambda functions to other functions that require a name attribute. For example,
    when using the autolog decorator, the wrapped function will be logged according the function name. If the original
    function is a lambda function, it's name attribute will be set to the generic name '<lambda>'.

    Args:
        name: The name to assign to the lambda function.
        lambda_func: The lambda function to assign the name to.

    Returns:
        The lambda function with the name attribute set to the given name.

    Example::

            from mindtrace.core import Mindtrace, named_lambda

            class HyperRunner(Mindtrace):
                def __init__(self):
                    super().__init__()

                def run_command(self, command: Callable, data: Any):  # cannot control the name of the command
                    return Mindtrace.autolog(command(data))()

            hyper_runner = HyperRunner()
            hyper_runner.run_command(lambda x, y: x + y, data=(1, 2))  # autologs to '<lambda>'
            hyper_runner.run_command(named_lambda("add", lambda x, y: x + y), data=(1, 2))  # autologs to 'add'

    """
    lambda_func.__name__ = name
    return lambda_func
