#!/usr/bin/env python3
# coding: utf-8
"""A durable adoption queue for the 1,183 shards, and a worker that churns it.

`shard_intake.py` names every Kali unit and runs none of them. `WIRED.json` is
where a unit stops being a stub, but hand-porting 1,183 units one at a time
leaves the ledger almost empty and no record of what remains. This tool carries
the remainder explicitly:

  python tools/adopt_queue.py --build          # one row per module, all shards
  python tools/adopt_queue.py --status         # pending / done / blocked counts
  python tools/adopt_queue.py --vendor         # mirror + normalise the source
  python tools/adopt_queue.py --run 20         # adopt the next 20 modules
  python tools/adopt_queue.py --retry-blocked  # try the blocked rows again

**How a row is adopted.** The row is a Kali module. The worker vendors the whole
Kali source tree once (verbatim, imports normalised to the vendored root), then
for each row imports the vendored module **in a subprocess with a timeout**. A
module that imports cleanly is adopted: every one of its shards gets
`WIRED = True`, a `load()` that returns the named attribute, and a ledger entry
pointing at the shared control `tests/test_adopted_kali_vendored.py`. A module
that does not import is recorded `blocked` with the reason, and its shards stay
stubs.

That is a **vendored adoption, not a re-implementation**, and the queue says so
in every row it finishes (`mode: vendored`). The five hand-ported units in
`adopted/aoa/event_bus.py` keep their own mode and are never touched: a row whose
shards are all already wired is skipped.

Why a subprocess per module: importing Kali code is executing it. Some modules
start threads, open sockets or read `/root`; a hang must cost one row's timeout,
not the worker. A worker that dies mid-row leaves the row `pending` -- the queue
is the state, and re-running it is safe because adoption is idempotent.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import shard_intake as intake  # noqa: E402

QUEUE = intake.SHARDS / "ADOPTION_QUEUE.json"
VENDOR = REPO / "adopted" / "kali"
SHARED_TEST = "tests/test_adopted_kali_vendored.py"
STUB = '''# coding: utf-8
"""Fed to ELIZA from Kali by tools/adopt_queue.py -- vendored, not re-implemented."""
from __future__ import annotations

WIRED = {wired}
SHARD_ID = {shard_id!r}
KIND = {kind!r}
SOURCE_ENVIRONMENT = "kali-linux"
SOURCE_MODULE = {module!r}
CLASS_NAME = {class_name!r}
UNNAMED_CLASSES = {unnamed}
TREE = {tree!r}


def describe() -> dict:
    return {{
        "shard_id": SHARD_ID,
        "kind": KIND,
        "tree": TREE,
        "source_module": SOURCE_MODULE,
        "class_name": CLASS_NAME,
        "unnamed_classes": UNNAMED_CLASSES,
        "environment": SOURCE_ENVIRONMENT,
        "wired": WIRED,
    }}


def load(*args, **kwargs):
    """Return the vendored unit. Importing the module is the adoption."""
    import importlib

    vendored = importlib.import_module({dotted!r})
    return vendored if CLASS_NAME is None else getattr(vendored, CLASS_NAME)
'''
LOAD_TAIL = '''def load(*args, **kwargs):
    """Return the vendored unit. Importing the module is the adoption."""
    import importlib

    vendored = importlib.import_module({dotted!r})
    return vendored if CLASS_NAME is None else getattr(vendored, CLASS_NAME)
'''


def _real_case(parts: Sequence[str]) -> Optional[str]:
    """The on-disk spelling of a path inside the vendor tree, or None.

    The atlas records `scripts/gate_bash.py`; the directory is `SCRIPTS`. Windows
    resolves that case-insensitively for a path check, so `_resolves` was happy
    and the dotted name was still wrong: `import adopted.kali.scripts` raised
    `ModuleNotFoundError` because Python matches package **names**, not paths,
    and `find_spec` returned None for a directory that visibly exists. Eight rows
    blocked on case alone (measured 2026-11-03). So every emitted name is rebuilt
    from the real directory entries.
    """
    base = VENDOR
    resolved: List[str] = []
    for part in parts:
        # A resolved `.py` file cannot be descended into (`METAWORMS.py` treated
        # as a directory raised NotADirectoryError), so the walk stops there.
        if not base.is_dir():
            return None
        # Never trust the spelling: `(base / "scripts").exists()` is True for a
        # directory actually named `SCRIPTS`, so asking the filesystem whether
        # the path lives is not the same question as what the entry is called.
        # A module part arrives without its suffix (`gate_bash`, from
        # `scripts/gate_bash.py`), so both spellings are candidates and a package
        # directory wins over a same-named module, as Python's own import does.
        entries = [child.name for child in base.iterdir()]
        wanted = [part, part + ".py"]
        chosen = next((name for name in wanted if name in entries), None)
        if chosen is None:
            lowered = {name.lower() for name in wanted}
            matches = sorted(name for name in entries if name.lower() in lowered)
            if not matches:
                return None
            chosen = matches[0]
        resolved.append(chosen)
        base = base / chosen
    return "/".join(resolved)


def _module_path(parts: Sequence[str]) -> Optional[str]:
    """On-disk module path for `parts`, without the source suffix.

    `_real_case` answers with what the file is called (`gate_bash.py`); a dotted
    module name must not carry that suffix, or every emitted import reads
    `adopted.kali.SCRIPTS.gate_bash.py`.
    """
    real = _real_case(parts)
    if real is None:
        return None
    return real[:-3] if real.endswith(".py") else real


def _dotted(module: str) -> str:
    parts = module[:-3].split("/") if module.endswith(".py") else module.split("/")
    real = _module_path(parts)
    return "adopted.kali." + (real if real is not None else module[:-3]).replace("/", ".")


SOURCE_ROOT = "/root/azazael/src"


def _source_root() -> str:
    """Where the Kali source is, as this host can reach it.

    Windows Python cannot open \\\\wsl.localhost\\... (measured 2026-11-03: os.path
    exists returns False while Git Bash lists it), so the vendor step streams a
    tar out of the distro instead of copying paths. It stays a **string**: a
    `Path` on Windows renders this as `\\root\\azazael\\src`, which wsl.exe reads
    as a relative Windows path and fails with exit 2 (measured 2026-11-03).
    """
    return SOURCE_ROOT


def _shards_by_module() -> Dict[str, Dict]:
    atlas = intake.read_atlas(intake.DEFAULT_ATLAS)
    grouped: Dict[str, Dict] = {}
    for entry in intake.units(atlas):
        row = grouped.setdefault(entry["module"], {
            "module": entry["module"], "tree": entry["tree"],
            "shards": [], "status": "pending", "attempts": 0, "note": "",
        })
        row["shards"].append({
            "shard_id": entry["shard_id"], "kind": entry["kind"],
            "class_name": entry["class"], "unnamed": entry.get("unnamed", 0),
            "path": entry["path"],
        })
    return grouped


def build() -> int:
    """One row per module; an existing row keeps its status and attempts."""
    existing: Dict[str, Dict] = {}
    if QUEUE.is_file():
        for row in json.loads(QUEUE.read_text(encoding="utf-8")).get("rows", []):
            existing[row["module"]] = row
    rows = []
    for module, fresh in sorted(_shards_by_module().items()):
        kept = existing.get(module)
        if kept is not None:
            fresh["status"] = kept.get("status", "pending")
            fresh["attempts"] = kept.get("attempts", 0)
            fresh["note"] = kept.get("note", "")
        rows.append(fresh)
    payload = {
        "schema": "eliza.adoption-queue/1",
        "note": ("One row per Kali module. `run` adopts a row by vendoring the tree "
                 "and importing the module in a subprocess; blocked rows name why."),
        "counts": {"rows": len(rows),
                   "shards": sum(len(row["shards"]) for row in rows)},
        "rows": rows,
    }
    QUEUE.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("queued %(rows)d module row(s) covering %(shards)d shard(s)" % payload["counts"])
    return 0


def read_queue() -> Dict:
    return json.loads(QUEUE.read_text(encoding="utf-8"))


def write_queue(payload: Dict) -> None:
    QUEUE.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")


def status() -> int:
    payload = read_queue()
    rows = payload["rows"]
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    wired = intake.wired_registry()
    adopted_shards = sum(len(row["shards"]) for row in rows if row["status"] == "done")
    print("rows: %d  shards: %d  ledger: %d wired"
          % (len(rows), payload["counts"]["shards"], len(wired)))
    for state in ("done", "blocked", "pending"):
        print("  %-8s %4d row(s), %4d shard(s)"
              % (state, counts.get(state, 0),
                 sum(len(row["shards"]) for row in rows if row["status"] == state)))
    print("  queue-adopted shards: %d (ledger has %d)" % (adopted_shards, len(wired)))
    blocked = [row for row in rows if row["status"] == "blocked"][:5]
    for row in blocked:
        print("  blocked: %s -- %s" % (row["module"], row["note"]))
    reasons: Dict[str, int] = {}
    for row in rows:
        if row["status"] != "blocked":
            continue
        note = row.get("note", "")
        key = note.split(":")[0] if note.startswith("ModuleNotFound") else note[:40]
        reasons[key] = reasons.get(key, 0) + 1
    for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1])[:8]:
        print("  %3d x %s" % (count, reason))
    return 0


CHECK_SNIPPET = r'''import json, sys, types
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import shards
MISSING = object()
for sid in sys.argv[2:]:
    try:
        entry = shards.describe(sid)
        stub = shards.load(sid)
        if getattr(stub, "WIRED", None) is not True:
            raise AssertionError("stub declares WIRED = %r" % (getattr(stub, "WIRED", None),))
        unit = stub.load()
        if entry["class"] is None:
            if not isinstance(unit, types.ModuleType):
                raise AssertionError("returned %r, expected a module" % (unit,))
        else:
            suffix = ("adopted/kali/" + entry["module"]).lower()
            owners = [m for m in list(sys.modules.values())
                      if getattr(m, "__file__", None)
                      and Path(m.__file__).as_posix().lower().endswith(suffix)]
            if not owners:
                raise AssertionError("no loaded module owns %s" % entry["module"])
            if not any(getattr(o, entry["class"], MISSING) is unit for o in owners):
                raise AssertionError("load() did not return %s.%s"
                                     % (entry["module"], entry["class"]))
            if isinstance(unit, type) and unit.__name__ != entry["class"]:
                raise AssertionError("class carries the name %r" % unit.__name__)
        print(json.dumps({"id": sid, "ok": True}), flush=True)
    except BaseException as error:
        print(json.dumps({"id": sid, "ok": False,
                          "error": ("%s: %s" % (type(error).__name__, error))[:200]}),
              flush=True)
'''


def check_shards(shard_ids: Sequence[str], batch: int = 40,
                 timeout: int = 300) -> Dict[str, Dict]:
    """Does every shard, through its stub, return the unit the atlas names?

    **In child processes, in batches.** Importing Kali code is executing it, and
    the in-process version of this check proved that the hard way: `CORE/
    sentinel_enforcer.py` wrote to `AppData\\AssistantLogs\\fusion.json` at
    import time and raised `PermissionError: CRITICAL: Unauthorized write` from
    inside a pytest run (measured 2026-11-03). A control that mutates the host, or
    that one rogue module can kill for the whole suite, is not a control.

    Batching keeps it affordable: ~29 children for all 1,152 shards instead of
    1,152 interpreters, and a child that dies still names every shard it had not
    yet reported.
    """
    report: Dict[str, Dict] = {}
    env = dict(os.environ)
    env.setdefault("AZAZAEL_ROOT", str(REPO / "adopted"))
    ids = list(shard_ids)
    for start in range(0, len(ids), batch):
        chunk = ids[start:start + batch]
        try:
            child = subprocess.run(
                [sys.executable, "-c", CHECK_SNIPPET, str(REPO), *chunk],
                cwd=str(REPO), capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            for shard_id in chunk:
                report[shard_id] = {"ok": False, "error": "batch exceeded %ds" % timeout}
            continue
        for line in (child.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                item = json.loads(line)
            except ValueError as error:
                print("unparseable child line (%s): %s" % (error, line[:120]),
                      file=sys.stderr)
                continue
            report[item["id"]] = {"ok": bool(item.get("ok")),
                                  "error": item.get("error", "")}
        missing = [shard_id for shard_id in chunk if shard_id not in report]
        for shard_id in missing:
            tail = (child.stderr or "").strip().splitlines()[-1:] or ["exit %d" % child.returncode]
            report[shard_id] = {"ok": False, "error": "child died: " + tail[0][:160]}
    return report


UNWIRED_TAIL = '''def load(*args, **kwargs):
    raise NotImplementedError(
        {reason!r} + " -- not adopted; see shards/ADOPTION_QUEUE.json")
'''


def _unwire(shard: Dict, reason: str) -> None:
    """Put a shard back to stub, with the reason it was taken back."""
    path = REPO / shard["path"]
    text = path.read_text(encoding="utf-8")
    head, _, _ = text.partition("def load(")
    head = head.replace("WIRED = True", "WIRED = False", 1)
    path.write_text(head + UNWIRED_TAIL.format(reason=reason),
                    encoding="utf-8", newline="\n")
    ledger = intake.wired_registry()
    ledger.pop(shard["shard_id"], None)
    intake.WIRED.write_text(json.dumps({
        "schema": intake.SCHEMA,
        "note": ("Shard id -> {test, commit}. A shard listed here has been wired "
                 "into ELIZA behind its stub path; the test is the evidence. "
                 "Edit by hand, in the adopting commit."),
        "wired": ledger,
    }, indent=1) + "\n", encoding="utf-8", newline="\n")


def verify() -> int:
    """Check every adopted shard through its stub, then demote what fails.

    The probe proves the module imports; this proves the *wire* is real -- the
    stub returns the object the atlas names, the ledger entry points at the
    control, and nothing on the way mutated the host into refusing the import.
    """
    payload = read_queue()
    adopted = [row for row in payload["rows"] if row["status"] == "done"]
    # The vendored ownership probe below only governs mode "vendored" rows.
    # Hand-ported rows (mode "adopted") keep their own mode and their own
    # control -- tests/test_adopted_event_bus.py asserts identity with the
    # adopted module -- and the module docstring's promise is that they are
    # never touched. Applying the vendored probe to them demoted a correct
    # adoption (measured 2026-11-03), so they are excluded here, exactly as
    # run() exempts wired rows.
    ledger = intake.wired_registry()
    ids = [shard["shard_id"] for row in adopted for shard in row["shards"]
           if ledger.get(shard["shard_id"], {}).get("mode") == "vendored"]
    report = check_shards(ids)
    bad = {shard_id: item for shard_id, item in report.items() if not item["ok"]}
    for row in adopted:
        failed = [shard for shard in row["shards"] if shard["shard_id"] in bad]
        if not failed:
            continue
        row["status"] = "blocked"
        row["note"] = "control failed: " + bad[failed[0]["shard_id"]]["error"]
        for shard in failed:
            _unwire(shard, row["note"])
    # A blocked row must not leave a wire behind: the ledger and the queue are two
    # records of one fact, and a row that failed *after* it was wired kept its
    # entry until this pass existed.
    ledger = intake.wired_registry()
    strays = 0
    for row in payload["rows"]:
        if row["status"] == "done":
            continue
        for shard in row["shards"]:
            if shard["shard_id"] in ledger:
                _unwire(shard, row.get("note") or "not adopted")
                strays += 1
    if strays:
        print("unwired %d stray shard(s) from rows that are not done" % strays)
    write_queue(payload)
    print("checked %d shard(s) through their stubs; %d failed and were demoted"
          % (len(ids), len(bad)))
    for shard_id, item in sorted(bad.items())[:6]:
        print("  %s -- %s" % (shard_id, item["error"][:110]))
    return status()


STDLIB = set(sys.stdlib_module_names)
FROM_LINE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)from +(?P<name>[A-Za-z_][\w.]*)(?= +import )")
IMPORT_LINE = re.compile(r"(?m)^(?P<indent>[ \t]*)import +(?P<body>[^\n#]+)")


def _candidate_roots(relative_dir: str) -> List[str]:
    """The package chain a bare name could resolve against, nearest first.

    Kali code writes `from core.arm_registry import ...` from `AOA/arms/`, where
    `core` is a **sibling** of `arms`, not a top-level name. Resolving only
    against the vendored root turned every such import into
    `ModuleNotFoundError: No module named 'core'` -- measured 2026-11-03, 6 of
    the first 20 rows blocked for exactly that reason. So each name is tried
    against the file's own directory, then each ancestor up to the root.
    """
    parts = [part for part in relative_dir.split("/") if part]
    return ["/".join(parts[:depth]) for depth in range(len(parts), -1, -1)]


def _resolves(root: str, name: str) -> bool:
    """Is `name` a module or package directly under `root` in the vendor tree?"""
    base = VENDOR / root if root else VENDOR
    package = base / name
    if package.is_dir() and (package / "__init__.py").is_file():
        return True
    return (base / (name + ".py")).is_file()


def _retarget(module: str, roots: Sequence[str]) -> Optional[str]:
    """Vendored path for a Kali module reference, or None to leave it alone.

    None means "this is not ours": stdlib, third-party, or a name that resolves
    nowhere in the tree. Inventing a target for those turns an honest
    ImportError into a wrong import, and a **stdlib name must never be
    retargeted**: `CORE/logging.py` starts with `import logging` meaning the
    standard library (its own docstring says it builds on it), and rewriting
    that to `adopted.kali.CORE.logging` made the module import *itself* -- a
    NameError cascading into every module that imported it, measured
    2026-11-03 as 256 blocked rows whose reasons all read
    `NameError: name 'logging' is not defined`.
    """
    head = module.split(".")[0]
    if head == "adopted" or head in STDLIB:
        return None
    for root in roots:
        if _resolves(root, head):
            # Split the module on its dots **then** prepend the root: joining
            # first and splitting after produced the single literal part
            # `AOA/core`, which resolved to nothing and silently dropped the
            # rewrite -- 7 rows regressed from adopted to `No module named
            # 'core'` (caught by `--verify`, 2026-11-03).
            parts = module.split(".")
            if root:
                parts = root.split("/") + parts
            real = _module_path([part for part in parts if part])
            if real is None:
                return None
            return "adopted.kali." + real.replace("/", ".")
    return None


def _normalise(text: str, relative_dir: str = "") -> str:
    """Point absolute imports of Kali names at the vendored copy of them.

    Two forms, and the difference is not cosmetic:

    * `from X import y` binds `y`, so prefixing `X` changes nothing visible.
    * `import X` binds **`X`**. Prefixing it to `import adopted.kali.X` binds
      `adopted`, and every later `X.something` raises NameError -- so the alias
      is emitted explicitly (`import adopted.kali.X as X`), and comma lists are
      rewritten segment by segment because only the first name matched a naive
      pattern while the rest stayed unresolvable.

    Any indent, because Kali imports inside function bodies as well as at module
    level.
    """
    roots = _candidate_roots(relative_dir)

    def from_sub(match: "re.Match[str]") -> str:
        target = _retarget(match.group("name"), roots)
        if target is None:
            return match.group(0)
        return "%sfrom %s" % (match.group("indent"), target)

    def import_sub(match: "re.Match[str]") -> str:
        segments: List[str] = []
        for segment in match.group("body").split(","):
            piece = segment.strip()
            if not piece:
                continue
            parts = piece.split(" as ")
            module, alias = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
            target = _retarget(module, roots)
            if target is None:
                segments.append(piece)
                continue
            # `import a.b` binds `a`, so the alias is the original head unless
            # the source already named one.
            segments.append("%s as %s" % (target, alias or module.split(".")[0]))
        return "%simport %s" % (match.group("indent"), ", ".join(segments))

    return IMPORT_LINE.sub(import_sub, FROM_LINE.sub(from_sub, text))


def vendor() -> int:
    """Mirror /root/azazael/src into adopted/kali and normalise its imports."""
    VENDOR.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(
        ["wsl.exe", "-d", "kali-linux", "--", "tar", "-C", _source_root(),
         "-cf", "-", "--exclude=__pycache__", "."],
        capture_output=True, check=True, timeout=600)
    subprocess.run(["tar", "-C", str(VENDOR), "-xf", "-"], input=tar.stdout,
                   check=True, timeout=600)
    (VENDOR / "__init__.py").write_text(
        '# coding: utf-8\n"""Verbatim Kali source, imports normalised by tools/adopt_queue.py.\n\n'
        "Vendored, not re-implemented: the units are the Kali code, reachable from\n"
        "ELIZA through `shards/<tree>/...load()`. Regenerate with `--vendor`; do not\n"
        'hand-edit -- a fix belongs in Kali and comes back through this step."""\n'
        "from __future__ import annotations\n", encoding="utf-8", newline="\n")
    changed = 0
    for path in VENDOR.rglob("*.py"):
        original = path.read_text(encoding="utf-8", errors="replace")
        relative_dir = path.parent.relative_to(VENDOR).as_posix()
        relative_dir = "" if relative_dir == "." else relative_dir
        normalised = _normalise(original, relative_dir)
        if normalised != original:
            path.write_text(normalised, encoding="utf-8", newline="\n")
            changed += 1
    _link_src()
    print("vendored %d module(s) from %s; normalised %d"
          % (sum(1 for _ in VENDOR.rglob("*.py")), _source_root(), changed))
    return 0


def _link_src() -> None:
    """Expose the vendored tree as `adopted/src`, the layout Kali expects.

    Kali code asserts `<root>/src/CORE` exists before it will run. The vendored
    `kali/` directory is that `src`, so a directory junction closes the gap on
    Windows (git cannot store one; `.gitignore` holds it out of the tree and
    `--vendor` recreates it, which is what makes this reproducible rather than
    a step someone has to remember).
    """
    link = REPO / "adopted" / "src"
    if (link / "CORE").is_dir():
        return
    if link.exists():
        return
    try:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(VENDOR)],
                       capture_output=True, check=True, timeout=30)
    except (OSError, subprocess.CalledProcessError) as error:
        print("could not link adopted/src (%s); root-detecting modules will block"
              % error, file=sys.stderr)


def _probe(dotted: str, timeout: int = 20) -> Optional[str]:
    """Import the module in a child process. None on success, a reason otherwise."""
    env = dict(os.environ)
    # Kali's CORE/paths/internal.py resolves the project root and then demands
    # that <root>/src/CORE exists (strategy 1 is exactly this variable). The
    # vendored `kali/` tree IS Kali's `src`, and `vendor()` lands it at
    # `adopted/src`, so 13 rows stopped dying on
    # `RuntimeError: Project root detection failed` (measured 2026-11-03).
    env.setdefault("AZAZAEL_ROOT", str(REPO / "adopted"))
    try:
        done = subprocess.run(
            [sys.executable, "-c", "import %s" % dotted],
            cwd=str(REPO), capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return "import exceeded %ds" % timeout
    if done.returncode == 0:
        return None
    lines = [line for line in (done.stderr or "").strip().splitlines() if line.strip()]
    return (lines[-1] if lines else "exit %d" % done.returncode)[:200]


def _wire(row: Dict) -> None:
    ledger = intake.wired_registry()
    for shard in row["shards"]:
        path = REPO / shard["path"]
        text = path.read_text(encoding="utf-8")
        head, _, _ = text.partition("def load(")
        head = head.replace("WIRED = False", "WIRED = True", 1)
        path.write_text(head + LOAD_TAIL.format(dotted=_dotted(row["module"])),
                        encoding="utf-8", newline="\n")
        ledger[shard["shard_id"]] = {"test": SHARED_TEST,
                                     "commit": "vendored", "mode": "vendored"}
    intake.WIRED.write_text(json.dumps({
        "schema": intake.SCHEMA,
        "note": ("Shard id -> {test, commit}. A shard listed here has been wired "
                 "into ELIZA behind its stub path; the test is the evidence. "
                 "Edit by hand, in the adopting commit."),
        "wired": ledger,
    }, indent=1) + "\n", encoding="utf-8", newline="\n")


def run(limit: int, retry_blocked: bool = False) -> int:
    if not VENDOR.is_dir():
        print("no vendored tree; run --vendor first", file=sys.stderr)
        return 2
    payload = read_queue()
    done = 0
    for row in payload["rows"]:
        if done >= limit:
            break
        if row["status"] == "done":
            continue
        if row["status"] == "blocked" and not retry_blocked:
            continue
        dotted = _dotted(row["module"])
        if not (VENDOR / row["module"]).is_file():
            row["status"], row["note"] = "blocked", "module absent from vendored tree"
            continue
        row["attempts"] = row.get("attempts", 0) + 1
        started = time.time()
        reason = _probe(dotted)
        if reason is None:
            _wire(row)
            row["status"] = "done"
            row["note"] = "vendored; imported in %.1fs" % (time.time() - started)
        elif row["status"] != "done":
            row["status"] = "blocked"
            row["note"] = reason
        done += 1
        write_queue(payload)          # durable per row: a crash costs one row
    write_queue(payload)
    print("processed %d row(s)" % done)
    return status()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--vendor", action="store_true")
    parser.add_argument("--run", type=int, metavar="N")
    parser.add_argument("--retry-blocked", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.build:
        return build()
    if args.vendor:
        return vendor()
    if args.run is not None:
        return run(args.run, args.retry_blocked)
    if args.verify:
        return verify()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
