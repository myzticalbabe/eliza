# coding: utf-8
"""Controls for the adopted AOA event bus, and for the shards that point at it.

Two questions per shard, and they are different:

* does the implementation behave like the unit it claims to be (a real publish,
  a real wildcard, a real failure path), and
* does `shards.load(<id>).load()` return *that* object rather than raising, which
  is the only thing that makes "wired" true rather than declared.

The second half is the one a flag flip cannot fake: it imports through the
surface, so a stub that lies about its state fails here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ELIZA = Path(__file__).resolve().parents[1]
if str(ELIZA) not in sys.path:
    sys.path.insert(0, str(ELIZA))

from adopted.aoa.event_bus import (  # noqa: E402
    AOEvent, AOEventType, EventBus, EventPipeline, EventPriority, get_event_bus,
)

SHARD_IDS = (
    "kali:AOA/core/event_bus.py#EventBus",
    "kali:AOA/core/event_bus.py#AOEvent",
    "kali:AOA/core/event_bus.py#AOEventType",
    "kali:AOA/core/event_bus.py#EventPipeline",
    "kali:AOA/core/event_bus.py#EventPriority",
)


def test_priority_values_match_the_source_including_the_medium_alias():
    assert (EventPriority.LOW, EventPriority.NORMAL, EventPriority.MEDIUM,
            EventPriority.HIGH, EventPriority.CRITICAL) == (0, 1, 1, 2, 3)


def test_publish_delivers_to_an_exact_pattern_and_counts_the_delivery():
    bus = EventBus()
    seen = []
    bus.subscribe(AOEventType.ARM_INITIALIZED, seen.append)

    delivered = bus.publish(AOEvent(event_type=AOEventType.ARM_INITIALIZED,
                                    source_arm="azazael"))

    assert delivered == 1
    assert [event.source_arm for event in seen] == ["azazael"]


@pytest.mark.parametrize("pattern, event_type, expected", [
    ("*", "anything.at.all", True),
    ("azazael.*", "azazael.worm.executed", True),
    ("*.executed", "azazael.worm.executed", True),
    ("azazael.*", "codex.render.started", False),
    ("*.executed", "azazael.worm.skipped", False),
])
def test_the_three_wildcard_forms(pattern, event_type, expected):
    assert EventBus._match_pattern(pattern, event_type) is expected


def test_a_failing_subscriber_is_isolated_counted_and_named():
    """The source swallowed this with `except: pass`; an adoption must not."""
    bus = EventBus()
    received = []

    def broken(event):
        raise RuntimeError("handler died")

    bus.subscribe("*", broken)
    bus.subscribe("*", received.append)

    delivered = bus.publish(AOEvent(event_type="x.y"))

    assert delivered == 1, "the healthy subscriber must still be served"
    assert bus.failed_deliveries == 1
    assert isinstance(bus.last_failure, RuntimeError)
    assert len(received) == 1


def test_history_is_bounded_and_filterable_and_correlation_is_addressable():
    bus = EventBus(max_history=3)
    for index in range(5):
        bus.publish(AOEvent(event_type="tick", source_arm="a",
                            correlation_id="run-1" if index % 2 else "run-2"))

    assert bus.history_count == 3, "the cap is a cap, not a hint"
    assert len(bus.get_history(source_arm="a", limit=2)) == 2
    assert len(bus.get_correlated_events("run-1")) == 1
    assert bus.get_history(event_type="absent") == []

    bus.clear_history()
    assert bus.history_count == 0


def test_unsubscribe_removes_only_the_named_callback():
    bus = EventBus()
    first, second = [], []
    bus.subscribe("*", first.append)
    bus.subscribe("*", second.append)

    bus.unsubscribe("*", first.append)

    assert bus.subscriber_count == 1
    bus.publish(AOEvent(event_type="e"))
    assert first == [] and len(second) == 1


def test_a_pipeline_folds_and_reports_the_failing_step():
    bus = EventBus()
    pipeline = EventPipeline(bus, name="demo")
    pipeline.add_step(lambda event: AOEvent(event_type="step.one",
                                            correlation_id=event.correlation_id))
    pipeline.add_step(lambda event: (_ for _ in ()).throw(ValueError("boom")))
    pipeline.add_step(lambda event: AOEvent(event_type="unreachable"))

    results = pipeline.execute(AOEvent(event_type="start", correlation_id="c1"))

    assert [event.event_type for event in results] == [
        "start", "step.one", AOEventType.WORKFLOW_FAILED]
    failure = results[-1]
    assert failure.payload == {"step": 1, "error": "boom"}
    assert failure.priority == EventPriority.CRITICAL
    assert failure.correlation_id == "c1"
    assert failure.source_arm == "pipeline.demo"


def test_a_pipeline_stops_on_a_none_step_instead_of_appending_null():
    pipeline = EventPipeline(EventBus(), name="halt")
    pipeline.add_step(lambda event: None)
    pipeline.add_step(lambda event: AOEvent(event_type="never"))

    assert [event.event_type for event in pipeline.execute(AOEvent(event_type="s"))] == ["s"]


def test_get_event_bus_is_a_lazy_singleton():
    assert get_event_bus() is get_event_bus()


@pytest.mark.parametrize("shard_id", SHARD_IDS)
def test_each_shard_returns_its_adopted_object(shard_id):
    import shards

    entry = shards.describe(shard_id)
    assert entry["wired"] is True, "%s is not in WIRED.json" % shard_id

    returned = shards.load(shard_id).load()
    expected = {"EventBus": EventBus, "AOEvent": AOEvent,
                "AOEventType": AOEventType, "EventPipeline": EventPipeline,
                "EventPriority": EventPriority}[entry["class"]]
    assert returned is expected
