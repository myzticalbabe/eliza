# coding: utf-8
"""CODEX / CODEX/CORE/AUTO_DOWNLOADER.py :: DownloadProgress -- INTAKE STUB. Not an implementation.

Source: kali-linux CODEX/CORE/AUTO_DOWNLOADER.py (class DownloadProgress, 712 lines in the module, 36 public API entries)
Atlas:  atlas_kali-linux.json, generated 2026-10-31
Adopt:  python tools/shard_intake.py --adopt "kali:CODEX/CORE/AUTO_DOWNLOADER.py#DownloadProgress"

This file exists so the unit is *visible and addressable* from ELIZA. It has no
behaviour: `load()` raises. Wiring it is a deliberate change, made against the
tutorial in docs/TUTORIAL_SHARD_DEV_2026-11-02.md, and the first step is to read
the Kali source rather than to import this module.
"""
from __future__ import annotations

WIRED = False
SHARD_ID = "kali:CODEX/CORE/AUTO_DOWNLOADER.py#DownloadProgress"
KIND = "class"
SOURCE_ENVIRONMENT = "kali-linux"
SOURCE_MODULE = "CODEX/CORE/AUTO_DOWNLOADER.py"
CLASS_NAME = 'DownloadProgress'
UNNAMED_CLASSES = 0
TREE = "CODEX"


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
