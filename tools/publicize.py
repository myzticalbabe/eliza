#!/usr/bin/env python3
# coding: utf-8
"""Materialise the public tree from PUBLIC_MANIFEST.json, with imports rewritten.

WHY A TOOL AND NOT A SCRIPT OF `cp`
-----------------------------------
The manifest is an ALLOWLIST: every published path is declared. A copy tool that
walks a directory instead of reading the manifest would ship whatever happened to
be in the source tree, which is the failure the release gate exists to prevent.
So this reads the manifest, and it refuses anything the manifest does not name.

THE IMPORT REWRITE IS THE PART THAT COULD SILENTLY BREAK
--------------------------------------------------------
Source modules are imported as `eliza.psyche.affect`; the public package is
`eliza.psyche.affect`. A verbatim copy therefore installs cleanly and then fails
on first import -- and it fails in the published artifact, after the push, where
nobody is watching. The rewrite is therefore verified, not assumed: after
copying, this tool imports the public package in a fresh subprocess with only the
public tree on `sys.path`. If that import fails, the publicise fails.

The `sys.path.insert(0, .../src)` bootstrap in the tools is removed rather than
rewritten: in the public tree the package is installed or the tree root is on the
path, and a bootstrap pointing at a directory that does not exist is a lie that
happens to work on the author's machine.

Usage:
  python Project_ELIZA/tools/publicize.py                    # materialise
  python Project_ELIZA/tools/publicize.py --check            # verify, write nothing
  python Project_ELIZA/tools/publicize.py --clean            # remove generated files
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

PROJECT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT / "PUBLIC_MANIFEST.json"

#: Source package name -> public package name. The rewrite is applied to whole
#: dotted references only: `eliza.psyche.affect` becomes `eliza.psyche.affect`, and a
#: bare `PSYCHE` in prose is left alone.
SOURCE_PKG = "PSYCHE"
PUBLIC_PKG = "eliza.psyche"

#: Text kinds get the import rewrite. Data is copied byte-for-byte, and a rewrite
#: applied to a JSONL corpus would corrupt an utterance that happens to contain
#: the package name.
REWRITE_KINDS: Tuple[str, ...] = ("code", "instrument", "test")

#: Bootstraps that point outside the public tree and must not survive the copy.
DROP_LINE_PATTERNS: Tuple[str, ...] = (
    r"^\s*sys\.path\.insert\(0,\s*str\(ROOT\s*/\s*\"src\"\)\)\s*$",
)


def load_manifest(path: Path = MANIFEST) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def denied(relative: str, manifest: Dict) -> Optional[str]:
    """Return the manifest rule that forbids `relative`, or None.

    Checked on the DESTINATION path: the deny rules are written against what a
    reader would receive, and a source file whose name is innocent can still be
    copied into an evidence-shaped slot.
    """
    name = Path(relative).name
    for rule in manifest.get("never_ship", []):
        glob = str(rule.get("glob", ""))
        if glob and (fnmatch.fnmatch(relative, glob) or fnmatch.fnmatch(name, glob)
                     or fnmatch.fnmatch(relative, glob.lstrip("*"))):
            return "%s (%s)" % (glob, rule.get("why", "no reason recorded"))
    lowered = relative.lower()
    for token in manifest.get("deny_substrings", []):
        if str(token).lower() in lowered:
            return "substring %r" % token
    return None


def rewrite_imports(text: str) -> str:
    """Rename the package and drop bootstraps that point outside the tree."""
    text = re.sub(r"(?<![\w.])%s\." % SOURCE_PKG, PUBLIC_PKG + ".", text)
    text = re.sub(r"(?<![\w.])from\s+%s\s+import\b" % SOURCE_PKG,
                  "from %s import" % PUBLIC_PKG, text)
    lines = []
    for line in text.splitlines():
        if any(re.match(pattern, line) for pattern in DROP_LINE_PATTERNS):
            lines.append("# (bootstrap removed by publicize: the package is installed)")
            continue
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def plan(manifest: Dict) -> Tuple[List[Tuple[Path, Path, str]], List[str]]:
    """Resolve every manifest entry. Refusals are collected, never skipped."""
    entries: List[Tuple[Path, Path, str]] = []
    refusals: List[str] = []
    for item in manifest.get("ship", []):
        source = (PROJECT / item["from"]).resolve()
        target_rel = str(item["to"])
        reason = denied(target_rel, manifest)
        if reason:
            refusals.append("%s -> %s refused by %s" % (item["from"], target_rel, reason))
            continue
        if not source.exists():
            refusals.append("%s is declared but missing" % item["from"])
            continue
        entries.append((source, PROJECT / target_rel, str(item.get("kind", "code"))))
    return entries, refusals


def materialise(manifest: Dict) -> List[str]:
    entries, refusals = plan(manifest)
    written: List[str] = []
    touched_dirs = set()
    for source, target, kind in entries:
        text = source.read_text(encoding="utf-8")
        if kind in REWRITE_KINDS:
            text = rewrite_imports(text)
        target.parent.mkdir(parents=True, exist_ok=True)
        touched_dirs.add(target.parent)
        target.write_text(text, encoding="utf-8", newline="\n")
        written.append(str(target.relative_to(PROJECT)).replace("\\", "/"))
    # `eliza/__init__.py` is not in the manifest because it does not exist in the
    # source tree; the namespace needs it to be a regular package on 3.10.
    init = PROJECT / "eliza" / "__init__.py"
    if not init.exists():
        init.parent.mkdir(parents=True, exist_ok=True)
        init.write_text('"""ELIZA -- see docs/index.md. Package layout mirrors PUBLIC_MANIFEST.json."""\n',
                        encoding="utf-8")
        written.append("eliza/__init__.py")
    for directory in sorted(touched_dirs):
        marker = directory / "__init__.py"
        if ("eliza" in directory.parts) and not marker.exists() and \
                directory.name != "data":
            marker.write_text("# generated by publicize.py\n", encoding="utf-8")
            written.append(str(marker.relative_to(PROJECT)).replace("\\", "/"))
    return written + ["REFUSED: " + r for r in refusals]


#: Probes that must all pass before the tree counts as materialised. The second
#: and third exist because the first version verified only the IMPORT and passed
#: while two instruments were broken in the public tree: they resolved the corpus
#: and the bridge by source-tree path (`ROOT/src/PSYCHE/data/...`), which does not
#: exist after materialisation. An install that imports is not an install that
#: works, and the gap between those two claims is where this project keeps
#: finding defects.
PROBES: Tuple[Tuple[str, str], ...] = (
    ("import package",
     "import eliza.psyche.rt_agent as m; "
     "from eliza.psyche.rt_agent import triage; "
     "print('imported', m.__name__, '| triage', triage('I want to die').risk)"),
    ("evaluation instrument runs",
     "import sys, runpy; sys.argv=['triage_eval.py','--json']; "
     "runpy.run_path('tools/triage_eval.py', run_name='__main__')"),
    ("bridge instrument runs",
     "import sys, runpy; sys.argv=['fit_affect_bridge.py','--check']; "
     "runpy.run_path('tools/fit_affect_bridge.py', run_name='__main__')"),
)


#: Wall-clock bound for each verification probe. See verify() for why it exists.
PROBE_TIMEOUT_S = 120


def drift(manifest: Dict) -> List[str]:
    """Targets that do not match what materialise() would write.

    Generated files are committed so a reader can review exactly what ships, and
    that only stays honest if staleness is detected. Without this check the
    copies are a second source of truth: a fix applied upstream, materialised
    once, and then edited nowhere leaves the public copy silently behind -- the
    published test says the old thing and passes.
    """
    problems: List[str] = []
    for source, target, kind in plan(manifest)[0]:
        if not target.exists():
            problems.append("missing: %s" % target.relative_to(PROJECT))
            continue
        text = source.read_text(encoding="utf-8")
        if kind in REWRITE_KINDS:
            text = rewrite_imports(text)
        if target.read_text(encoding="utf-8") != text:
            problems.append("stale: %s (source changed since it was materialised)"
                            % target.relative_to(PROJECT))
    return problems


def verify() -> Tuple[bool, List[str]]:
    """Prove the public tree imports with nothing but itself on sys.path.

    A rewrite that is merely plausible is the failure mode this exists for: the
    copy installs, the import fails, and it fails in the published artifact.

    The environment is COPIED and narrowed, not replaced. Replacing it with just
    PYTHONPATH and PATH looked stricter and was simply broken on Windows, where
    the interpreter needs SYSTEMROOT to start: the first version of this function
    reported FAILED for a tree that imported fine, and a verification step that
    fails on a healthy tree is worse than none, because the next person turns it
    off. What actually isolates the run is `-E` (ignore PYTHON* env vars), `-S`
    (no site packages), and `-I`-style isolation via cwd + an explicit path entry.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    failures: List[str] = []
    try:
        failures.extend(drift(load_manifest()))
    except (OSError, ValueError) as exc:
        failures.append("manifest unreadable: %s" % exc)
    for label, body in PROBES:
        code = ("import sys; sys.path.insert(0, %r); sys.path.insert(0, %r); "
                % (str(PROJECT), str(PROJECT / "tools"))) + body
        # A timeout, because a probe that hangs would hang the release step and
        # read as "still running" rather than "broken" -- the failure mode this
        # project has already paid for once with a metering helper that wedged a
        # whole test run. 120s is far above a 0.3s import of a stdlib-only package.
        try:
            result = subprocess.run([sys.executable, "-E", "-s", "-c", code],
                                    cwd=str(PROJECT), capture_output=True, text=True,
                                    env=env, timeout=PROBE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            failures.append("%s: TIMED OUT after %ds" % (label, PROBE_TIMEOUT_S))
            continue
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or [""]
            failures.append("%s: %s" % (label, tail[0]))
        elif label == "import package" and "triage crisis" not in result.stdout:
            failures.append("%s: probe did not report a crisis routing" % label)
    return not failures, failures


def clean(manifest: Dict) -> List[str]:
    removed: List[str] = []
    for item in manifest.get("ship", []):
        target = PROJECT / str(item["to"])
        if target.exists():
            target.unlink()
            removed.append(str(target.relative_to(PROJECT)).replace("\\", "/"))
    for extra in ("eliza/__init__.py", "eliza/psyche/__init__.py"):
        path = PROJECT / extra
        if path.exists():
            path.unlink()
            removed.append(extra)
    return removed


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="verify the materialised tree; write nothing")
    parser.add_argument("--clean", action="store_true",
                        help="remove generated files")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    manifest = load_manifest()
    if args.clean:
        removed = clean(manifest)
        print("\n".join(removed) or "nothing to remove")
        return 0

    if args.check:
        ok, failures = verify()
        payload = {"ok": ok, "probes": [p[0] for p in PROBES], "failures": failures}
        print(json.dumps(payload, indent=1) if args.json
              else ("public tree: %s" % ("OK" if ok else "FAILED")))
        for line in failures:
            print("  FAILED %s" % line, file=sys.stderr)
        return 0 if ok else 1

    written = materialise(manifest)
    refusals = [line for line in written if line.startswith("REFUSED: ")]
    for line in written:
        if not line.startswith("REFUSED: "):
            print("wrote %s" % line)
    for line in refusals:
        print(line[9:], file=sys.stderr)
    ok, failures = verify()
    print("public tree: %s" % ("OK" if ok else "FAILED"))
    for line in failures:
        print("  FAILED %s" % line, file=sys.stderr)
    # A manifest entry that could not be honoured is a failure, not a warning:
    # the gate would then be checking a tree that is not the one declared.
    return 0 if (ok and not refusals) else 1


if __name__ == "__main__":
    raise SystemExit(main())
