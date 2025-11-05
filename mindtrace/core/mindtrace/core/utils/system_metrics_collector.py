import threading

import psutil


class SystemMetricsCollector:
    """Class for collecting various system metrics.

    This class allows collection of CPU, memory, disk usage, network I/O, etc. Users can
    specify which metrics to collect and optionally enable periodic background updates.

    Available metrics include:
        - "cpu_percent": Overall CPU usage percentage.
        - "per_core_cpu_percent": CPU usage percentage per core.
        - "memory_percent": Memory usage percentage.
        - "disk_usage": Disk usage percentage.
        - "network_io": Network I/O statistics (bytes sent and received).
        - "load_average": System load average (if available).

    Example Usage:

        from time import sleep
        from mindtrace.core.utils import SystemMetricsCollector

        with SystemMetricsCollector(interval=3) as collector:
            for _ in range(10):
                print(collector())
                sleep(1)

    Alternative (manual stop):

        from time import sleep
        from mindtrace.core.utils import SystemMetricsCollector

        collector = SystemMetricsCollector(interval=3)
        try:
            for _ in range(10):
                print(collector())
                sleep(1)
        finally:
            collector.stop()

    On-demand usage (no background thread):

        from mindtrace.core.utils import SystemMetricsCollector

        collector = SystemMetricsCollector()  # no interval; collected on demand
        print(collector())
    """

    AVAILABLE_METRICS = {
        "cpu_percent": lambda: psutil.cpu_percent(),
        "per_core_cpu_percent": lambda: psutil.cpu_percent(percpu=True),
        "memory_percent": lambda: psutil.virtual_memory().percent,
        "disk_usage": lambda: psutil.disk_usage("/").percent,
        "network_io": lambda: {
            "bytes_sent": psutil.net_io_counters().bytes_sent,
            "bytes_recv": psutil.net_io_counters().bytes_recv,
        },
        "load_average": lambda: psutil.getloadavg() if hasattr(psutil, "getloadavg") else None,
    }

    def __init__(self, interval: int | None = None, metrics_to_collect: list[str] | None = None):
        """
        Initialize the system metrics collector.

        Args:
            interval: Interval in seconds for periodic metrics collection. If provided, metrics will be updated
                to a separate cache periodically, instead of being collected on demand. Using a cache in this way can
                be less resource intensive than collecting metrics on demand. If None, metrics will be collected on
                demand.
            metrics_to_collect: List of metrics to collect. If None, all available metrics will be collected.
        """
        self.interval = interval
        self.metrics_cache: dict[str, float | list | dict] | None = None
        self._event: threading.Event | None = None

        if metrics_to_collect is None:
            self.metrics_to_collect = self.AVAILABLE_METRICS.keys()
        else:
            invalid_metrics = [metric for metric in metrics_to_collect if metric not in self.AVAILABLE_METRICS]
            if invalid_metrics:
                raise ValueError(f"Unknown metrics specified: {', '.join(invalid_metrics)}")
            self.metrics_to_collect = metrics_to_collect

        if self.interval:
            self._thread = threading.Thread(target=self._start_periodic_metrics_collection, daemon=True)
            self._thread.start()

    def __call__(self):
        return self.fetch()

    def fetch(self) -> dict[str, float | list | dict]:
        """Get the current system metrics.

        Returns:
            A dictionary containing system metrics. If metrics are cached, return them; otherwise, collect new metrics.
        """
        return self.metrics_cache if self.metrics_cache else self._collect_metrics()

    def stop(self):
        """Stop the background collection thread if running.

        Prefer using the context manager (`with SystemMetricsCollector(...) as collector:`)
        which stops the thread automatically on exit.
        """
        if self._event is not None:
            self._event.set()

    def _collect_metrics(self) -> dict[str, float | list | dict]:
        """Collect the specified system metrics.

        Returns:
            A dictionary containing system metrics.
        """
        return {metric: self.AVAILABLE_METRICS[metric]() for metric in self.metrics_to_collect}

    def _update_metrics(self) -> None:
        """Update the metrics cache with the latest system metrics."""
        self.metrics_cache = self._collect_metrics()

    def _start_periodic_metrics_collection(self) -> None:
        """Start periodic system metrics collection."""
        self._event = threading.Event()
        while not self._event.is_set():
            self._update_metrics()
            self._event.wait(self.interval)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
