# coding: utf-8
"""AOA / AOA/core/event_bus.py :: EventBus -- INTAKE STUB. Not an implementation.

Source: kali-linux AOA/core/event_bus.py (class EventBus, 98 lines in the module, 6 public API entries)
Atlas:  atlas_kali-linux.json, generated 2026-10-31
Adopt:  python tools/shard_intake.py --adopt "kali:AOA/core/event_bus.py#EventBus"

This file exists so the unit is *visible and addressable* from ELIZA. It has no
behaviour: `load()` raises. Wiring it is a deliberate change, made against the
tutorial in docs/TUTORIAL_SHARD_DEV_2026-11-02.md, and the first step is to read
the Kali source rather than to import this module.
"""
from __future__ import annotations

WIRED = True
SHARD_ID = "kali:AOA/core/event_bus.py#EventBus"
KIND = "class"
SOURCE_ENVIRONMENT = "kali-linux"
SOURCE_MODULE = "AOA/core/event_bus.py"
CLASS_NAME = 'EventBus'
UNNAMED_CLASSES = 0
TREE = "AOA"


def describe() -> dict:
    """What this shard is, where it came from, and whether it runs."""
    return {
        "shard_id": SHARD_ID,
        "kind": KIND,
        "tree": TREE,
        "source_module": SOURCE_MODULE,
        "class_name": CLASS_NAME,
        "unnamed_classes": UNNAMED_CLASSES,
        "environment": SOURCE_ENVIRONMENT,
        "wired": WIRED,
    }


def load(*args, **kwargs):
    """Return the adopted implementation, not a sentence about it."""
    from adopted.aoa.event_bus import EventBus
    return EventBus
