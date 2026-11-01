# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet. Every entry below describes 0.1.0, which is **pre-publication**:
  the version exists so that the changelog has a first row, not because a
  release happened.

## [0.1.0] - 2026-11-01

### Added

- `eliza/psyche/network.py` — construct graph. Nodes are constructs and observable
  states; edges are ridge-shrunk partial correlations estimated from observations
  and editable by hand; one GNN message-passing layer with symmetric degree
  normalisation. Centrality carries the edge support behind each row.
- `eliza/psyche/intuition.py` — compiled inference. Prototypes with support counts,
  `read()` / `deliberate()` / `read_or_think()`, a resolution ledger and a Brier
  score reported with the count it rests on. Resolving a reading never edits the
  prototype, so a wrong intuition stays wrong and stays measurable.
- `eliza/psyche/rt_agent.py` — the realtime loop. Six stances, risk triage before
  stance scoring, a receptivity gate that keeps skills work out of a state outside
  the learning window, and a dose cap on elevated risk.
- `eliza/psyche/rt_channel.py` — newline-delimited JSON over stdio, flushed per
  turn, with per-turn budget reporting and error records that never end a session.
- `tools/triage_eval.py` — crisis-router evaluation with dev/holdout splits, a
  per-category breakdown, and false negatives printed before false positives.
- `tools/psyche_fit_pams.py` — probes a store for construct-bearing readings and
  **refuses** to fit when none exist. Exit code 2 is a result, not a failure.
- `tools/eliza_release_gate.py` — publication gate: community-file standard,
  manifest allowlist, evidence deny-list, secret scan, required disclosures.
- 76 tests across seven files. Every claim of a capability ships with a control
  able to show it false.

### Changed

- Crisis routing matches **patterns**, not only exact phrases, and downgrades to
  `monitor` when intent language is attributed to another person, framed in the
  past, or quoted. Motivation: an evaluation measured recall 0.76 with three
  euphemism misses and five false positives.
- Similarity matching runs on measured coordinates with a `sqrt(coverage)`
  discount instead of cosine over the union, which had made the fast path
  unreachable for exact partial matches.

### Fixed

- Elevated risk applied a 0.15 penalty that a change-work stance could outbid
  (0.75 versus 0.67). The dose is now capped: only low-dose stances are eligible.
- `stats()` mixed two denominators — session turn count against audit-window
  stance counts — so a 200-turn session appeared to have lost turns.

### Security

- The safety branch is asserted to be un-outbiddable by construction, with a test
  that supplies an input which would otherwise select a skills intervention.
- The publication gate refuses to ship a tree containing secret-shaped strings and
  refuses to publish while the README's Limitations section is missing.

### Known limitation

- Crisis-router **holdout recall is 0.33** (dev 1.00, fitted). Precision on holdout
  is 1.00. This is documented in the README, asserted by a test, and is a release
  blocker rather than a backlog item.

[Unreleased]: https://example.invalid/eliza/compare/0.1.0...HEAD
[0.1.0]: https://example.invalid/eliza/releases/tag/v0.1.0
