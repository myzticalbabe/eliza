# coding: utf-8
"""Instrument package: the scripts that build, grade and audit this tree.

WHY THIS FILE EXISTS
--------------------
`pyproject.toml` already declares `tools` in `[tool.setuptools] packages`, and
`tests/test_adopted_kali_vendored.py` imports it as `tools.adopt_queue` -- a
qualified import that needs `tools/` to be a package, since the repository root
(rather than `tools/`) is what the test puts on `sys.path`. Without this file the
suite failed at collection with `ModuleNotFoundError: No module named
'tools.adopt_queue'`, and an editable install of the declared package layout
could not resolve the submodule either.

The modules stay runnable as scripts (`python tools/shard_intake.py`) because
each one carries its own `main()`; being a package only adds the qualified path.
"""
