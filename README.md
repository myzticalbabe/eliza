# Project ELIZA

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
python -m pytest tests/ -q                          # 76 tests, no network, no deps
PYTHONPATH=src python src/PSYCHE/rt_channel.py --demo --turns 3   # three turns, streamed
PYTHONPATH=src python tools/triage_eval.py          # the crisis-router numbers
PYTHONPATH=src python tools/psyche_fit_pams.py      # does any store carry state readings?
python tools/eliza_release_gate.py --check          # is this publishable at all
```

Nothing above needs an API key, a database, or an install step beyond Python 3.10.
The loop is deterministic by design: same input, same stance, so an audit is
checkable and a complaint can name the number that decided.

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

1. **The crisis router misses intent it was not written around.** On the holdout
   split — twelve rows written after the last change — it measures **recall 0.33,
   precision 1.00**. On the dev split it measures recall 1.00, because that split
   is what it was changed against. Both numbers are in
   `tools/triage_eval.py` output, always, with the split named. A 0.33 recall
   safety router is **not fit to be the only safety mechanism anywhere**; the
   product decision that follows is that it must not be deployed without a human
   in the loop, and that is a hard requirement, not advice.
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
5. **`eliza` is not a package here.** The modules live under `src/PSYCHE` in their
   parent repository and are mapped into a distributable layout by
   `PUBLIC_MANIFEST.json`; packaging is a release step, not a claim made now.

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
- **The router generalised poorly, and the split is what showed it.** Adding four
  paraphrase patterns took dev recall from 0.76 to 1.00 and left holdout at 0.33.
  Tuning further would have burned the holdout and produced a number that looked
  like a generalisation and was not. The next step is a classifier trained on
  genuinely disjoint data, or a vocabulary built from how people actually talk.
- **Open:** communication channel between the affect layer and the graph is
  hand-mapped (`activation_from_pad`), not fitted. That mapping is the weakest
  modelling assumption in the release.

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

**PRE-PUBLICATION, version 0.1.0.** What is done: the four layers, 76 tests, the
channel, and four instruments. What blocks a release: the holdout recall figure
above, real construct data, and packaging. `python tools/eliza_release_gate.py
--check` is the current answer to "is it publishable", and it is meant to say no
until those are addressed.

## Citing

See `CITATION.cff`. Licensed Apache-2.0; see `NOTICE` for attribution.

## Contributing

Read `CONTRIBUTING.md` first. The short version: bring a negative control. This
project does not accept a claim that has no test able to show it false.
