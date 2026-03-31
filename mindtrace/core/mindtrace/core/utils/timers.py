"""Utility class for simple Timer and TimerCollection classes."""

import time
from typing import Dict, Optional, Type

from tqdm import tqdm


class Timer:
    """Utility timer class.

    This class can be used to time operations. It can be started, stopped, and reset. The duration of the timer can be
    retrieved at any time.

    Usage:
        ```python
        import time
        from mindtrace.core import Timer

        timer = Timer()
        timer.start()
        time.sleep(1)
        timer.stop()
        print(f'The timer ran for {timer.duration()} seconds.')  # The timer ran for 1.0000000000000002 seconds.
        timer.reset()
        timer.start()
        time.sleep(2)
        timer.stop()
        print(f'The timer ran for {timer.duration()} seconds.')  # The timer ran for 2.0000000000000004 seconds.
        ```

    """

    def __init__(self):
        self._start_time: Optional[float] = None
        self._stop_time: Optional[float] = None
        self._duration: float = 0.0

    def start(self):
        """Start the timer."""
        self._start_time = time.perf_counter()
        self._stop_time = None

    def stop(self):
        """Stop the timer."""
        if self._start_time is None:
            raise ValueError("Timer has not been started.")
        if self._stop_time is None:
            self._stop_time = time.perf_counter()
            self._duration += self._stop_time - self._start_time

    def duration(self) -> float:
        """Get the duration of the timer."""
        if self._start_time is not None and self._stop_time is None:
            return self._duration + (time.perf_counter() - self._start_time)
        else:
            return self._duration

    def reset(self):
        """Reset the timer."""
        self._start_time = None
        self._stop_time = None
        self._duration = 0.0

    def restart(self):
        """Reset and start the timer."""
        self.reset()
        self.start()

    def __enter__(self):
        """Enter the context manager."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager and stop the timer."""
        self.stop()
        return False  # Don't suppress exceptions

    def __str__(self):
        return f"{self.duration():.3f}s"


class TimerContext:
    """Context manager for individual timers in a TimerCollection."""

    def __init__(self, timer_collection: "TimerCollection", name: str):
        self.timer_collection = timer_collection
        self.name = name

    def __enter__(self):
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager and stop the specific timer."""
        self.timer_collection.stop(self.name)
        return False  # Don't suppress exceptions


class TimerCollection:
    """Utility class for timing multiple operations.

    This class keeps a collection of named timers. Each timer can be started, stopped, and reset. The duration of each
    timer can be retrieved at any time. If a timer is stopped and restarted, the duration will be added to the previous
    duration. The timers can be reset individually, or all at once.

    Usage:
        ```python
        import time
        from mindtrace.core import TimerCollection

        tc = TimerCollection()
        tc.start('Timer 1')
        tc.start('Timer 2')
        time.sleep(1)
        tc.stop('Timer 1')
        time.sleep(1)
        tc.stop('Timer 2')
        tc.start('Timer 3')
        time.sleep(1)
        tc.reset('Timer 1')
        print(tc)
            # Timer 1: 0.000s
            # Timer 2: 2.000s
            # Timer 3: 1.000s
        tc.reset_all()
        print(tc)
            # Timer 1: 0.000s
            # Timer 2: 0.000s
            # Timer 3: 0.000s
        ```
    Context Manager Usage:
        ```python
        import time
        from mindtrace.core import TimerCollection

        tc = TimerCollection()
        with tc.start('Timer 1'):
            with tc.start('Timer 2'):
                time.sleep(1)
            # stops "Timer 2"
            with tc.start('Timer 3'):
                time.sleep(2)
            # stops "Timer 3"
        # stops "Timer 1"

        print(tc)
            # Timer 1: 3.000s
            # Timer 2: 1.000s
            # Timer 3: 2.000s
        ```

    """

    def __init__(self):
        self._timers: Dict[str, Timer] = {}

    def add_timer(self, name: str):
        """Add a timer with the given name. If the timer already exists, it will be replaced."""
        self._timers[name] = Timer()

    def start(self, name: str):
        """Start the timer with the given name. If the timer does not exist, it will be created."""
        if name not in self._timers:
            self.add_timer(name)
        self._timers[name].start()
        return TimerContext(self, name)

    def stop(self, name: str):
        """Stop the timer with the given name.

        Raises:
            KeyError: If the timer with the given name does not exist.
        """
        if name not in self._timers:
            raise KeyError(f"Timer {name} does not exist. Unable to stop.")
        self._timers[name].stop()

    def duration(self, name: str) -> float:
        """Get the duration of the timer with the given name.

        Raises:
            KeyError: If the timer with the given name does not exist.
        """
        if name not in self._timers:
            raise KeyError(f"Timer {name} does not exist. Unable to get duration.")
        return self._timers[name].duration()

    def reset(self, name: str):
        """Reset the timer with the given name.

        Raises:
            KeyError: If the timer with the given name does not exist.
        """
        if name not in self._timers:
            raise KeyError(f"Timer {name} does not exist. Unable to reset.")
        self._timers[name].reset()

    def restart(self, name: str):
        """Reset and start the timer with the given name.

        Raises:
            KeyError: If the timer with the given name does not exist.
        """
        if name not in self._timers:
            raise KeyError(f"Timer {name} does not exist. Unable to restart.")
        self._timers[name].restart()

    def reset_all(self):
        """Reset all timers."""
        for timer in self._timers.values():
            timer.reset()

    def names(self):
        """Get the names of all timers."""
        return self._timers.keys()

    def __str__(self):
        """Print each timer to the nearest microsecond."""
        return "\n".join([f"{name}: {timer.duration():.6f}s" for name, timer in self._timers.items()])


class Timeout:
    """Utility for adding a timeout to a given method.

    The given method will be run and rerun until an exception is not raised, or the timeout period is reached.

    If the method raises an exception that is in the exceptions tuple, that exception will be caught and ignored. After
    a retry_delay, the method will be run again. This process will continue until the method runs without raising an
    exception, or the timeout period is passed.

    If the timeout is reached, a TimeoutError will be raised. If the method ever raises an exception that is not in the
    exceptions tuple, the timeout process will stop and that exception will be reraised.

    Args:
        timeout: The maximum time in seconds that the method can run before a TimeoutError is raised.
        retry_delay: The time in seconds to wait between attempts to run the method.
        exceptions: A tuple of exceptions that will be caught and ignored. By default, all exceptions are caught.
        progress_bar: A boolean indicating whether to display a progress bar while waiting for the timeout.
        desc: A description to display in the progress bar.

    Returns:
        The result of the given method.

    Raises:
        TimeoutError: If the timeout is reached.
        Exception: Any raised exception not in the exceptions tuple will be reraised.

    Example— Running Timeout Manually:
        ```python
        import requests
        from urllib3.util.url import parse_url, Url
        from mindtrace.core import Timeout
        from mindtrace.services import Service

        def get_server_status(url: Url):
            # The following request may fail for two categories of reasons:
            #   1. The server has not launched yet: Will raise a ConnectionError, we should retry.
            #   2. Any other reason: Will raise some other exception, we should break out and reraise it.
            # Both cases will be raised to the Timeout class. We will tell the Timeout object to ignore ConnectionError.
            response = requests.request("POST", str(url) + "status")

            if response.status_code == 200:
                return json.loads(response.content)["status"]  # Server is up and responding
            else:
                raise HTTPException(response.status_code, response.content)  # Request completed but something is wrong

        url = parse_url("http://localhost:8080/")
        timeout = Timeout(timeout=60.0, exceptions=(ConnectionRefusedError, requests.exceptions.ConnectionError))

        Service.launch(url)
        status = timeout.run(get_server_status, url)  # Will wait up to 60 seconds for the server to launch.
        print(f"Server status: {status}")
        ```


    Example— Using Timeout as a Decorator:
        ```python

        import requests
        from urllib3.util.url import parse_url, Url
        from mindtrace.core import Timeout
        from mindtrace.services import Service

        @Timeout(timeout=60.0, exceptions=(ConnectionRefusedError, requests.exceptions.ConnectionError))
        def get_server_status(url: Url):
            response = requests.request("POST", str(url) + "status")
            if response.status_code == 200:
                return json.loads(response.content)["status"]
            else:
                raise HTTPException(response.status_code, response.content)

        url = parse_url("http://localhost:8080/")
        Service.launch(url)

        try:
            status = get_server_status(url)  # Will wait up to 60 seconds for the server to launch.
        except TimeoutError as e:
            print(f"The server did not respond within the timeout period: {e}")  # Timeout of 60 seconds reached.
        except Exception as e:  # Guaranteed not to be one of the given exceptions in the exceptions tuple.
            print(f"An unexpected error occurred: {e}")
        else:
            print(f"Server status: {status}")
        ```

    """

    def __init__(
        self,
        timeout: float = 60.0,
        retry_delay: float = 1.0,
        exceptions: tuple[Type[Exception], ...] = (Exception,),
        progress_bar: bool = False,
        desc: str | None = None,
    ):
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.exceptions = exceptions
        self.progress_bar = progress_bar
        self.desc = desc

    def _wrapper(self, func, *args, **kwargs):
        _progress_bar = tqdm(total=self.timeout, desc=self.desc, leave=False) if self.progress_bar else None
        start_time = time.perf_counter()
        while True:
            if _progress_bar:
                _progress_bar.update()
            try:
                result = func(*args, **kwargs)
            except self.exceptions as e:  # ignore exception and try again after retry_delay
                if time.perf_counter() - start_time > self.timeout:
                    raise TimeoutError(f"Timeout of {self.timeout} seconds reached.") from e
                time.sleep(self.retry_delay)
            except Exception as e:  # reraise exception
                if _progress_bar:
                    _progress_bar.close()
                raise e
            else:
                if _progress_bar:
                    _progress_bar.close()
                return result

    def __call__(self, func):
        """Wrap the given function. This method allows the Timeout class to be used as a decorator."""
        return lambda *args, **kwargs: self._wrapper(func, *args, **kwargs)

    def run(self, func, *args, **kwargs):
        """Run the given function with the given args and kwargs."""
        return self._wrapper(func, *args, **kwargs)
