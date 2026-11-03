# coding: utf-8
"""The control behind every vendored adoption in `WIRED.json`.

`tools/adopt_queue.py` adopts a module by importing it in a subprocess; this file
re-checks the same units through the *stub path* a consumer would use, and
asserts that what comes back is the object the shard names. A ledger entry that
points at this file is therefore a claim with a control, not a flag.

**The work happens in `adopt_queue.check_shards`, and it happens in child
processes.** The first version imported every module in the pytest process and
paid for it: `CORE/sentinel_enforcer.py` writes to
`AppData\\AssistantLogs\\fusion.json` at import time and raised
`PermissionError: CRITICAL: Unauthorized write` from inside the suite (measured
2026-11-03). Importing vendored code is executing it, so the control executes it
where a side effect costs one batch instead of the run.

Each test covers one batch, so a wedged or hostile module names its own shard ids
instead of taking the suite with it.

Skips when nothing is vendored yet, so a checkout that has not run `--vendor`
still passes the suite instead of failing for a reason about the host.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ELIZA = Path(__file__).resolve().parents[1]
if str(ELIZA) not in sys.path:
    sys.path.insert(0, str(ELIZA))

import shards  # noqa: E402
from tools.adopt_queue import check_shards  # noqa: E402

VENDORED_TEST = "tests/test_adopted_kali_vendored.py"
BATCH = 40


def _entries():
    return sorted(shard_id for shard_id, claim
                  in shards.wired_ledger().items()
                  if isinstance(claim, dict) and claim.get("test") == VENDORED_TEST)


ENTRIES = _entries()
BATCHES = [ENTRIES[start:start + BATCH] for start in range(0, len(ENTRIES), BATCH)]

pytestmark = pytest.mark.skipif(
    not ENTRIES,
    reason="no vendored adoptions yet; run python tools/adopt_queue.py --vendor "
           "then --run N")


def test_the_ledger_entry_names_this_file_for_every_vendored_row():
    assert ENTRIES, "the ledger has no vendored rows"
    for shard_id, claim in shards.wired_ledger().items():
        if claim.get("mode") == "vendored":
            assert claim["test"] == VENDORED_TEST, shard_id


@pytest.mark.parametrize("batch", BATCHES,
                         ids=lambda batch: "%d shard(s) from %s" % (len(batch), batch[0]))
def test_each_batch_returns_the_units_its_shards_name(batch):
    report = check_shards(batch, batch=BATCH)
    failures = {shard_id: report[shard_id]["error"]
                for shard_id in batch
                if not report.get(shard_id, {}).get("ok")}
    assert not failures, "%d of %d shard(s) failed:\n%s" % (
        len(failures), len(batch),
        "\n".join("  %s -- %s" % (shard_id, failures[shard_id])
                  for shard_id in sorted(failures)))
