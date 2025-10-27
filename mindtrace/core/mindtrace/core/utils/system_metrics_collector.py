import threading

import psutil


class SystemMetricsCollector:
    """Class for collecting various system metrics.

    This class allows the collection of system metrics like CPU usage, memory usage, disk usage, network I/O, etc.
    Users can specify which metrics to collect and whether to collect metrics periodically.

    Available metrics include:
        - "cpu_percent": Overall CPU usage percentage.
        - "per_core_cpu_percent": CPU usage percentage per core.
        - "memory_percent": Memory usage percentage.
        - "disk_usage": Disk usage percentage.
        - "network_io": Network I/O statistics (bytes sent and received).
        - "load_average": System load average (if available).

    Example Usage::

        from time import sleep
        from mindtrace.core.utils import SystemMetricsCollector

        # Collect All Metrics (default behavior)
        metrics_collector = SystemMetricsCollector()
        metrics = metrics_collector()  # Equivalent to metrics_collector.fetch()

        # Collect Specific Metrics Only
        metrics_to_collect = ["cpu_percent", "memory_percent", "network_io"]
        metrics_collector = SystemMetricsCollector(metrics_to_collect=metrics_to_collect)
        metrics = metrics_collector()

        # Get Metrics on Demand
        for _ in range(3):
            current_metrics = metrics_collector()
            print(current_metrics)

        # Set Interval for Periodic Metrics Collection
        metrics_collector = SystemMetricsCollector(interval=5)  # Will only update metrics every 5 seconds
        for _ in range(15):
            current_metrics = metrics_collector()
            print(current_metrics)
            sleep(1)
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
        """Stop the automatic metrics collection background thread.

        If using a set interval to automatically refresh metrics, it is important to close the background thread when
        you are finished with it. I.e.

            Manually closing the thread::

                import time
                from mindtrace.core.utils import SystemMetricsCollector

                system_metrics = SystemMetricsCollector(interval=3)
                with _ in range(10):
                   print(system_metrics())
                   time.sleep(1)

                $ Manually stop the background thread
                system_metrics.stop()

        The recommended solution is to do the same automatically through using the collector as a context manager:

            Using a context manager::

                import time
                from mindtrace.core.utils import SystemMetricsCollector

                i = 0
                with SystemMetricsCollector(interval=3) as system_metrics:
                    print(system_metrics())
                    i += 1
                    if i > 10:
                        break
                    time.sleep(1)
        """
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
