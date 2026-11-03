# coding: utf-8
"""Cross-arm pub/sub, adopted from `kali:AOA/core/event_bus.py`.

The Kali module is 98 lines with no third-party imports and no import-time side
effects, which makes it the clean case: five named units that only mean anything
together, so all five shards point here.

    kali:AOA/core/event_bus.py#EventBus        -> EventBus
    kali:AOA/core/event_bus.py#AOEvent         -> AOEvent
    kali:AOA/core/event_bus.py#AOEventType     -> AOEventType
    kali:AOA/core/event_bus.py#EventPipeline   -> EventPipeline
    kali:AOA/core/event_bus.py#EventPriority   -> EventPriority

What changed in the adoption, and why (the differences are deliberate, not
drift):

* `publish()` no longer wraps each callback in a bare `except: pass`. A failing
  subscriber is isolated -- the remaining subscribers still receive the event --
  but the failure is counted and the last exception is kept on
  `failed_deliveries` / `last_failure`. A bus that swallows handler errors is a
  capability that reads as working while a callback is dead.
* `publish()` returns the number of deliveries, so a caller can tell "nobody was
  listening" from "handled". The Kali version returns None.
* The module-level singleton is created on first `get_event_bus()` call, not at
  import: importing a module should not build global state.

Everything else -- the pattern syntax, the history cap, the pipeline's
WORKFLOW_FAILED event, the priority values -- matches the source.
"""
from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple


class EventPriority:
    """Delivery urgency. `MEDIUM` is an alias of `NORMAL`, as in the source."""

    LOW = 0
    NORMAL = 1
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class AOEventType:
    """The event names the AOA arms publish. Plain strings, as in the source."""

    ARM_INITIALIZED = "arm.initialized"
    ARM_SHUTDOWN = "arm.shutdown"
    ARM_ERROR = "arm.error"

    LIBRA_DOC_GENERATED = "libra.doc.generated"
    LIBRA_TEMPLATE_LOADED = "libra.template.loaded"
    LIBRA_FILING_COMPLETE = "libra.filing.complete"

    AZAZAEL_WORM_EXECUTED = "azazael.worm.executed"
    AZAZAEL_CLUSTER_COMPLETE = "azazael.cluster.complete"
    AZAZAEL_ANOMALY_DETECTED = "azazael.anomaly.detected"

    CODEX_RENDER_STARTED = "codex.render.started"
    CODEX_RENDER_COMPLETE = "codex.render.complete"
    CODEX_VIDEO_READY = "codex.video.ready"

    EVE_MODEL_SELECTED = "eve.model.selected"
    EVE_BENCHMARK_COMPLETE = "eve.benchmark.complete"
    EVE_INFERENCE_COMPLETE = "eve.inference.complete"

    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_STEP_COMPLETE = "workflow.step.complete"
    WORKFLOW_COMPLETE = "workflow.complete"
    WORKFLOW_FAILED = "workflow.failed"

    SESSION_MILESTONE = "session.milestone"
    SESSION_STARTED = "session.started"
    SESSION_COMPLETED = "session.completed"


@dataclass
class AOEvent:
    """One published event, with the eight-character id the source uses."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: str = ""
    source_arm: str = ""
    target_arm: str = ""
    payload: dict = field(default_factory=dict)
    priority: int = EventPriority.NORMAL
    correlation_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_arm": self.source_arm,
            "target_arm": self.target_arm,
            "payload": self.payload,
            "priority": self.priority,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class EventBus:
    """Topic bus with three wildcard forms, a bounded history and isolation.

    Patterns are matched exactly, as `*`, as `prefix.*`, or as `*.suffix`. The
    source's `prefix.*` test uses `startswith(pattern[:-2])`, which is why
    `azazael.*` also matches `azazael_x`: kept, because a caller that relies on
    the looser form must not be surprised by a stricter adoption.
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._subscribers: Dict[str, List[Callable[[AOEvent], Any]]] = defaultdict(list)
        self._history: List[AOEvent] = []
        self._max_history = max_history
        self._lock = threading.Lock()
        self.failed_deliveries = 0
        self.last_failure: Optional[BaseException] = None

    def publish(self, event: AOEvent) -> int:
        """Record the event, then deliver it. Returns the delivery count."""
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            targets: List[Callable[[AOEvent], Any]] = []
            for pattern, callbacks in self._subscribers.items():
                if self._match_pattern(pattern, event.event_type):
                    targets.extend(callbacks)
        delivered = 0
        for callback in targets:
            try:
                callback(event)
                delivered += 1
            except Exception as exc:          # isolated, counted, never silent
                self.failed_deliveries += 1
                self.last_failure = exc
        return delivered

    def subscribe(self, pattern: str, callback: Callable[[AOEvent], Any]) -> None:
        with self._lock:
            self._subscribers[pattern].append(callback)

    def unsubscribe(self, pattern: str, callback: Callable[[AOEvent], Any]) -> None:
        with self._lock:
            if pattern in self._subscribers:
                self._subscribers[pattern] = [
                    existing for existing in self._subscribers[pattern]
                    if existing != callback
                ]

    def get_history(self, event_type: Optional[str] = None,
                    source_arm: Optional[str] = None, limit: int = 100) -> List[AOEvent]:
        with self._lock:
            found = list(self._history)
        if event_type:
            found = [event for event in found if event.event_type == event_type]
        if source_arm:
            found = [event for event in found if event.source_arm == source_arm]
        return found[-limit:]

    def get_correlated_events(self, correlation_id: str) -> List[AOEvent]:
        with self._lock:
            return [event for event in self._history
                    if event.correlation_id == correlation_id]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    @staticmethod
    def _match_pattern(pattern: str, event_type: str) -> bool:
        if pattern == event_type or pattern == "*":
            return True
        if pattern.endswith(".*") and event_type.startswith(pattern[:-2]):
            return True
        if pattern.startswith("*.") and event_type.endswith(pattern[2:]):
            return True
        return False

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return sum(len(callbacks) for callbacks in self._subscribers.values())

    @property
    def history_count(self) -> int:
        with self._lock:
            return len(self._history)


class EventPipeline:
    """Steps folded left to right over one event; a raise ends the chain.

    A failing step does not propagate: it appends a CRITICAL
    `WORKFLOW_FAILED` event carrying the step index and the error string, and
    the partial results are returned. Same contract as the source.
    """

    def __init__(self, bus: EventBus, name: str = "") -> None:
        self.bus = bus
        self.name = name
        self._steps: List[Callable[[AOEvent], Optional[AOEvent]]] = []

    def add_step(self, handler: Callable[[AOEvent], Optional[AOEvent]]) -> None:
        self._steps.append(handler)

    def execute(self, initial: AOEvent) -> List[AOEvent]:
        results: List[AOEvent] = [initial]
        current = initial
        for index, step in enumerate(self._steps):
            try:
                following = step(current)
                if following is None:
                    break
                results.append(following)
                current = following
            except Exception as exc:
                results.append(AOEvent(
                    event_type=AOEventType.WORKFLOW_FAILED,
                    source_arm="pipeline." + self.name,
                    payload={"step": index, "error": str(exc)},
                    correlation_id=initial.correlation_id,
                    priority=EventPriority.CRITICAL,
                ))
                break
        return results


_BUS: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """The process-wide bus. Built on first use, not at import."""
    global _BUS
    if _BUS is None:
        _BUS = EventBus()
    return _BUS
