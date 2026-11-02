# The shard substrate: the whole Kali class surface (1,274 classes, 1,183 stubs), addressable from ELIZA, wired by decision

**Status:** built and gated, 2026-11-02. Surface at `shards/` — a tracked sibling
of `eliza/`, which `tools/publicize.py` generates and `--clean` deletes — with the
generator at `tools/shard_intake.py` and the gate at
`python tools/shard_intake.py --check`.

---

## 1. The problem this solves

The Kali lane holds code that ELIZA cannot see. It is not that the code is secret:
it is that the two environments have different roots, different venvs and
different file systems, and "use the Kali version" had no addressable form. In
practice that meant three bad options — copy a module and inherit its imports and
side effects, re-implement from memory and lose the source, or leave the
capability unmentioned so the next developer never learns it was an option.

An inventory fixes that without claiming more than it can prove. It says: **these
units exist, here is where each one comes from, and none of them runs until
someone decides it should.** That is the whole design.

## 2. What is actually in the atlas

`atlas_kali-linux.json` is a census of `/root/azazael/src` produced by
`tools/domain_trees.py` on 2026-10-31. The figures below are read from that file,
not remembered:

| measure | value | what it means |
| --- | --- | --- |
| trees | 18 | top-level limbs of the Kali source root |
| modules | 679 | `.py` files with a parse |
| lines | 273,425 | of Python |
| classes | 1,274 | total, including nested and private |
| public named classes | 1,249 | the parser's public count |
| **named units** | **1,131** | what `top_classes` lists individually — at most six per module |
| residual units | 52 | modules holding classes the list truncates, one shard each |
| **stubs written** | **1,183** | one per named unit plus one per residual module |
| parse failures | 0 | every module in the census parsed |

The 143-class gap between 1,274 and 1,131 is the atlas's honesty about
granularity: `top_classes` records the classes a module presents, capped at six,
and a class nested two levels deep inside another may be counted in the total
without being named. **A shard must be a name** — inventing one for a unit the
census did not record would be the exact defect this estate keeps paying for. But
omitting the unit entirely would hide a real module from the surface, so the 52
truncated modules get one *residual* shard apiece: `CLASS_NAME = None`,
`UNNAMED_CLASSES = 9`, and a docstring that says read the module rather than
trust the six names.

That is how a surface becomes complete without becoming a liar. Every class the
atlas counts is reachable — 1,131 by name, 143 through their module's residual
shard — and no shard claims to know a name the census never wrote down. Measured:
`named + residual = 1,131 + 143 = 1,274`, asserted by
`test_every_class_the_atlas_counts_is_reachable_through_a_shard`.

So: 1,183 shards drawn from 400 of the 679 modules. The other 279 modules declare
functions and constants and no class at all (1,785 functions between them); they
are in the atlas and reachable through it, and they are deliberately not sharded,
because the shard unit here is a class. `top_funcs` exists in the atlas if that
boundary ever needs moving — moving it is a decision, not a regeneration.

## 3. Why stubs and not copies

Three reasons, in order of how much they cost when ignored.

**A copy drags.** A copied module brings its imports, its module-level globals,
its file-system assumptions, and its licence into a package whose `pyproject.toml`
says `dependencies = []` and Apache-2.0. None of that is visible at the import
site, and none of it is reviewed at the moment it arrives.

**A copy rots silently.** There would be no way to answer "is this still what
Kali has?" without diffing two trees on two hosts, so nobody would. A generated
stub carries its source module and atlas date, and `--check` re-derives the whole
surface from the atlas. Drift is a failure, not a discovery.

**A copy pretends.** The failure mode this estate has recorded most often is a
capability that reads as present and does nothing. A stub cannot do that: it
declares `WIRED = False`, and `load()` raises with the shard id, the class and the
document to read next. Importing one to get behaviour produces a sentence, not a
silent zero.

## 4. The contract

Every stub is generated from one template and holds exactly this:

```python
WIRED = False
SHARD_ID = "kali:CORE/paths.py#Paths"      # environment:module#unit
KIND = "class"                             # or "module" for a residual
SOURCE_MODULE = "CORE/paths.py"
CLASS_NAME = "Paths"                       # None on a residual shard
UNNAMED_CLASSES = 0                        # >0 on a residual shard
TREE = "CORE"

def describe() -> dict: ...                # provenance, and wired: False
def load(*args, **kwargs): ...             # raises NotImplementedError, with why
```

`SHARD_INDEX.json` records, per shard, the id, kind, tree, module, class, module
length, public API count, unnamed-class count and stub path — plus the atlas it
came from, so a reader can tell which census produced the surface.

`--check` is the gate, and it asserts four things:

1. **Set equality.** Every atlas unit has an indexed stub and no stub exists that
   the atlas does not name. A stale stub is a name with no referent.
2. **Identity.** Each stub's `SHARD_ID` and `CLASS_NAME` match the index entry.
3. **Inertness.** An unwired stub declares `WIRED = False` and its `load()` body
   raises. A stub that returns a value is a fake, and the check says so in that
   word.
4. **No dependencies.** Stubs import nothing but `__future__`. A stub that imports
   `requests` is a copy wearing a stub's clothes.

The adoption ledger `WIRED.json` is the one hand-written file in the directory,
and it is where state change happens: a shard listed there must declare
`WIRED = True` and name the test that proves it. The gate knows both states, so
adoption is allowed and cannot be faked.

## 5. A finding that changed the design

The first run reported 1,131 shards written and 1,118 present. Kali carries both
`SCRIPTS/` and `scripts/` — the atlas is case-sensitive, Windows is not, and the
lowercase tree overwrote the uppercase one's files. Thirteen units vanished with
no error at all, which is the shape of failure this whole estate is built to
refuse.

The repair is not a warning. A path collision now gets a content-addressed suffix
derived from the shard id, and `--check` verifies that no two shards share a path
**compared case-insensitively**. The general lesson is worth more than the fix: an
inventory produced on one file system and read on another may not depend on case,
and the gate must therefore test the weaker of the two invariants.

## 6. What "optional development at will" means, operationally

- **Zero coupling.** Nothing in `eliza/` imports `shards` in a code path that runs
  the therapeutic loop. The surface is a catalogue; its `__init__` exposes
  `index()`, `trees()`, `find()`, `describe()`, `load()` and `unwired()`, and no
  module below it is imported until one of those is called.
- **Individually adoptable.** Adopting one shard touches one stub, one entry in
  `WIRED.json` and one test. It does not require adopting the tree, the module or
  the neighbour. A residual shard is the coarser step: adopting it means the
  module, and its first review question is which of its unnamed classes you
  actually want.
- **Reversible.** A wired shard that turns out to be a bad fit goes back to a stub
  by removing its `WIRED.json` entry and restoring the generated file — which is a
  `--write` away, because the generator is the source of truth for stubs and the
  ledger only ever adds claims.

## 7. Limits — the part that keeps this honest

- **A stub is not a port.** It is a name and a provenance. The Kali code has not
  been executed here, its behaviour is unverified, and adopting a shard is the
  beginning of work rather than a retrieval of it.
- **The atlas is a census, not a contract.** It records what parsed on 2026-10-31.
  A module deleted from Kali afterwards stays in the surface until the atlas is
  regenerated, and `--check` will keep passing because it compares the surface to
  the atlas, not to Kali itself. Regenerating the atlas is a separate, deliberate
  act on the Kali lane.
- **Unnamed classes are reachable, not enumerable.** The 143 classes behind the 52
  residual shards have an address and a count, not a name. If one of them matters,
  the remedy is a better atlas (raise the `top_classes` cap and regenerate on the
  Kali lane), not a guessed identifier here.
- **Functions are not sharded.** 279 class-free modules hold 1,785 functions and
  appear in no stub. They are outside the unit this surface chose, and the atlas
  does carry `top_funcs` if a future pass decides otherwise.
- **Names are not designs.** `SessionManager` in ELIZA and `SessionManager` in Kali
  are related by origin and nothing else until someone reads both.

## 8. What would falsify this design

- A production import path in `eliza/` that reaches a stub → the surface stopped
  being optional; revert the import.
- `SHARD_INDEX.json` edited by hand → the generator is no longer the source of
  truth, and `--check` should fail on the next write.
- A stub whose `load()` returns a value while absent from `WIRED.json` → the
  inertness claim is broken, and the gate reports it as a fake.
- Two shards resolving to one path → the case-collision defect has returned on a
  third file system.

## 9. Reproducing

```bash
python tools/shard_intake.py --list               # 1,183, by tree
python tools/shard_intake.py --write              # regenerate stubs + index
python tools/shard_intake.py --check              # the gate
python tools/shard_intake.py --adopt "kali:CORE/paths.py#Paths"   # the plan for one unit
python -m pytest tests/test_shard_intake.py -q    # the controls, including fakes
```

Measured on 2026-11-02: `clean -- 1183 shard(s), 400 module(s) yielding units,
18 tree(s), 0 wired`; 12 controls passing.
