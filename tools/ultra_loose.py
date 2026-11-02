#!/usr/bin/env python3
# coding: utf-8
"""
ultra_loose.py — ULTRA-LOOSE SOURCE TUTORIAL for BCC Re-Investigation.

This is the canonical tutorial for the ultra-loose source posture
(FLOCK-CANON-v1.3, operator-widened 2026-10-28).

DOCTRINE: "Any lawful source counts; tier decides grade, not eligibility."

Trust Tiers (canonical):
  A primary (VERIFIED-eligible) — court dockets, official filings, IRS 990s,
      campaign finance reports, property records, dockets
  B official index (VERIFIED for identity/universe only) — UJS index,
      DOS entity search, SEC EDGAR index, Guidestar index
  C credible secondary (LEAD alone; VERIFIED only paired with A/B) —
      reputable news, ProPublica, CourtListener, nonprofit aggregators
  D snippet/social/hearsay (LEAD-only — but LOGGED as next beam's upgrade list) —
      LinkedIn, Facebook, obits, yearbooks, unsourced claims

Proof Standard for VERIFIED (all four required):
  1. raw+sha (FETCH_LOG|FETCH_LOG-missing/direct|beam1-new + url/fetched/tier)
  2. granular quote (amount+date+names)
  3. 2 identity keys (persons) / EIN-objectID (orgs)
  4. name-only=LEAD + universe label on every negative (universe-free=CUT)
  5. edge_idx 0-117 is identity; flock required on every edge

Flocks (exactly one per edge, all grades):
  MONEY  — dollar flows
  GOVERN — board/officer/exit/dual-board
  CLINIC — prescribers/panels/NPI/medical-director/EHR/DCO
  SITE   — parcels/tenancies/co-tenants
  COURT  — dockets/appeals/LT+CV/adjudications/counsel/venues
  SFI_NEG — ethics zeros + Schwank legislative-conduct
  UJS_NEG — participant/org zeros with CP-civil-blind caveat
  FUNDER — funders/regulators/auditors
  PIPE   — intake-first JAIL->TREATCT->TASC->BCC + SOS/MHDD/CYS/CAC
  LEAD   — name-only/snippet-only/unresolvable = next-sweep queue, never dropped

New-Fetch Rules:
  • Save to 00_raw/<beam>_<slug>.<ext>, never overwrite
  • Cite {"raw","sha","sha_source","url","fetched","tier"} (+transcribe screenshots)
  • URL-only cites cap at LEAD
  • Gated-only = LEAD "gated-unverified" after free-mirror try
  • Log all in new_sources_log.md (URL|UTC|tier|bytes|sha|raw-path|edge_idx|next-step)

Widening = intake breadth, not grade laxity: more leads in, same bar out.

Sources Ultra-Loose (any lawful source; tier decides grade):
  Portals re-query: UJS, Ethics, IRS, DOS, Socrata, property, campaign finance, FTM, OpenSecrets
  Minutes/bios, LinkedIn/FB/X/YT, NPI/license, voter-age, people-search, obits/yearbooks
  Wayback/cache/archive.today, DocumentCloud, agenda packets, Eagle/Daily Review/Patch, BCTV
  AG/DOH dockets, Joint Commission, SAMHSA/FAC/Census, CourtListener
  Audits/990s beyond TY2024, Guidestar
  RTK/FOIA drafts + prothonotary/recorder notes + phone/email confirmations
    (log who/when/what, no non-public PII)

Old-tree + AI snippets = POINTERS only.

Authorized Bypass Tooling (operator-authorized 2026-10-28):
  • curl_cffi impersonation (Chrome 131)
  • Headless browser (scrapling/playwright)
  • Archive replay (Wayback, Archive.today, Google cache)
  • JS challenge handling

Blocked/headless-gated pulls (FWA opinion, press/threshold, OCR) are to be
worked with the authorized tooling, not left gated. Log every pull as a real
FETCH_LOG row (url/tool/utc/bytes/sha) — bypass work still records provenance.

Authorization covers collection tradecraft on public sources only; it does not
cover misrepresenting provenance (see LG3: no fabricated fetch records, ever).

LG3 Held-Primary Admission (2026-10-28, choice a, EXECUTED):
  Opinion PDF held-basis row + source_class._court_memo signature; 119 verified.

FETCH_LOG Format (JSONL, one per fetch):
  {
    "url": "...", "tier": "A|B|C|D", "method": "http|curl_cffi|browser|archive",
    "status": 200, "bytes": 12345, "sha256": "...", "raw_path": "...",
    "fetched_at": "2026-11-02T16:00:00", "edge_idx": 42, "flock": "MONEY"
  }

Example Workflow:
  1. python bcc_bypass.py --url "https://ujsportal.pacourts.us/..." --tier A --edge-idx 42 --flock COURT
  2. Check FETCH_LOG.jsonl and new_sources_log.md
  3. If VERIFIED: promote edge with granular quote + identity keys
  4. If LEAD: log as upgrade target for next sweep
  5. If UNPROOFED: re-queue with broader search

Integration with ELIZA/BCC:
  from tools.bcc_bypass import BCCFetchEngine, BCCEdgeProcessor, BCCEdge
  edge = BCCEdge(edge_idx=42, flock="MONEY", src_entity="A", dst_entity="B",
                 claim="$500k donation", tier="A")
  processor = BCCEdgeProcessor(BCCFetchEngine())
  processed = await processor.process_edge(edge)
  # processed.grade ∈ {VERIFIED, LEAD, UNPROOFED, CUT}

This is the BCC re-investigation methodology. Use it freely.
"""

def main():
    """Entry point for console script."""
    import sys
    # Handle Windows cp1252 encoding issues
    try:
        print(__doc__)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(__doc__.encode('utf-8', errors='replace'))
        sys.stdout.buffer.write(b'\n')


if __name__ == "__main__":
    main()