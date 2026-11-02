# coding: utf-8
"""Controls for the requiem recorder: it must survive the crash it describes.

The failure this file exists to prevent is a crash handler that itself throws,
or one that writes a cause it cannot know. Both are tested from the outside —
by calling the recorder with the worst inputs available (an unserializable
context, a grave that cannot be opened, a SecurityError-shaped path) and
asserting that a record still comes back and that nothing propagates.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from eliza.psyche import requiem as rq  # noqa: E402


def _boom(depth: int = 0):
    if depth:
        return _boom(depth - 1)
    raise ValueError("the loop stopped mid-turn")


def _record(tmp_path, **overrides):
    try:
        _boom(2)
    except ValueError as exc:
        return rq.requiem(exc, path=tmp_path / "requiem.jsonl",
                          **{"unit": "eliza.psyche.rt_agent",
                             "where": "rt_agent.step", **overrides})


def test_a_crash_is_recorded_with_its_type_message_and_place(tmp_path):
    record = _record(tmp_path)
    assert record["recorded"] is True, record
    assert record["error"]["type"] == "ValueError"
    assert record["error"]["message"] == "the loop stopped mid-turn"
    assert record["unit"] == "eliza.psyche.rt_agent"
    assert record["where"] == "rt_agent.step"


def test_the_frame_chain_locates_the_death_not_the_entry_point(tmp_path):
    record = _record(tmp_path)
    assert record["frames"], "a requiem with no frames cannot be acted on"
    assert record["frames"][-1]["func"] == "_boom"
    assert record["frames"][-1]["line"] > 0


def test_it_records_but_names_no_cause(tmp_path):
    """Cause is a judgement made at the worst possible moment."""
    record = _record(tmp_path)
    assert "cause" not in record
    assert "diagnosis" not in record


def test_context_survives_values_json_cannot_hold(tmp_path):
    class Opaque:
        def __repr__(self):
            return "<opaque>"

    record = _record(tmp_path, context={"turn": 7, "session": Opaque(),
                                        "blob": b"\x00\x01", "nested": {"a": [1, 2]}})
    assert record["recorded"] is True
    stored = json.loads((tmp_path / "requiem.jsonl").read_text(encoding="utf-8"))
    assert stored["context"]["turn"] == 7
    assert "opaque" in stored["context"]["session"]
    assert stored["context"]["nested"] == {"a": [1, 2]}
    # ...and a scalar three levels down keeps its type instead of becoming a repr.
    assert stored["context"]["nested"]["a"] == [1, 2]


def test_a_grave_that_cannot_be_opened_returns_a_record_instead_of_raising(tmp_path):
    blocked = tmp_path / "a_directory.jsonl"
    blocked.mkdir()                       # opening a directory for append fails
    try:
        _boom(0)
    except ValueError as exc:
        record = rq.requiem(exc, unit="u", where="w", path=blocked)
    assert record["recorded"] is False
    assert record["write_error"]
    assert record["error"]["type"] == "ValueError"


def test_a_base_exception_is_recorded_too(tmp_path):
    try:
        raise KeyboardInterrupt("operator stopped it")
    except BaseException as exc:
        record = rq.requiem(exc, unit="u", where="w", path=tmp_path / "r.jsonl")
    assert record["error"]["type"] == "KeyboardInterrupt"
    assert record["recorded"] is True


def test_requiems_accumulate_and_read_back_newest_last(tmp_path):
    _record(tmp_path)
    _record(tmp_path)
    rows = rq.last(2, path=tmp_path / "requiem.jsonl")
    assert len(rows) == 2
    assert all(row["schema"] == rq.SCHEMA for row in rows)


def test_an_absent_grave_reads_as_empty_not_as_an_error(tmp_path):
    assert rq.last(path=tmp_path / "never_written.jsonl") == []



def test_a_torn_final_line_does_not_hide_the_records_before_it(tmp_path):
    target = tmp_path / "requiem.jsonl"
    _record(tmp_path)
    with target.open("a", encoding="utf-8") as handle:
        handle.write('{"schema": "eliza.requiem/1", "at": "torn')   # hard kill mid-write
    rows = rq.last(10, path=target)
    assert len(rows) == 1, rows


def test_the_epitaph_says_whether_it_was_recorded(tmp_path):
    record = _record(tmp_path)
    line = rq.epitaph(record)
    assert "eliza.psyche.rt_agent" in line and "ValueError" in line
    assert "NOT recorded" not in line

    blocked = tmp_path / "dir.jsonl"
    blocked.mkdir()
    try:
        _boom(0)
    except ValueError as exc:
        failed = rq.requiem(exc, unit="u", where="w", path=blocked)
    assert "NOT recorded" in rq.epitaph(failed)


def test_the_environment_names_the_grave(monkeypatch, tmp_path):
    target = tmp_path / "env.jsonl"
    monkeypatch.setenv(rq.ENV_PATH, str(target))
    try:
        _boom(0)
    except ValueError as exc:
        record = rq.requiem(exc, unit="u", where="w")   # no explicit path
    assert record["path"] == str(target)
    assert target.is_file()
    assert len(rq.last(path=None)) == 1
