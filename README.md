# Project ELIZA

**BCC RE-INVESTIGATION MACHINERY — PUBLIC, FULLY EXECUTABLE.**

A therapeutic agent that is honest about what it cannot do, plus the instruments
that prove it.

Named for Weizenbaum's 1966 program, which was a parody of a therapist and was
nevertheless trusted by the people who used it. That is the cautionary tale this
project is built around: a system that sounds like it is listening will be
believed, whether or not anything underneath is doing the work. So the deliverable
here is not a chatbot. It is a **loop with receipts** — a person's psychological
state modelled as an editable graph, a fast path that can be graded against a slow
one, and a safety branch that runs before any other decision and cannot be
outvoted.

## What this is

Four layers, each in dependency order, each able to be run and measured alone:

| layer | module | what it does | measured |
|---|---|---|---|
| persona | `eliza/psyche/traits.py`, `affect.py` | 6-domain trait vector, PAD state, OCC appraisal | 45 evaluated constants, invariance tested |
| network | `eliza/psyche/network.py` | constructs as nodes, ridge-shrunk **partial correlations** as edges, one GNN message-passing layer | planted dependency recovered at pcorr **+0.352** over 120 observations |
| intuition | `eliza/psyche/intuition.py` | repeated evaluation **compiled** into prototypes with support counts | **8.5 µs** fast vs **148.2 µs** deliberate, same answer |
| loop | `eliza/psyche/rt_agent.py`, `rt_channel.py` | JITAI turn: sense → triage → stance → deliver, over a line protocol | 200 turns, median **0.025 ms** against a 50 ms budget |

**BCC RE-INVESTIGATION EXTENSION (NEW):**

| layer | module | what it does | measured |
|---|---|---|---|
| bypass | `tools/bcc_bypass.py` | Engineered web bypass chain: HTTP → curl_cffi → headless browser → archive replay | UJS, DOS, ProPublica, campaign finance, press — all public records |
| ultra-loose | `tools/ultra_loose.py` | FLOCK-CANON-v1.3 ultra-loose source tutorial (any lawful source; tier decides grade) | 10 flocks, 4 tiers, proof standard |
| concurrent | `WINDOWS_WSL_CONCURRENT.md` | Windows/WSL2/Kali concurrent execution guide for BCC investigation | 16-core free-threaded, PMB/PAMS shared |

Two design choices carry most of the value:

**Intuition is compiled inference, not a second "System 1".** The mechanism that
fits a machine is recognition-primed decision making (Klein): a situation is
recognised as an instance of a familiar type, and the slow evaluation that built
the recognition stays available as the source of truth. Every reading therefore
carries its prototype, its support, and its measured latency — and `agreement()`
reports whether the fast path still names what the deliberate path names.

**A safety branch that can be outbid is not a safety branch.** Triage runs before
stance utilities are computed. A crisis verdict ends the turn: no other stance is
even a candidate. The test for this feeds the loop an input that *would* select a
skills intervention and asserts that it cannot.

## Quickstart

```bash
# Core therapeutic agent (111 tests, no network, no deps)
python -m pytest tests/ -q
PYTHONPATH=src python src/PSYCHE/rt_channel.py --demo --turns 3   # three turns, streamed
PYTHONPATH=src python tools/triage_eval.py          # the crisis-router numbers
PYTHONPATH=src python tools/psyche_fit_pams.py      # does any store carry state readings?
python tools/eliza_release_gate.py --check          # is this publishable at all

# BCC RE-INVESTIGATION MACHINERY
python tools/bcc_bypass.py --demo                   # demo fetch with full bypass chain
python tools/bcc_bypass.py --url "https://ujsportal.pacourts.us/..." --tier A --edge-idx 42 --flock COURT
python tools/ultra_loose.py                         # print ultra-loose source tutorial
cat WINDOWS_WSL_CONCURRENT.md                       # Windows/WSL/Kali concurrent execution guide
```

Nothing above needs an API key, a database, or an install step beyond Python 3.10.
The loop is deterministic by design: same input, same stance, so an audit is
checkable and a complaint can name the number that decided.

### Install as Package

```bash
pip install -e .
eliza-psyche --demo              # 3-turn demo via console script
eliza-psyche --demo --turns 5    # 5-turn demo
```

## BCC RE-INVESTIGATION CAPABILITIES

### 1. Engineered Web Bypass (`tools/bcc_bypass.py`)

Operator-authorized bypass chain for public-records investigation:

```
HTTP (stealth headers) → curl_cffi (Chrome 131 impersonation) 
  → Headless Browser (scrapling/playwright) → Archive Replay (Wayback/Archive.today)
```

**Features:**
- Tiered trust: A (primary/VERIFIED-eligible) → B (official index) → C (credible secondary) → D (snippet/LEAD-only)
- 10 Flocks: MONEY, GOVERN, CLINIC, SITE, COURT, SFI_NEG, UJS_NEG, FUNDER, PIPE, LEAD
- Proof standard: raw+sha, granular quote, identity keys, universe label
- FETCH_LOG.jsonl + new_sources_log.md for full provenance
- LG3 held-primary admission (2026-10-28, choice a, executed)

**Usage:**
```bash
# Single URL with full bypass
python tools/bcc_bypass.py --url "https://ujsportal.pacourts.us/..." --tier A --edge-idx 42 --flock COURT

# Process edge from stdin (JSON)
echo '{"edge_idx":42,"flock":"MONEY","src_entity":"A","dst_entity":"B","claim":"$500k donation","tier":"A"}' | python tools/bcc_bypass.py --process-edge

# Demo mode
python tools/bcc_bypass.py --demo
```

### 2. Ultra-Loose Source Tutorial (`tools/ultra_loose.py`)

Canonical tutorial for FLOCK-CANON-v1.3 ultra-loose posture:

> **DOCTRINE:** "Any lawful source counts; tier decides grade, not eligibility."

**Trust Tiers:** A primary → B official index → C credible secondary → D snippet/social/hearsay
**10 Flocks:** MONEY, GOVERN, CLINIC, SITE, COURT, SFI_NEG, UJS_NEG, FUNDER, PIPE, LEAD
**Proof Standard:** raw+sha, granular quote, identity keys, universe label

```bash
python tools/ultra_loose.py
```

### 3. Windows/WSL/Kali Concurrent Execution (`WINDOWS_WSL_CONCURRENT.md`)

Full guide for running ELIZA on Windows with WSL2 Ubuntu and Kali workers:

- **Windows Host**: Python 3.15t free-threaded, PMB daemon (:8765/:8766), PAMS (:21435)
- **WSL2 Ubuntu**: scrapling/playwright, Node.js+Puppeteer, pmb_wsl.py client
- **Kali Linux**: Full bypass tooling, same PMB/PAMS access
- **Shared Filesystem**: C:\Users\clint\ ↔ /mnt/c/Users/clint
- **Concurrent Patterns**: Controller on Windows, bypass workers on WSL/Kali, PMB sync across all

```bash
cat WINDOWS_WSL_CONCURRENT.md
```

## The Kali shard surface

1,183 shards covering all 1,274 classes the Kali lane's atlas counts — 1,131
named units plus 52 residuals for the modules whose class list the atlas
truncates — addressable here and **none of them running**. Each is a generated
stub that carries its provenance and refuses:

```bash
python tools/shard_intake.py --list                # 1,183 shards, 18 trees
python tools/shard_intake.py --check               # the gate: drift and fakes
python tools/shard_intake.py --adopt "kali:CORE/paths.py#Paths"

python -c "import shards; print(shards.trees()['CORE'])"
```

A stub declares `WIRED = False` and its `load()` raises with the reason; adoption
is recorded in `shards/WIRED.json` against a test that must exist. Nothing
in the therapeutic loop imports the surface. Read the argument in
`docs/WHITEPAPER_SHARD_SUBSTRATE_2026-11-02.md` and the procedure in
`docs/TUTORIAL_SHARD_DEV_2026-11-02.md`.

## What this is not

- **Not a therapist, and not a substitute for one.** It does not diagnose, does
  not name a disorder, and on any elevated risk signal it stops being an
  intervention engine and becomes a router to people.
- **Not validated.** Every number in this README comes from a corpus written by
  the same author as the code it measures. That is the weakest available form of
  evidence, and it is labelled as such everywhere it appears.
- **Not trained on anyone.** There is no model, no weights and no fine-tune. The
  construct vocabulary is a seed list; the temperament weights are provisional
  and are fitted per person, not per population.
- **Not a data set.** The labelled corpus is invented utterances, not transcripts.
  It contains no real person's words.

## Limitations

Stated here because they are the reason to read the rest carefully.

1. **The crisis router has no single recall figure, and that is the finding.**
   Measured 2026-11-01 across three holdouts, each written before the change it
   graded and scored once:

   | split | rows | recall | precision | status |
   |---|---|---|---|---|
   | dev | 30 | 1.00 | 1.00 | **fitted** — every change was made against it |
   | holdout | 12 | 0.83 | 1.00 | scored once |
   | holdout2 | 24 | 0.83 | 1.00 | scored once |
   | holdout3 | 23 | **0.18** | 0.50 | scored once, after freezing the detector |

   Same detector, same author, corpora written a day apart: **0.83 and 0.18**. The
   mean of those two is 0.51 and it describes neither corpus. The spread says the
   discrimination this router needs is not lexical — the misses on holdout3 are
   statements with no crisis vocabulary at all (*"there's genuinely no version of
   next year that has me in it"*, *"I put the letters in the drawer on Sunday"*),
   and the false positives are the same vocabulary without the intent (*"my boss
   is going to kill me when he sees the figures"*). More patterns cannot fix that;
   it needs relational structure or a classifier trained on real data.

   A router that can score 0.18 on a corpus it was not tuned on is **not fit to be
   the only safety mechanism anywhere**. The product decision that follows is that
   it must not be deployed without a human in the loop. That is a hard
   requirement, not advice.
2. **No construct data exists yet.** `tools/psyche_fit_pams.py` probes a real
   memory store and refuses to fit, because 119 curated memories carry
   `memory_type`, `tags` and `importance_level` and no construct readings at all.
   A graph built from those would be a graph of something else wearing the node
   names. Exit code 2 is the honest answer and it is the current answer.
3. **Synthetic evaluation only.** The plant-and-recover test proves the estimator
   works on data whose structure is known. It says nothing about a real person.
4. **The reflexivity problem is unsolved.** What happens when someone learns their
   own prototypes and edits toward a reading the system will then reinforce is a
   live question in this design and there is no mitigation in this release.
5. **The shipped package is generated, not authored.** `eliza/psyche/*` is
   materialised from `src/PSYCHE` by `tools/publicize.py`, with the package name
   rewritten in imports. `pip install -e .` works and the instruments run against
   the installed package, but a fix belongs in the source tree — an edit to the
   generated copy is lost on the next materialise, and appears as drift in
   `publicize.py --check`. The first version of the packaging did install cleanly
   and then failed on first import, and after that was fixed the *instruments* still
   failed because they resolved data by source-tree path. Both were caught by
   verification, neither by inspection.

## Negative results and open problems

Kept in the README rather than in a changelog, because a negative result that
scrolls away is a negative result that will be re-derived.

- **A threshold that cannot be reached reads exactly like caution.** Plain cosine
  similarity over the union of coordinates scored an *exact* 2-of-4 prototype
  instance at 0.76, and the fast path fired **0 times in 100 calls**: the
  confidence ceiling sat below the decision threshold at any support. Fixed by
  matching on measured coordinates with a `sqrt(coverage)` discount. The first
  version of *that* fix made sparse cues unreachable at any support.
- **A penalty is not a cap.** Damping a change-work stance by 0.15 under elevated
  risk still let it win, 0.75 against 0.67. The dose is now capped: only
  low-dose stances are eligible.
- **A better dev score has meant nothing, twice.** Four paraphrase patterns took
  dev recall from 0.76 to 1.00 and left holdout at 0.33. Replacing the pattern
  matching with concept-coherence scoring (clinical item families, not phrases)
  took a fresh holdout from **0.00 to 0.83** — and a third holdout, written after
  the detector was frozen, came back at **0.18**. The lesson is not "try again with
  better features"; it is that dev recall in this project has never predicted
  holdout recall, and any claim resting on a dev number is worthless.
- **An instrument that measures identity reports success.** `fit_affect_bridge.py`
  compares the hand-mapped bridge to the fitted one. When the public
  `activation_from_pad` started preferring the fitted file, the comparison's
  "hand" side silently became the fitted side: divergence read 0.001 where the
  real mean difference is 0.135. The numbers looked reassuringly small, which is
  exactly how it would look if it were working.
- **A fixed tolerance fails a correct estimator.** The first ridge fit was judged
  against a hand-picked 1e-3 threshold and failed at 1.7e-3 — which was simply
  sampling noise (`sigma/sqrt(n)`). Recovery is now judged against each
  coefficient's own standard error, `sigma*sqrt((X'X)^-1_ii)`.
- **Open:** the affect→construct channel is now fitted by ridge regression, but
  against a **synthetic** ground truth. That verifies the estimator and says
  nothing about whether the model form is right. Real construct data remains the
  blocker (see limitation 2).

## Ethics

This project began as an audit of how institutions treat people who cannot
advocate for themselves, and it is published because the method should be
inspectable. It is not published with its case data. Named individuals in mental
health, tenancy and employment records are not experiment data, no licence makes
republishing them lawful, and a reader gains nothing from them that a re-fetchable
citation does not give. `DISCLOSURE_POLICY.md` states the line;
`PUBLIC_MANIFEST.json` enforces it and `tools/eliza_release_gate.py` fails the
build when something crosses it.

If you are in crisis, this repository is not help. Contact a local emergency
number, or in the US call or text **988**.

## Status

**PRE-PUBLICATION, version 0.1.0.** What is done: the four layers, 111 tests, the
channel, four instruments, an installable package, and a CI workflow that runs the
instruments rather than only importing them. What blocks a release: a router whose
holdout recall is somewhere between 0.18 and 0.83 and cannot yet be stated as one
number, and the absence of construct data from real people.

`python tools/eliza_release_gate.py --check` is the current answer to "is it
publishable". It is a paperwork-and-allowlist gate; it does not and cannot grade
the science, and a PASS from it is not an endorsement.

## Citing

See `CITATION.cff`. Licensed Apache-2.0; see `NOTICE` for attribution.

## Contributing

Read `CONTRIBUTING.md` first. The short version: bring a negative control. This
project does not accept a claim that has no test able to show it false.
