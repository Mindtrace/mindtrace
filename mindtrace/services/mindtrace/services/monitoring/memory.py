"""ServiceSessionMemory — thread-safe ring buffer for service state and events.

Design decisions:
- Bounded deque (maxlen) prevents unbounded memory growth.
- Separate state dict gives O(1) current-status lookup per service.
- Optional Redis sync via progressive enhancement: fails silently so no
  mandatory infrastructure dependency.
- All timestamps are UTC-aware datetimes.
- Thread-safe via threading.RLock (monitor and service may run in threads).
"""

from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    LAUNCH_STARTED = "launch_started"
    LAUNCH_SUCCESS = "launch_success"
    LAUNCH_FAILED = "launch_failed"
    SHUTDOWN = "shutdown"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_FAILED = "heartbeat_failed"
    ENDPOINT_CALLED = "endpoint_called"
    ENDPOINT_ERROR = "endpoint_error"
    ERROR = "error"
    RESTART = "restart"
    STATUS_CHANGE = "status_change"


class EventSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


_SEVERITY_RANK: Dict[EventSeverity, int] = {
    EventSeverity.DEBUG: 0,
    EventSeverity.INFO: 1,
    EventSeverity.WARNING: 2,
    EventSeverity.ERROR: 3,
    EventSeverity.CRITICAL: 4,
}


@dataclass
class ServiceEvent:
    timestamp: datetime
    service_name: str
    event_type: EventType
    severity: EventSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "service_name": self.service_name,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class ServiceState:
    """Current snapshot of a single service's health."""

    name: str
    status: str  # unknown | launching | running | stopped | failed | unreachable
    url: Optional[str] = None
    pid: Optional[int] = None
    service_class: Optional[str] = None
    last_seen: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    launch_time: Optional[datetime] = None
    restart_count: int = 0
    endpoint_calls: int = 0
    error_count: int = 0
    consecutive_heartbeat_failures: int = 0


# ---------------------------------------------------------------------------
# State machine: EventType → status transitions
# ---------------------------------------------------------------------------
_EVENT_TO_STATUS: Dict[EventType, str] = {
    EventType.LAUNCH_STARTED: "launching",
    EventType.LAUNCH_SUCCESS: "running",
    EventType.LAUNCH_FAILED: "failed",
    EventType.SHUTDOWN: "stopped",
    EventType.HEARTBEAT: "running",
    EventType.HEARTBEAT_FAILED: "unreachable",
    EventType.RESTART: "launching",
}


# ---------------------------------------------------------------------------
# ServiceSessionMemory
# ---------------------------------------------------------------------------


class ServiceSessionMemory:
    """Thread-safe in-process ring buffer for Mindtrace service monitoring.

    Args:
        max_events: Maximum events retained in memory (FIFO eviction).
        redis_url:  Optional Redis URL for persistence / multi-process sharing.
                    Falls back to in-memory only if Redis is unavailable.
        ttl_seconds: TTL applied to Redis keys (default 24 h).
    """

    def __init__(
        self,
        max_events: int = 10_000,
        redis_url: Optional[str] = None,
        ttl_seconds: int = 86_400,
    ) -> None:
        self._max_events = max_events
        self._events: Deque[ServiceEvent] = deque(maxlen=max_events)
        self._states: Dict[str, ServiceState] = {}
        self._lock = threading.RLock()
        self._redis: Any = None
        self._ttl = ttl_seconds

        if redis_url:
            self._connect_redis(redis_url)

    # ------------------------------------------------------------------
    # Redis (optional)
    # ------------------------------------------------------------------

    def _connect_redis(self, url: str) -> None:
        try:
            import redis  # type: ignore[import]
            client = redis.from_url(url, decode_responses=True)
            client.ping()
            self._redis = client
        except ImportError:
            pass  # redis package not installed
        except Exception:
            pass  # connection failed — graceful degradation

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def record_event(self, event: ServiceEvent) -> None:
        """Append an event and update the derived service state."""
        with self._lock:
            self._events.append(event)
            state = self._ensure_state(event.service_name)
            state.last_seen = event.timestamp

            # Error counters
            if event.severity in (EventSeverity.ERROR, EventSeverity.CRITICAL):
                state.error_count += 1
                state.last_error = event.message
                state.last_error_time = event.timestamp

            # State machine transition
            if event.event_type in _EVENT_TO_STATUS:
                state.status = _EVENT_TO_STATUS[event.event_type]

            # Specialised field updates
            if event.event_type == EventType.LAUNCH_SUCCESS:
                state.launch_time = event.timestamp
                state.consecutive_heartbeat_failures = 0
                if "url" in event.details:
                    state.url = event.details["url"]
                if "pid" in event.details:
                    state.pid = event.details["pid"]

            if event.event_type == EventType.HEARTBEAT:
                state.last_heartbeat = event.timestamp
                state.consecutive_heartbeat_failures = 0

            if event.event_type == EventType.HEARTBEAT_FAILED:
                state.consecutive_heartbeat_failures += 1

            if event.event_type == EventType.ENDPOINT_CALLED:
                state.endpoint_calls += 1

            if event.event_type == EventType.RESTART:
                state.restart_count += 1

        if self._redis:
            self._push_to_redis(event)

    def update_state(self, service_name: str, **kwargs: Any) -> None:
        """Directly update fields on a ServiceState (no event recorded)."""
        with self._lock:
            state = self._ensure_state(service_name)
            for key, value in kwargs.items():
                if hasattr(state, key):
                    setattr(state, key, value)

    def _ensure_state(self, name: str) -> ServiceState:
        if name not in self._states:
            self._states[name] = ServiceState(name=name, status="unknown")
        return self._states[name]

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get_state(self, service_name: str) -> Optional[ServiceState]:
        with self._lock:
            return self._states.get(service_name)

    def get_all_states(self) -> Dict[str, ServiceState]:
        with self._lock:
            return dict(self._states)

    def get_events(
        self,
        service_name: Optional[str] = None,
        event_type: Optional[EventType] = None,
        min_severity: Optional[EventSeverity] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ServiceEvent]:
        """Return matching events, most-recent last, up to *limit*."""
        with self._lock:
            events: List[ServiceEvent] = list(self._events)

        if service_name:
            events = [e for e in events if e.service_name == service_name]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if min_severity is not None:
            threshold = _SEVERITY_RANK[min_severity]
            events = [e for e in events if _SEVERITY_RANK.get(e.severity, 0) >= threshold]
        if since:
            events = [e for e in events if e.timestamp >= since]

        return events[-limit:]

    def get_errors(
        self,
        service_name: Optional[str] = None,
        since_minutes: int = 60,
        limit: int = 50,
    ) -> List[ServiceEvent]:
        """Convenience wrapper: errors in the last *since_minutes* minutes."""
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        return self.get_events(
            service_name=service_name,
            min_severity=EventSeverity.ERROR,
            since=since,
            limit=limit,
        )

    def summary(self) -> str:
        """One-line-per-service summary for LLM consumption."""
        states = self.get_all_states()
        if not states:
            return "No services are registered with the monitor."

        _icon = {
            "running": "✓",
            "stopped": "■",
            "failed": "✗",
            "launching": "…",
            "unreachable": "?",
            "unknown": "-",
        }
        lines = [f"=== Mindtrace Service Monitor ({len(states)} services) ==="]
        for name, s in states.items():
            icon = _icon.get(s.status, "?")
            parts = [f"  {icon} {name}: {s.status}"]
            if s.url:
                parts.append(f"url={s.url}")
            if s.error_count:
                parts.append(f"errors={s.error_count}")
            if s.restart_count:
                parts.append(f"restarts={s.restart_count}")
            if s.last_heartbeat:
                age = int((datetime.now(timezone.utc) - s.last_heartbeat).total_seconds())
                parts.append(f"last_heartbeat={age}s ago")
            if s.consecutive_heartbeat_failures:
                parts.append(f"consecutive_failures={s.consecutive_heartbeat_failures}")
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Redis sync (best-effort, never raises)
    # ------------------------------------------------------------------

    def _push_to_redis(self, event: ServiceEvent) -> None:
        try:
            key = f"mindtrace:monitor:events:{event.service_name}"
            payload = json.dumps(event.to_dict())
            pipe = self._redis.pipeline()
            pipe.lpush(key, payload)
            pipe.ltrim(key, 0, self._max_events - 1)
            pipe.expire(key, self._ttl)
            pipe.execute()
        except Exception:
            pass
