# coding: utf-8
"""Units adopted from the Kali lane, by decision, behind their shard paths.

`shards/` names 1,183 units and runs none of them. This package is where a unit
goes when someone decides it should run: a re-implementation in ELIZA's own
idiom, kept in a package that `tools/publicize.py` does not generate and
`--clean` does not delete.

Nothing here is a copy. A copied module drags its imports, its module-level
globals and its file-system assumptions into a package whose `pyproject.toml`
says `dependencies = []`; the point of reading the Kali source is to decide what
the unit needs here, not to move it.

The stub in `shards/` keeps the provenance (`SHARD_ID`, `SOURCE_MODULE`,
`CLASS_NAME`) and its `load()` returns the object defined here, so the index can
still answer "where did this come from". `shards/WIRED.json` records the test
that proves it.
"""
from __future__ import annotations
