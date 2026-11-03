# coding: utf-8
"""CORE / CORE/inference/nim_client.py :: NimModel -- INTAKE STUB. Not an implementation.

Source: kali-linux CORE/inference/nim_client.py (class NimModel, 331 lines in the module, 5 public API entries)
Atlas:  atlas_kali-linux.json, generated 2026-10-31
Adopt:  python tools/shard_intake.py --adopt "kali:CORE/inference/nim_client.py#NimModel"

This file exists so the unit is *visible and addressable* from ELIZA. It has no
behaviour: `load()` raises. Wiring it is a deliberate change, made against the
tutorial in docs/TUTORIAL_SHARD_DEV_2026-11-02.md, and the first step is to read
the Kali source rather than to import this module.
"""
from __future__ import annotations

WIRED = True
SHARD_ID = "kali:CORE/inference/nim_client.py#NimModel"
KIND = "class"
SOURCE_ENVIRONMENT = "kali-linux"
SOURCE_MODULE = "CORE/inference/nim_client.py"
CLASS_NAME = 'NimModel'
UNNAMED_CLASSES = 0
TREE = "CORE"


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
    """Return the vendored unit. Importing the module is the adoption."""
    import importlib

    vendored = importlib.import_module('adopted.kali.CORE.inference.nim_client')
    return vendored if CLASS_NAME is None else getattr(vendored, CLASS_NAME)
