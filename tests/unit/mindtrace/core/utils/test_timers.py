"""Unit tests for mindtrace.core.utils.timers module."""

from unittest.mock import MagicMock, patch

import pytest

from mindtrace.core.utils.timers import Timeout, Timer, TimerCollection


class TestTimer:
    """Test suite for the Timer class."""

    def test_timer_initialization(self):
        """Test timer is properly initialized."""
        timer = Timer()
        assert timer._start_time is None
        assert timer._stop_time is None
        assert timer._duration == 0.0
        assert timer.duration() == 0.0

    @patch("time.perf_counter")
    def test_timer_start(self, mock_perf_counter):
        """Test timer start functionality."""
        mock_perf_counter.return_value = 10.0
        timer = Timer()
        timer.start()

        assert timer._start_time == 10.0
        assert timer._stop_time is None

    @patch("time.perf_counter")
    def test_timer_stop(self, mock_perf_counter):
        """Test timer stop functionality."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        timer = Timer()
        timer.start()
        timer.stop()

        assert timer._start_time == 10.0
        assert timer._stop_time == 15.0
        assert timer._duration == 5.0

    @patch("time.perf_counter")
    def test_timer_stop_without_start(self, mock_perf_counter):
        """Test stopping timer without starting raises TypeError due to None arithmetic."""
        mock_perf_counter.return_value = 15.0
        timer = Timer()
        # This should raise TypeError because _start_time is None
        with pytest.raises(TypeError):
            timer.stop()

    @patch("time.perf_counter")
    def test_timer_multiple_stop_calls(self, mock_perf_counter):
        """Test multiple stop calls only record the first stop time."""
        mock_perf_counter.side_effect = [10.0, 15.0, 20.0]
        timer = Timer()
        timer.start()
        timer.stop()
        timer.stop()  # Second stop should be ignored

        assert timer._stop_time == 15.0
        assert timer._duration == 5.0

    @patch("time.perf_counter")
    def test_timer_duration_while_running(self, mock_perf_counter):
        """Test getting duration while timer is running."""
        mock_perf_counter.side_effect = [10.0, 17.5]
        timer = Timer()
        timer.start()
        duration = timer.duration()

        assert duration == 7.5

    @patch("time.perf_counter")
    def test_timer_duration_after_stop(self, mock_perf_counter):
        """Test getting duration after timer is stopped."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        timer = Timer()
        timer.start()
        timer.stop()

        assert timer.duration() == 5.0

    @patch("time.perf_counter")
    def test_timer_cumulative_duration(self, mock_perf_counter):
        """Test timer accumulates duration across multiple start/stop cycles."""
        mock_perf_counter.side_effect = [10.0, 15.0, 20.0, 25.0]
        timer = Timer()

        # First cycle: 5 seconds
        timer.start()
        timer.stop()
        assert timer.duration() == 5.0

        # Second cycle: 5 more seconds
        timer.start()
        timer.stop()
        assert timer.duration() == 10.0

    def test_timer_reset(self):
        """Test timer reset functionality."""
        timer = Timer()
        timer._start_time = 10.0
        timer._stop_time = 15.0
        timer._duration = 5.0

        timer.reset()

        assert timer._start_time is None
        assert timer._stop_time is None
        assert timer._duration == 0.0

    @patch("time.perf_counter")
    def test_timer_restart(self, mock_perf_counter):
        """Test timer restart functionality."""
        mock_perf_counter.return_value = 20.0
        timer = Timer()
        timer._duration = 5.0  # Simulate some previous duration

        timer.restart()

        assert timer._start_time == 20.0
        assert timer._stop_time is None
        assert timer._duration == 0.0

    @patch("time.perf_counter")
    def test_timer_str_representation(self, mock_perf_counter):
        """Test timer string representation."""
        mock_perf_counter.side_effect = [10.0, 15.123456]
        timer = Timer()
        timer.start()
        timer.stop()

        assert str(timer) == "5.123s"

    def test_timer_str_representation_zero(self):
        """Test timer string representation when duration is zero."""
        timer = Timer()
        assert str(timer) == "0.000s"


class TestTimerCollection:
    """Test suite for the TimerCollection class."""

    def test_timer_collection_initialization(self):
        """Test timer collection is properly initialized."""
        tc = TimerCollection()
        assert tc._timers == {}
        assert list(tc.names()) == []

    @patch("time.perf_counter")
    def test_start_new_timer(self, mock_perf_counter):
        """Test starting a new timer creates it."""
        mock_perf_counter.return_value = 10.0
        tc = TimerCollection()
        tc.start("test_timer")

        assert "test_timer" in tc._timers
        assert tc._timers["test_timer"]._start_time == 10.0

    @patch("time.perf_counter")
    def test_start_existing_timer(self, mock_perf_counter):
        """Test starting an existing timer."""
        mock_perf_counter.side_effect = [10.0, 15.0, 20.0]
        tc = TimerCollection()
        tc.start("test_timer")
        tc.stop("test_timer")
        tc.start("test_timer")  # Restart existing timer

        assert tc._timers["test_timer"]._start_time == 20.0

    @patch("time.perf_counter")
    def test_stop_existing_timer(self, mock_perf_counter):
        """Test stopping an existing timer."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        tc = TimerCollection()
        tc.start("test_timer")
        tc.stop("test_timer")

        assert tc._timers["test_timer"]._stop_time == 15.0

    def test_stop_nonexistent_timer(self):
        """Test stopping a non-existent timer raises KeyError."""
        tc = TimerCollection()
        with pytest.raises(KeyError, match="Timer nonexistent does not exist. Unable to stop."):
            tc.stop("nonexistent")

    @patch("time.perf_counter")
    def test_duration_existing_timer(self, mock_perf_counter):
        """Test getting duration of an existing timer."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        tc = TimerCollection()
        tc.start("test_timer")
        tc.stop("test_timer")

        assert tc.duration("test_timer") == 5.0

    def test_duration_nonexistent_timer(self):
        """Test getting duration of a non-existent timer raises KeyError."""
        tc = TimerCollection()
        with pytest.raises(KeyError, match="Timer nonexistent does not exist. Unable to get duration."):
            tc.duration("nonexistent")

    @patch("time.perf_counter")
    def test_reset_existing_timer(self, mock_perf_counter):
        """Test resetting an existing timer."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        tc = TimerCollection()
        tc.start("test_timer")
        tc.stop("test_timer")

        tc.reset("test_timer")

        assert tc._timers["test_timer"]._duration == 0.0
        assert tc._timers["test_timer"]._start_time is None

    def test_reset_nonexistent_timer(self):
        """Test resetting a non-existent timer raises KeyError."""
        tc = TimerCollection()
        with pytest.raises(KeyError, match="Timer nonexistent does not exist. Unable to reset."):
            tc.reset("nonexistent")

    @patch("time.perf_counter")
    def test_restart_existing_timer(self, mock_perf_counter):
        """Test restarting an existing timer."""
        mock_perf_counter.side_effect = [10.0, 15.0, 20.0]
        tc = TimerCollection()
        tc.start("test_timer")
        tc.stop("test_timer")

        tc.restart("test_timer")

        assert tc._timers["test_timer"]._start_time == 20.0
        assert tc._timers["test_timer"]._duration == 0.0

    def test_restart_nonexistent_timer(self):
        """Test restarting a non-existent timer raises KeyError."""
        tc = TimerCollection()
        with pytest.raises(KeyError, match="Timer nonexistent does not exist. Unable to restart."):
            tc.restart("nonexistent")

    @patch("time.perf_counter")
    def test_reset_all_timers(self, mock_perf_counter):
        """Test resetting all timers."""
        mock_perf_counter.side_effect = [10.0, 15.0, 20.0, 25.0]
        tc = TimerCollection()
        tc.start("timer1")
        tc.stop("timer1")
        tc.start("timer2")
        tc.stop("timer2")

        tc.reset_all()

        assert tc._timers["timer1"]._duration == 0.0
        assert tc._timers["timer2"]._duration == 0.0

    @patch("time.perf_counter")
    def test_names_method(self, mock_perf_counter):
        """Test getting names of all timers."""
        mock_perf_counter.return_value = 10.0
        tc = TimerCollection()
        tc.start("timer1")
        tc.start("timer2")
        tc.start("timer3")

        names = list(tc.names())
        assert set(names) == {"timer1", "timer2", "timer3"}

    @patch("time.perf_counter")
    def test_str_representation(self, mock_perf_counter):
        """Test string representation of timer collection."""
        mock_perf_counter.side_effect = [10.0, 15.123456, 20.0, 25.654321]
        tc = TimerCollection()
        tc.start("timer1")
        tc.stop("timer1")
        tc.start("timer2")
        tc.stop("timer2")

        result = str(tc)
        lines = result.split("\n")

        # Check that both timers are represented with 6 decimal places
        assert len(lines) == 2
        assert "timer1: 5.123456s" in lines
        assert "timer2: 5.654321s" in lines

    def test_str_representation_empty(self):
        """Test string representation of empty timer collection."""
        tc = TimerCollection()
        assert str(tc) == ""


class TestTimeout:
    """Test suite for the Timeout class."""

    def test_timeout_initialization_defaults(self):
        """Test timeout initialization with default values."""
        timeout = Timeout()
        assert timeout.timeout == 60.0
        assert timeout.retry_delay == 1.0
        assert timeout.exceptions == (Exception,)
        assert timeout.progress_bar is False
        assert timeout.desc is None

    def test_timeout_initialization_custom(self):
        """Test timeout initialization with custom values."""
        timeout = Timeout(
            timeout=30.0, retry_delay=0.5, exceptions=(ValueError, TypeError), progress_bar=True, desc="Testing"
        )
        assert timeout.timeout == 30.0
        assert timeout.retry_delay == 0.5
        assert timeout.exceptions == (ValueError, TypeError)
        assert timeout.progress_bar is True
        assert timeout.desc == "Testing"

    @patch("time.perf_counter")
    @patch("time.sleep")
    def test_timeout_run_success_immediately(self, mock_sleep, mock_perf_counter):
        """Test timeout run with immediate success."""
        mock_perf_counter.return_value = 0.0

        def test_func(x, y):
            return x + y

        timeout = Timeout(timeout=5.0)
        result = timeout.run(test_func, 2, 3)

        assert result == 5
        mock_sleep.assert_not_called()

    @patch("time.perf_counter")
    @patch("time.sleep")
    def test_timeout_run_success_after_retries(self, mock_sleep, mock_perf_counter):
        """Test timeout run with success after retries."""
        mock_perf_counter.side_effect = [0.0, 1.0, 2.0]

        call_count = 0

        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not ready yet")
            return "success"

        timeout = Timeout(timeout=5.0, retry_delay=0.1, exceptions=(ValueError,))
        result = timeout.run(test_func)

        assert result == "success"
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.1)

    @patch("time.perf_counter")
    @patch("time.sleep")
    def test_timeout_run_timeout_exceeded(self, mock_sleep, mock_perf_counter):
        """Test timeout run when timeout is exceeded."""
        mock_perf_counter.side_effect = [0.0, 3.0, 6.0]  # Exceeds 5.0 timeout

        def test_func():
            raise ValueError("Always fails")

        timeout = Timeout(timeout=5.0, retry_delay=0.1, exceptions=(ValueError,))

        with pytest.raises(TimeoutError, match="Timeout of 5.0 seconds reached."):
            timeout.run(test_func)

    @patch("time.perf_counter")
    @patch("time.sleep")
    def test_timeout_run_unexpected_exception(self, mock_sleep, mock_perf_counter):
        """Test timeout run with unexpected exception."""
        mock_perf_counter.return_value = 0.0

        def test_func():
            raise TypeError("Unexpected error")

        timeout = Timeout(timeout=5.0, exceptions=(ValueError,))

        with pytest.raises(TypeError, match="Unexpected error"):
            timeout.run(test_func)

        mock_sleep.assert_not_called()

    @patch("time.perf_counter")
    @patch("time.sleep")
    def test_timeout_as_decorator(self, mock_sleep, mock_perf_counter):
        """Test timeout used as a decorator."""
        mock_perf_counter.return_value = 0.0

        @Timeout(timeout=5.0)
        def test_func(x):
            return x * 2

        result = test_func(5)
        assert result == 10

    @patch("time.perf_counter")
    @patch("time.sleep")
    def test_timeout_decorator_with_exception(self, mock_sleep, mock_perf_counter):
        """Test timeout decorator with exception handling."""
        mock_perf_counter.side_effect = [0.0, 1.0]

        call_count = 0

        @Timeout(timeout=5.0, retry_delay=0.1, exceptions=(ValueError,))
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Not ready")
            return "success"

        result = test_func()
        assert result == "success"
        mock_sleep.assert_called_once_with(0.1)

    @patch("mindtrace.core.utils.timers.tqdm")
    @patch("time.perf_counter")
    @patch("time.sleep")
    def test_timeout_with_progress_bar(self, mock_sleep, mock_perf_counter, mock_tqdm):
        """Test timeout with progress bar enabled."""
        mock_perf_counter.return_value = 0.0
        mock_progress_bar = MagicMock()
        mock_tqdm.return_value = mock_progress_bar

        def test_func():
            return "success"

        timeout = Timeout(timeout=5.0, progress_bar=True, desc="Testing")
        result = timeout.run(test_func)

        assert result == "success"
        mock_tqdm.assert_called_once_with(total=5.0, desc="Testing", leave=False)
        mock_progress_bar.update.assert_called_once()
        mock_progress_bar.close.assert_called_once()

    @patch("mindtrace.core.utils.timers.tqdm")
    @patch("time.perf_counter")
    @patch("time.sleep")
    def test_timeout_progress_bar_with_exception(self, mock_sleep, mock_perf_counter, mock_tqdm):
        """Test timeout progress bar is closed when unexpected exception occurs."""
        mock_perf_counter.return_value = 0.0
        mock_progress_bar = MagicMock()
        mock_tqdm.return_value = mock_progress_bar

        def test_func():
            raise RuntimeError("Unexpected error")

        timeout = Timeout(timeout=5.0, progress_bar=True, exceptions=(ValueError,))

        with pytest.raises(RuntimeError):
            timeout.run(test_func)

        mock_progress_bar.close.assert_called_once()

    @patch("time.perf_counter")
    @patch("time.sleep")
    def test_timeout_with_args_and_kwargs(self, mock_sleep, mock_perf_counter):
        """Test timeout properly passes args and kwargs to the function."""
        mock_perf_counter.return_value = 0.0

        def test_func(a, b, c=None):
            return f"{a}-{b}-{c}"

        timeout = Timeout()
        result = timeout.run(test_func, "arg1", "arg2", c="kwarg1")

        assert result == "arg1-arg2-kwarg1"

    def test_timeout_call_returns_wrapped_function(self):
        """Test that calling timeout returns a properly wrapped function."""
        timeout = Timeout()

        def test_func(x):
            return x * 2

        wrapped_func = timeout(test_func)
        result = wrapped_func(5)

        assert result == 10


class TestTimerContextManager:
    """Test suite for Timer context manager functionality."""

    @patch("time.perf_counter")
    def test_timer_context_manager_basic(self, mock_perf_counter):
        """Test Timer as a context manager."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        timer = Timer()

        with timer:
            pass

        assert timer._start_time == 10.0
        assert timer._stop_time == 15.0
        assert timer.duration() == 5.0

    @patch("time.perf_counter")
    def test_timer_context_manager_returns_self(self, mock_perf_counter):
        """Test Timer context manager returns the timer instance."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        timer = Timer()

        with timer as ctx_timer:
            assert ctx_timer is timer
            assert ctx_timer._start_time == 10.0

    @patch("time.perf_counter")
    def test_timer_context_manager_with_exception(self, mock_perf_counter):
        """Test Timer context manager properly handles exceptions."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        timer = Timer()

        with pytest.raises(ValueError, match="test exception"):
            with timer:
                raise ValueError("test exception")

        # Timer should still be stopped even with exception
        assert timer._stop_time == 15.0
        assert timer.duration() == 5.0

    @patch("time.perf_counter")
    def test_timer_context_manager_cumulative(self, mock_perf_counter):
        """Test Timer context manager with cumulative timing."""
        mock_perf_counter.side_effect = [10.0, 15.0, 20.0, 25.0]
        timer = Timer()

        # First context
        with timer:
            pass
        assert timer.duration() == 5.0

        # Second context (should accumulate)
        with timer:
            pass
        assert timer.duration() == 10.0


class TestTimerCollectionContextManager:
    """Test suite for TimerCollection context manager functionality via TimerContext."""

    @patch("time.perf_counter")
    def test_timer_collection_start_returns_context_manager(self, mock_perf_counter):
        """Test TimerCollection.start() returns a context manager."""
        from mindtrace.core.utils.timers import TimerContext

        mock_perf_counter.return_value = 10.0
        tc = TimerCollection()

        context_manager = tc.start("test_timer")

        assert isinstance(context_manager, TimerContext)
        assert context_manager.timer_collection is tc
        assert context_manager.name == "test_timer"
        assert tc._timers["test_timer"]._start_time == 10.0

    @patch("time.perf_counter")
    def test_timer_context_manager_basic(self, mock_perf_counter):
        """Test TimerContext as a context manager."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        tc = TimerCollection()

        with tc.start("timer1"):
            pass

        # Timer should be stopped automatically
        assert tc.duration("timer1") == 5.0

    @patch("time.perf_counter")
    def test_timer_context_manager_nested(self, mock_perf_counter):
        """Test nested TimerContext managers."""
        mock_perf_counter.side_effect = [10.0, 20.0, 30.0, 40.0]
        tc = TimerCollection()

        with tc.start("Timer 1"):
            with tc.start("Timer 2"):
                pass  # Timer 2 stops here at 30.0
            # Timer 2 should be stopped, Timer 1 still running
            pass
        # Timer 1 stops here at 40.0

        assert tc.duration("Timer 1") == 30.0  # 40.0 - 10.0
        assert tc.duration("Timer 2") == 10.0  # 30.0 - 20.0

    @patch("time.perf_counter")
    def test_timer_context_manager_with_exception(self, mock_perf_counter):
        """Test TimerContext properly handles exceptions."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        tc = TimerCollection()

        with pytest.raises(ValueError, match="test exception"):
            with tc.start("timer1"):
                raise ValueError("test exception")

        # Timer should still be stopped even with exception
        assert tc.duration("timer1") == 5.0

    @patch("time.perf_counter")
    def test_timer_context_manager_returns_context(self, mock_perf_counter):
        """Test TimerContext manager returns the context object."""
        mock_perf_counter.side_effect = [10.0, 15.0]
        tc = TimerCollection()

        with tc.start("timer1") as ctx:
            assert ctx.name == "timer1"
            assert ctx.timer_collection is tc

    @patch("time.perf_counter")
    def test_timer_context_manager_multiple_sequential(self, mock_perf_counter):
        """Test multiple sequential context managers work correctly."""
        mock_perf_counter.side_effect = [10.0, 15.0, 20.0, 25.0]
        tc = TimerCollection()

        with tc.start("Timer 1"):
            pass
        # Timer 1 stopped at 15.0

        with tc.start("Timer 2"):
            pass
        # Timer 2 stopped at 25.0

        assert tc.duration("Timer 1") == 5.0  # 15.0 - 10.0
        assert tc.duration("Timer 2") == 5.0  # 25.0 - 20.0


class TestTimerCollectionAddTimer:
    """Test suite for TimerCollection add_timer method."""

    def test_add_timer_new(self):
        """Test adding a new timer."""
        tc = TimerCollection()
        tc.add_timer("test_timer")

        assert "test_timer" in tc._timers
        assert isinstance(tc._timers["test_timer"], Timer)

    def test_add_timer_replace_existing(self):
        """Test adding a timer that replaces an existing one."""
        tc = TimerCollection()
        tc.add_timer("test_timer")
        old_timer = tc._timers["test_timer"]
        old_timer._duration = 5.0  # Set some state

        tc.add_timer("test_timer")  # Replace
        new_timer = tc._timers["test_timer"]

        assert new_timer is not old_timer
        assert new_timer._duration == 0.0  # New timer is fresh


class TestTimerCollectionStartReturnValue:
    """Test suite for TimerCollection start method return value."""

    @patch("time.perf_counter")
    def test_start_returns_timer_context(self, mock_perf_counter):
        """Test that start method returns a TimerContext instance."""
        from mindtrace.core.utils.timers import TimerContext

        mock_perf_counter.return_value = 10.0
        tc = TimerCollection()

        returned_context = tc.start("test_timer")

        assert isinstance(returned_context, TimerContext)
        assert returned_context.timer_collection is tc
        assert returned_context.name == "test_timer"
        assert tc._timers["test_timer"]._start_time == 10.0
