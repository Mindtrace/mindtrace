import threading
import time
from unittest.mock import Mock, patch

import pytest

from mindtrace.core.utils import SystemMetricsCollector


class TestSystemMetricsCollectorInitialization:
    """Test SystemMetricsCollector initialization."""

    def test_initialization_default(self):
        """Test default initialization."""
        collector = SystemMetricsCollector()
        
        assert collector.interval is None
        assert collector.metrics_cache is None
        assert collector._event is None
        assert set(collector.metrics_to_collect) == set(SystemMetricsCollector.AVAILABLE_METRICS.keys())

    def test_initialization_with_interval(self):
        """Test initialization with interval."""
        collector = SystemMetricsCollector(interval=1)
        
        # Give thread time to start
        time.sleep(0.1)
        
        assert collector.interval == 1
        assert collector._event is not None
        assert collector._thread.is_alive()
        
        collector.stop()
        time.sleep(0.1)  # Give thread time to stop

    def test_initialization_with_specific_metrics(self):
        """Test initialization with specific metrics."""
        metrics = ["cpu_percent", "memory_percent"]
        collector = SystemMetricsCollector(metrics_to_collect=metrics)
        
        assert collector.metrics_to_collect == metrics

    def test_initialization_with_invalid_metrics(self):
        """Test initialization with invalid metrics raises ValueError."""
        with pytest.raises(ValueError, match="Unknown metrics specified"):
            SystemMetricsCollector(metrics_to_collect=["invalid_metric", "another_invalid"])

    def test_initialization_with_mixed_valid_invalid_metrics(self):
        """Test initialization with mix of valid and invalid metrics."""
        with pytest.raises(ValueError, match="Unknown metrics specified: invalid_metric"):
            SystemMetricsCollector(metrics_to_collect=["cpu_percent", "invalid_metric"])


class TestSystemMetricsCollectorCollection:
    """Test SystemMetricsCollector metrics collection."""

    def test_on_demand_collection(self):
        """Test on-demand metrics collection without interval."""
        collector = SystemMetricsCollector()
        metrics = collector.fetch()
        
        # Should have all available metrics
        assert isinstance(metrics, dict)
        assert "cpu_percent" in metrics
        assert "memory_percent" in metrics
        assert "disk_usage" in metrics
        assert isinstance(metrics["cpu_percent"], (int, float))
        assert isinstance(metrics["memory_percent"], (int, float))

    def test_callable_interface(self):
        """Test that collector is callable."""
        collector = SystemMetricsCollector()
        metrics = collector()
        
        assert isinstance(metrics, dict)
        assert "cpu_percent" in metrics

    def test_specific_metrics_collection(self):
        """Test collection of specific metrics only."""
        metrics_list = ["cpu_percent", "memory_percent"]
        collector = SystemMetricsCollector(metrics_to_collect=metrics_list)
        metrics = collector.fetch()
        
        assert set(metrics.keys()) == set(metrics_list)
        assert "disk_usage" not in metrics
        assert "network_io" not in metrics

    def test_network_io_format(self):
        """Test network I/O metrics format."""
        collector = SystemMetricsCollector(metrics_to_collect=["network_io"])
        metrics = collector.fetch()
        
        assert "network_io" in metrics
        assert isinstance(metrics["network_io"], dict)
        assert "bytes_sent" in metrics["network_io"]
        assert "bytes_recv" in metrics["network_io"]

    def test_per_core_cpu_format(self):
        """Test per-core CPU metrics format."""
        collector = SystemMetricsCollector(metrics_to_collect=["per_core_cpu_percent"])
        metrics = collector.fetch()
        
        assert "per_core_cpu_percent" in metrics
        assert isinstance(metrics["per_core_cpu_percent"], list)
        assert len(metrics["per_core_cpu_percent"]) > 0


class TestSystemMetricsCollectorPeriodicCollection:
    """Test SystemMetricsCollector periodic collection."""

    def test_periodic_collection_updates_cache(self):
        """Test that periodic collection updates the cache."""
        collector = SystemMetricsCollector(interval=0.1, metrics_to_collect=["cpu_percent"])
        
        # Wait for first collection
        time.sleep(0.2)
        
        # Cache should be populated
        assert collector.metrics_cache is not None
        assert "cpu_percent" in collector.metrics_cache
        
        # Get cached value
        first_metrics = collector.fetch()
        
        # Fetch should return cached value (same object)
        assert collector.fetch() is first_metrics
        
        collector.stop()

    def test_periodic_collection_multiple_updates(self):
        """Test that periodic collection updates multiple times."""
        collector = SystemMetricsCollector(interval=0.1, metrics_to_collect=["cpu_percent"])
        
        # Wait for first collection
        time.sleep(0.15)
        first_cache = collector.metrics_cache
        
        # Wait for second collection
        time.sleep(0.15)
        second_cache = collector.metrics_cache
        
        # Caches should be different objects (new collection)
        assert first_cache is not second_cache
        
        collector.stop()

    def test_stop_terminates_thread(self):
        """Test that stop() terminates the background thread."""
        collector = SystemMetricsCollector(interval=0.1)
        
        # Give thread time to start
        time.sleep(0.05)
        assert collector._thread.is_alive()
        
        collector.stop()
        
        # Give thread time to stop
        time.sleep(0.2)
        assert not collector._thread.is_alive()


class TestSystemMetricsCollectorContextManager:
    """Test SystemMetricsCollector as context manager."""

    def test_context_manager_without_interval(self):
        """Test context manager without interval."""
        with SystemMetricsCollector() as collector:
            metrics = collector()
            assert isinstance(metrics, dict)
            assert "cpu_percent" in metrics

    def test_context_manager_with_interval(self):
        """Test context manager with interval."""
        with SystemMetricsCollector(interval=0.1) as collector:
            time.sleep(0.15)
            metrics = collector()
            assert isinstance(metrics, dict)
            assert collector.metrics_cache is not None
            
        # After exit, thread should be stopped
        time.sleep(0.2)
        assert not collector._thread.is_alive()

    def test_context_manager_stops_on_exception(self):
        """Test context manager stops thread even on exception."""
        collector = None
        try:
            with SystemMetricsCollector(interval=0.1) as collector:
                time.sleep(0.05)
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Thread should be stopped despite exception
        time.sleep(0.2)
        assert collector is not None
        assert not collector._thread.is_alive()


class TestSystemMetricsCollectorEdgeCases:
    """Test SystemMetricsCollector edge cases."""

    def test_stop_without_interval(self):
        """Test stop() on collector without interval doesn't raise error."""
        collector = SystemMetricsCollector()
        collector.stop()  # Should not raise

    def test_multiple_stop_calls(self):
        """Test multiple stop() calls don't cause issues."""
        collector = SystemMetricsCollector(interval=0.1)
        time.sleep(0.05)
        
        collector.stop()
        collector.stop()  # Second stop should not raise
        collector.stop()  # Third stop should not raise

    def test_fetch_before_first_collection(self):
        """Test fetch() before periodic collection has run."""
        collector = SystemMetricsCollector(interval=1)  # Long interval
        
        # Fetch immediately before cache is populated
        metrics = collector.fetch()
        
        # Should collect on-demand since cache is empty
        assert isinstance(metrics, dict)
        assert "cpu_percent" in metrics
        
        collector.stop()

    def test_concurrent_fetch_calls(self):
        """Test concurrent fetch() calls are safe."""
        collector = SystemMetricsCollector()
        
        def fetch_metrics():
            for _ in range(10):
                metrics = collector.fetch()
                assert isinstance(metrics, dict)
        
        threads = [threading.Thread(target=fetch_metrics) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    @patch("psutil.cpu_percent")
    def test_metrics_collection_with_mocked_psutil(self, mock_cpu):
        """Test metrics collection with mocked psutil."""
        mock_cpu.return_value = 50.0
        
        collector = SystemMetricsCollector(metrics_to_collect=["cpu_percent"])
        metrics = collector.fetch()
        
        assert metrics["cpu_percent"] == 50.0
        mock_cpu.assert_called_once()

    def test_load_average_handling(self):
        """Test load_average metric handling (may not be available on all platforms)."""
        collector = SystemMetricsCollector(metrics_to_collect=["load_average"])
        metrics = collector.fetch()
        
        # load_average may be None on platforms that don't support it
        assert "load_average" in metrics
        if metrics["load_average"] is not None:
            assert isinstance(metrics["load_average"], (list, tuple))


class TestSystemMetricsCollectorAvailableMetrics:
    """Test SystemMetricsCollector available metrics."""

    def test_all_metrics_are_callable(self):
        """Test that all available metrics are callable."""
        for metric_name, metric_func in SystemMetricsCollector.AVAILABLE_METRICS.items():
            result = metric_func()
            assert result is not None or metric_name == "load_average"

    def test_available_metrics_constant(self):
        """Test AVAILABLE_METRICS constant has expected keys."""
        expected_metrics = {
            "cpu_percent",
            "per_core_cpu_percent",
            "memory_percent",
            "disk_usage",
            "network_io",
            "load_average",
        }
        assert set(SystemMetricsCollector.AVAILABLE_METRICS.keys()) == expected_metrics


class TestSystemMetricsCollectorPerformance:
    """Test SystemMetricsCollector performance characteristics."""

    def test_cached_collection_faster_than_on_demand(self):
        """Test that cached collection is faster than on-demand."""
        # Collector with interval (cached)
        cached_collector = SystemMetricsCollector(interval=0.1)
        time.sleep(0.15)  # Wait for cache to populate
        
        # Collector without interval (on-demand)
        on_demand_collector = SystemMetricsCollector()
        
        # Measure cached fetch
        start = time.time()
        for _ in range(100):
            cached_collector.fetch()
        cached_time = time.time() - start
        
        # Measure on-demand fetch
        start = time.time()
        for _ in range(100):
            on_demand_collector.fetch()
        on_demand_time = time.time() - start
        
        # Cached should be significantly faster (just dict access)
        assert cached_time < on_demand_time * 0.5
        
        cached_collector.stop()

    def test_minimal_overhead_on_demand(self):
        """Test that on-demand collection has minimal overhead."""
        collector = SystemMetricsCollector(metrics_to_collect=["cpu_percent"])
        
        # Should complete quickly
        start = time.time()
        for _ in range(10):
            collector.fetch()
        duration = time.time() - start
        
        # Should take less than 1 second for 10 collections
        assert duration < 1.0

