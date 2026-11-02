# coding: utf-8
"""TOOLS / TOOLS/PythonSystemMapper.py :: PythonSystemMapper -- INTAKE STUB. Not an implementation.

Source: kali-linux TOOLS/PythonSystemMapper.py (class PythonSystemMapper, 378 lines in the module, 2 public API entries)
Atlas:  atlas_kali-linux.json, generated 2026-10-31
Adopt:  python tools/shard_intake.py --adopt "kali:TOOLS/PythonSystemMapper.py#PythonSystemMapper"

This file exists so the unit is *visible and addressable* from ELIZA. It has no
behaviour: `load()` raises. Wiring it is a deliberate change, made against the
tutorial in docs/TUTORIAL_SHARD_DEV_2026-11-02.md, and the first step is to read
the Kali source rather than to import this module.
"""
from __future__ import annotations

WIRED = False
SHARD_ID = "kali:TOOLS/PythonSystemMapper.py#PythonSystemMapper"
KIND = "class"
SOURCE_ENVIRONMENT = "kali-linux"
SOURCE_MODULE = "TOOLS/PythonSystemMapper.py"
CLASS_NAME = 'PythonSystemMapper'
UNNAMED_CLASSES = 0
TREE = "TOOLS"


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
