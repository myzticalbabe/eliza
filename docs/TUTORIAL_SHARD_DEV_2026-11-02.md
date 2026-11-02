# Tutorial: adopting a Kali shard into ELIZA

You have 1,183 shards covering all 1,274 classes the Kali lane's atlas counts:
1,131 units named individually, plus 52 *residual* shards standing for the 143
classes the atlas lists only as a count. None of them runs. This walks one from
"I wonder what that is" to "it is wired, tested and in the ledger", using the
commands that actually exist.

Audience: a developer who knows Python and this repository, and has not read the
surface before. Time: 20–60 minutes for a small unit, longer for anything that
touches the file system.

---

## Step 0 — see what is there

```bash
cd Project_ELIZA
python tools/shard_intake.py --list
```

```
(root)                    109 shard(s)
AOA                        30 shard(s)
AZAZAEL_TOOLKIT             7 shard(s)
CLI                         1 shard(s)
CODEX                      46 shard(s)
CORE                      574 shard(s)
DAEMONS                     1 shard(s)
HYDRA                      12 shard(s)
INTERPRETERS                6 shard(s)
META                       58 shard(s)
ML                          4 shard(s)
ORCHESTRATION             210 shard(s)
SCRIPTS                    13 shard(s)
TOOLS                       9 shard(s)
UTILITIES                  40 shard(s)
eve_unleashed              15 shard(s)
scripts                    13 shard(s)
tests                      35 shard(s)
total                    1183
```

Two entries look like duplicates: `SCRIPTS` and `scripts`. They are not — the
Kali atlas is case-sensitive and both trees exist there. On Windows their files
cannot share a directory, so the colliding shard keeps a hashed name. See §5 of the
whitepaper before you decide this is a bug.

Narrow it:

```bash
python tools/shard_intake.py --list --tree CORE
```

One entry in that list is not a class. A shard whose id ends `#module` (for
example `kali:CORE/config.py#module`) is a **residual**: the atlas counts nine
classes in `CORE/config.py` but names only six, so the seventh through ninth have
no identifier to stub. The residual shard says so in its own header and carries
`CLASS_NAME = None`, `UNNAMED_CLASSES = 9`. Adopting it means adopting the module
and deciding, from the source, which class you actually wanted.

## Step 1 — read the provenance before the code

```bash
python tools/shard_intake.py --adopt "kali:UTILITIES/PERSEPHONE/persephone.py#PathTranslator"
```

```
Adopt plan for kali:UTILITIES/PERSEPHONE/persephone.py#PathTranslator
  source   kali-linux UTILITIES/PERSEPHONE/persephone.py (class PathTranslator)
  stub     shards/utilities/utilities_persephone_persephone__pathtranslator.py
  steps
    1. read the Kali source; list its imports and its side effects
    ...
```

Or from Python, without importing anything:

```python
import shards
shards.describe("kali:UTILITIES/PERSEPHONE/persephone.py#PathTranslator")
# {'shard_id': ..., 'kind': 'class', 'tree': 'UTILITIES',
#  'module': 'UTILITIES/PERSEPHONE/persephone.py', 'class': 'PathTranslator',
#  'unnamed': 0, 'path': 'shards/utilities/...', 'wired': False, 'test': None,
#  'source_environment': 'kali-linux'}
```

`wired` is read from `shards/WIRED.json`, not assumed: adopt the shard in step 5
and the same call starts returning `wired: True` with the test that backs it.

`wired: False` is not decoration. It means the only thing you can get from this
shard today is the sentence its `load()` raises:

```python
shards.load("kali:UTILITIES/PERSEPHONE/persephone.py#PathTranslator").load()
# NotImplementedError: shard kali:... is an intake stub: PathTranslator is not
# implemented in ELIZA. Read the Kali source at UTILITIES/PERSEPHONE/persephone.py,
# then see docs/TUTORIAL_SHARD_DEV_2026-11-02.md
```

## Step 2 — read the Kali source, and write down what it drags

Open the module **on the Kali lane** (`/root/azazael/src/UTILITIES/PERSEPHONE/
persephone.py`). Before writing a line, answer four questions in the adopting
issue or commit message:

1. **Imports.** What does it need that ELIZA does not have? `pyproject.toml` says
   `dependencies = []` deliberately; every addition is a decision, not a detail.
2. **Side effects at import.** Does it read the environment, open a file, start a
   thread, bind a socket, or print? Anything that happens at import time will
   happen to every consumer.
3. **Path assumptions.** Does it assume POSIX separators, `/root`, a venv, or a
   case-sensitive tree? This is how a port acquires a Windows-only bug.
4. **What is the minimum useful slice?** A 587-line module with nine classes
   usually has one class that does the work you want. Adopt that shard, not the
   module.

## Step 3 — write the failing test first

The adoption ledger records a test, so the test is part of the deliverable rather
than an afterthought. In `tests/test_<unit>.py`:

```python
def test_path_translator_maps_a_posix_path_to_windows():
    from eliza.paths.translator import translate
    assert translate("/root/azazael/src") == "C:/Azazael/azazael/src"
```

Run it. It must fail because the module does not exist — not because of an import
typo. A test that fails for the wrong reason proves nothing and is how a wired
shard ships unverified.

## Step 4 — implement behind the stub path

Two shapes are allowed, and the second is preferred:

**Implement in the stub's own module.** Set `WIRED = True`, and make `load()`
return the implementation object. Use this when the unit is small and the stub
path is a sensible home.

**Or implement in a proper module** (`eliza/paths/translator.py`) and have the
stub's `load()` return it. Use this when the unit needs neighbours, or when the
shard path is an awkward public name. The stub then documents a mapping, and the
index still answers "where did this come from".

Either way: the stub's provenance constants (`SHARD_ID`, `SOURCE_MODULE`,
`CLASS_NAME`) stay. They are what connects the ELIZA code to the Kali original for
the next reader.

## Step 5 — record the adoption

`shards/WIRED.json` is the only file here a human edits:

```json
{
  "wired": {
    "kali:UTILITIES/PERSEPHONE/persephone.py#PathTranslator": {
      "test": "tests/test_path_translator.py",
      "commit": "<sha of the adopting commit>"
    }
  }
}
```

Fill `commit` with the commit that does the wiring. It is provenance, and the
ledger is read by people, not only by the gate.

## Step 6 — run the gate

```bash
python tools/shard_intake.py --check
python -m pytest tests/test_shard_intake.py -q
```

`--check` must report `clean` with your shard counted as wired. Four things can
fail here, and each has one cause:

| message | cause | fix |
| --- | --- | --- |
| `is listed as wired in WIRED.json but declares WIRED = False` | you edited the ledger before the module, or regenerated over your edit | set `WIRED = True` in the stub |
| `load() does not raise: a stub that returns is a fake` | an unwired stub returns a value | either finish the adoption (add the ledger entry) or restore the file with `--write` |
| `WIRED.json entry ... names '...', which does not exist` | the test path is wrong or the test is not written yet | write the test; the ledger entry is a claim needing a control |
| `imports 'requests'` | a stub grew a dependency | move the implementation into a module and let the stub import it, or ask whether ELIZA wants that dependency at all |

If you hand-edited a generated stub and want the text back:
`python tools/shard_intake.py --write` restores every unwired stub and the index.
It never touches `WIRED.json`.

## Step 7 — go back if it does not fit

Reversing an adoption is three edits: delete the ledger entry, delete or revert
the implementation, `--write` to restore the stub. Nothing else in the surface
depended on your choice, which is the property that makes 1,183 units adoptable
without a migration plan.

---

## Worked example: a small unit, end to end

Target: `kali:AOA/core/event_bus.py#EventBus` (98-line module, five named units).

```bash
python tools/shard_intake.py --adopt "kali:AOA/core/event_bus.py#EventBus"
sed -n 1,40p shards/aoa/aoa_core_event_bus__eventbus.py   # the stub
```

Reading the Kali module shows a small pub/sub with no third-party imports and no
import-time side effects — the good case. The five named units are the bus itself,
an event, an event type, a pipeline and a priority enum; adopting `EventBus` alone
would strand its four collaborators, so the honest slice is the module.

```bash
# the failing test first
$EDITOR tests/test_event_bus.py
python -m pytest tests/test_event_bus.py -q        # fails: no module
```

Implement in `eliza/events/bus.py`, point all five stubs' `load()` at it, set
`WIRED = True` in the five files, add five ledger entries — three tests, one
ledger, five filenames, and `--check` proves the surface still matches the atlas.

## Troubleshooting

- **`atlas not found`** — `--atlas PATH` or regenerate the atlas on the Kali lane
  with `python tools/domain_trees.py`. The default is
  `~/yggdrasil_forest/atlas_kali-linux.json`.
- **`no shard '...' in the atlas`** — the id is `kali:<module path>#<ClassName>`.
  `--list` shows what exists; the command prints the closest matches.
- **`is indexed but absent`** — run `--write`. A stub that was deleted by hand is
  not a state the surface supports.
- **`is in the index but not the atlas (stale stub)`** — the atlas moved and the
  surface has not. `--write` regenerates from the current atlas; check what
  disappeared before you do.
- **A unit you need is not listed by name** — check its module for a `#module`
  residual shard first (the class is counted but unnamed; §2 of the whitepaper).
  If the module has no shard at all, it either declares no class — 279 modules,
  1,785 functions, outside this surface's unit — or belongs to a tree the census
  did not include. Ask for the atlas, not for a guessed stub.

## Rules for this surface, in one paragraph

Stubs are generated; never hand-edit one except to adopt it. `SHARD_INDEX.json` and
the unwired stubs are regenerated freely and carry no history. `WIRED.json` is
hand-written, is the only place a shard changes state, and every entry needs a
test that exists. Nothing in ELIZA's runtime imports a stub. If you find yourself
copying a file out of Kali into `eliza/`, stop: that is the option this surface was
built to replace.
