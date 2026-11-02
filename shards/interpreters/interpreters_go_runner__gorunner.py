# coding: utf-8
"""INTERPRETERS / INTERPRETERS/go_runner.py :: GoRunner -- INTAKE STUB. Not an implementation.

Source: kali-linux INTERPRETERS/go_runner.py (class GoRunner, 395 lines in the module, 3 public API entries)
Atlas:  atlas_kali-linux.json, generated 2026-10-31
Adopt:  python tools/shard_intake.py --adopt "kali:INTERPRETERS/go_runner.py#GoRunner"

This file exists so the unit is *visible and addressable* from ELIZA. It has no
behaviour: `load()` raises. Wiring it is a deliberate change, made against the
tutorial in docs/TUTORIAL_SHARD_DEV_2026-11-02.md, and the first step is to read
the Kali source rather than to import this module.
"""
from __future__ import annotations

WIRED = False
SHARD_ID = "kali:INTERPRETERS/go_runner.py#GoRunner"
KIND = "class"
SOURCE_ENVIRONMENT = "kali-linux"
SOURCE_MODULE = "INTERPRETERS/go_runner.py"
CLASS_NAME = 'GoRunner'
UNNAMED_CLASSES = 0
TREE = "INTERPRETERS"


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
    """Refuse, loudly, with the reason and the place to start reading."""
    raise NotImplementedError(
        "shard %s is an intake stub: %s is not implemented in ELIZA. "
        "Read the Kali source at %s, then see "
        "docs/TUTORIAL_SHARD_DEV_2026-11-02.md" % (SHARD_ID, SHARD_ID, SOURCE_MODULE)
    )
