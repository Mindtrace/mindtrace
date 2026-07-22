"""Thermal-aware load shedding for fanless edge devices.

Passively cooled edge boxes (Jetson modules, industrial NUCs, ARM SBCs)
throttle hard — or shut down outright — when the SoC overheats.  Rather than
letting the kernel governor clamp clock speeds mid-inspection, it is better
to shed inference load proactively and keep the device inside its thermal
envelope.

:func:`read_temperature_c` is a best-effort reader for the Linux sysfs
thermal interface, and :class:`ThermalGovernor` wraps it in a hysteresis
state machine: load is shed once the temperature reaches ``max_temp_c`` and
resumed only after it falls back below ``resume_temp_c``, so the system does
not flap around a single threshold.

The governor composes with
:class:`~mindtrace.models.serving.queue.InferenceQueue` at the call site —
check before submitting and skip the frame while shedding:

Example:
    >>> governor = ThermalGovernor(max_temp_c=85.0, resume_temp_c=75.0)
    >>> with InferenceQueue(model.predict, mode="latency") as queue:
    ...     for frame in camera:
    ...         if governor.check():
    ...             continue  # too hot: shed load by skipping this frame
    ...         queue.submit(frame)
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from mindtrace.core import Mindtrace

__all__ = ["ThermalGovernor", "read_temperature_c"]


_THERMAL_BASE = Path("/sys/class/thermal")


def read_temperature_c(zone: str | None = None) -> float | None:
    """Read a SoC temperature from the Linux sysfs thermal interface.

    Args:
        zone: Name of a specific thermal zone directory (e.g.
            ``"thermal_zone0"``).  When ``None``, all
            ``/sys/class/thermal/thermal_zone*/temp`` files are read and the
            highest temperature is returned.

    Returns:
        Temperature in degrees Celsius, or ``None`` when no zone could be
        read (non-Linux platform, missing sysfs entries, unreadable files).
    """
    if zone is not None:
        paths = [_THERMAL_BASE / zone / "temp"]
    else:
        try:
            paths = sorted(_THERMAL_BASE.glob("thermal_zone*/temp"))
        except OSError:
            return None

    temps: list[float] = []
    for path in paths:
        try:
            temps.append(int(path.read_text().strip()) / 1000.0)
        except (OSError, ValueError):
            continue
    return max(temps) if temps else None


class ThermalGovernor(Mindtrace):
    """Hysteresis state machine deciding when to shed inference load.

    The governor flips to *shedding* once a reading reaches ``max_temp_c``
    and flips back only when a reading falls below ``resume_temp_c``; the
    gap between the two thresholds prevents rapid flapping.  ``on_shed`` and
    ``on_resume`` fire exactly once per transition, each receiving the
    triggering temperature.  ``None`` readings never cause a transition: the
    governor simply reports its current state.

    Args:
        max_temp_c: Temperature (Celsius) at which load shedding starts.
        resume_temp_c: Temperature below which normal operation resumes.
            Must be lower than ``max_temp_c``.
        reader: Zero-argument callable returning the current temperature in
            Celsius or ``None``.  Defaults to :func:`read_temperature_c`.
        on_shed: Optional callback fired once when shedding starts.
        on_resume: Optional callback fired once when shedding ends.

    Raises:
        ValueError: If ``resume_temp_c`` is not lower than ``max_temp_c``.
    """

    def __init__(
        self,
        *,
        max_temp_c: float = 85.0,
        resume_temp_c: float = 75.0,
        reader: Callable[[], float | None] | None = None,
        on_shed: Callable[[float], None] | None = None,
        on_resume: Callable[[float], None] | None = None,
    ) -> None:
        super().__init__()
        if resume_temp_c >= max_temp_c:
            raise ValueError(
                f"resume_temp_c ({resume_temp_c}) must be lower than max_temp_c ({max_temp_c}) for hysteresis."
            )
        self._max_temp_c = max_temp_c
        self._resume_temp_c = resume_temp_c
        self._reader = reader if reader is not None else read_temperature_c
        self._on_shed = on_shed
        self._on_resume = on_resume
        self._shedding = False

    @property
    def shedding(self) -> bool:
        """Whether the governor is currently shedding load."""
        return self._shedding

    def check(self) -> bool:
        """Read the temperature and update the shedding state.

        Returns:
            ``True`` when the caller should shed load now (skip the next
            submission), ``False`` when it is safe to proceed.
        """
        temp = self._reader()
        if temp is None:
            return self._shedding
        if not self._shedding and temp >= self._max_temp_c:
            self._shedding = True
            self.logger.warning("Thermal governor shedding load at %.1f C (max %.1f C)", temp, self._max_temp_c)
            if self._on_shed is not None:
                self._on_shed(temp)
        elif self._shedding and temp < self._resume_temp_c:
            self._shedding = False
            self.logger.info("Thermal governor resuming at %.1f C (resume %.1f C)", temp, self._resume_temp_c)
            if self._on_resume is not None:
                self._on_resume(temp)
        return self._shedding
