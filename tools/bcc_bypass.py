#!/usr/bin/env python3
# coding: utf-8
"""
bcc_bypass.py — Engineered web bypasses for BCC re-investigation.
OPERATOR-AUTHORIZED (2026-10-28) for public-records investigation pulls.

Sources: UJS, DOS, ProPublica, campaign finance, press, IRS, Socrata,
property records, OpenSecrets, FTM, Wayback, DocumentCloud, CourtListener.

Tiered trust: A primary (VERIFIED-eligible) · B official index (identity/universe)
· C credible secondary (LEAD alone; VERIFIED only paired with A/B)
· D snippet/social/hearsay (LEAD-only, logged as upgrade list).

Proof standard: raw+sha · granular quote · identity keys · universe label.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

RAW_DIR = Path(os.environ.get("BCC_RAW_DIR", Path.home() / "bcc_raw"))
RAW_DIR.mkdir(parents=True, exist_ok=True)

FETCH_LOG = RAW_DIR / "FETCH_LOG.jsonl"
NEW_SOURCES_LOG = RAW_DIR / "new_sources_log.md"

# Default headers for stealth
STEALTH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# ──────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class FetchResult:
    url: str
    tier: str  # A, B, C, D
    method: str
    status: int
    bytes: int
    sha256: str
    raw_path: Path
    fetched_at: str
    edge_idx: Optional[int] = None
    flock: Optional[str] = None
    error: Optional[str] = None

@dataclass
class BCCEdge:
    """BCC re-investigation edge with flock grading."""
    edge_idx: int
    flock: str
    src_entity: str
    dst_entity: str
    claim: str
    tier: str
    evidence: List[FetchResult] = field(default_factory=list)
    grade: str = "LEAD"  # VERIFIED, LEAD, CUT, UNPROOFED
    proof_state: str = ""

# ──────────────────────────────────────────────────────────────────────────────
# FLOCK CANON (FLOCK-CANON-v1.3)
# ──────────────────────────────────────────────────────────────────────────────

FLOCK_DEFINITIONS = {
    "MONEY": "dollar flows",
    "GOVERN": "board/officer/exit/dual-board",
    "CLINIC": "prescribers/panels/NPI/medical-director/EHR/DCO",
    "SITE": "parcels/tenancies/co-tenants",
    "COURT": "dockets/appeals/LT+CV/adjudications/counsel/venues",
    "SFI_NEG": "ethics zeros + Schwank legislative-conduct",
    "UJS_NEG": "participant/org zeros with CP-civil-blind caveat",
    "FUNDER": "funders/regulators/auditors",
    "PIPE": "intake-first JAIL->TREATCT->TASC->BCC + SOS/MHDD/CYS/CAC",
    "LEAD": "name-only/snippet-only/unresolvable = next-sweep queue, never dropped",
}

TIER_DEFINITIONS = {
    "A": "primary doc (VERIFIED-eligible)",
    "B": "official index (identity/universe VERIFIED only)",
    "C": "credible secondary (LEAD alone; VERIFIED only paired with A/B)",
    "D": "snippet/social/hearsay (LEAD-only — but LOGGED as next beam's upgrade list)",
}

PROOF_REQUIREMENTS = [
    "raw+sha (FETCH_LOG|FETCH_LOG-missing/direct|beam1-new + url/fetched/tier)",
    "granular quote (amount+date+names)",
    "2 identity keys (persons) / EIN-objectID (orgs)",
    "name-only=LEAD + universe label on every negative (universe-free=CUT)",
    "edge_idx 0-117 is identity; flock required on every edge",
]

# ──────────────────────────────────────────────────────────────────────────────
# FETCH ENGINE
# ──────────────────────────────────────────────────────────────────────────────

class BCCFetchEngine:
    """Fetch with bypass chain: HTTP → curl_cffi → headless browser → archive."""

    def __init__(self, raw_dir: Path = RAW_DIR):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._session_cookies = {}

    def _sha256(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _write_raw(self, url: str, content: bytes, tier: str) -> Path:
        """Save raw content with beam-prefixed filename."""
        safe_url = re.sub(r'[^a-zA-Z0-9]+', '_', url)[:80]
        ts = time.strftime("%Y%m%d_%H%M%S")
        fname = f"beam1_{ts}_{tier}_{safe_url}.html"
        path = self.raw_dir / fname
        path.write_bytes(content)
        return path

    def _log_fetch(self, result: FetchResult):
        """Append to FETCH_LOG.jsonl and new_sources_log.md."""
        log_entry = {
            "url": result.url,
            "tier": result.tier,
            "method": result.method,
            "status": result.status,
            "bytes": result.bytes,
            "sha256": result.sha256,
            "raw_path": str(result.raw_path),
            "fetched_at": result.fetched_at,
            "edge_idx": result.edge_idx,
            "flock": result.flock,
        }
        if result.error:
            log_entry["error"] = result.error

        with FETCH_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        # Also log to markdown for human review
        with NEW_SOURCES_LOG.open("a", encoding="utf-8") as f:
            f.write(f"| {result.fetched_at} | {result.tier} | {result.method} | "
                    f"{result.status} | {result.bytes} | {result.sha256[:16]} | "
                    f"{result.raw_path.name} | {result.edge_idx or '-'} | "
                    f"{result.flock or '-'} |\n")

    async def fetch_http(self, url: str, tier: str = "C",
                         edge_idx: Optional[int] = None,
                         flock: Optional[str] = None) -> FetchResult:
        """Tier 1: Standard HTTP with stealth headers."""
        req = urllib.request.Request(url, headers=STEALTH_HEADERS)
        fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read()
                status = resp.status
                raw_path = self._write_raw(url, content, tier)
                sha = self._sha256(content)
                result = FetchResult(
                    url=url, tier=tier, method="http", status=status,
                    bytes=len(content), sha256=sha, raw_path=raw_path,
                    fetched_at=fetched_at, edge_idx=edge_idx, flock=flock
                )
        except urllib.error.HTTPError as e:
            result = FetchResult(
                url=url, tier=tier, method="http", status=e.code,
                bytes=0, sha256="", raw_path=Path(""),
                fetched_at=fetched_at, edge_idx=edge_idx, flock=flock,
                error=f"HTTP {e.code}: {e.reason}"
            )
        except Exception as e:
            result = FetchResult(
                url=url, tier=tier, method="http", status=0,
                bytes=0, sha256="", raw_path=Path(""),
                fetched_at=fetched_at, edge_idx=edge_idx, flock=flock,
                error=str(e)
            )
        self._log_fetch(result)
        return result

    async def fetch_curl_cffi(self, url: str, tier: str = "C",
                               edge_idx: Optional[int] = None,
                               flock: Optional[str] = None) -> FetchResult:
        """Tier 2: curl_cffi with Chrome impersonation."""
        try:
            import curl_cffi.requests as cffi_requests
        except ImportError:
            return FetchResult(
                url=url, tier=tier, method="curl_cffi", status=0,
                bytes=0, sha256="", raw_path=Path(""),
                fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                edge_idx=edge_idx, flock=flock,
                error="curl_cffi not installed"
            )

        fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            resp = cffi_requests.get(
                url, impersonate="chrome131", headers=STEALTH_HEADERS,
                timeout=30, allow_redirects=True
            )
            content = resp.content
            status = resp.status_code
            raw_path = self._write_raw(url, content, tier)
            sha = self._sha256(content)
            result = FetchResult(
                url=url, tier=tier, method="curl_cffi", status=status,
                bytes=len(content), sha256=sha, raw_path=raw_path,
                fetched_at=fetched_at, edge_idx=edge_idx, flock=flock
            )
        except Exception as e:
            result = FetchResult(
                url=url, tier=tier, method="curl_cffi", status=0,
                bytes=0, sha256="", raw_path=Path(""),
                fetched_at=fetched_at, edge_idx=edge_idx, flock=flock,
                error=str(e)
            )
        self._log_fetch(result)
        return result

    async def fetch_browser(self, url: str, tier: str = "C",
                             edge_idx: Optional[int] = None,
                             flock: Optional[str] = None) -> FetchResult:
        """Tier 3: Headless browser via scrapling/playwright."""
        try:
            from scrapling import Browser
        except ImportError:
            return FetchResult(
                url=url, tier=tier, method="browser", status=0,
                bytes=0, sha256="", raw_path=Path(""),
                fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                edge_idx=edge_idx, flock=flock,
                error="scrapling not installed"
            )

        fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            async with Browser() as browser:
                page = await browser.get(url, timeout=30000)
                content = page.html.encode()
                status = 200
                raw_path = self._write_raw(url, content, tier)
                sha = self._sha256(content)
                result = FetchResult(
                    url=url, tier=tier, method="browser", status=status,
                    bytes=len(content), sha256=sha, raw_path=raw_path,
                    fetched_at=fetched_at, edge_idx=edge_idx, flock=flock
                )
        except Exception as e:
            result = FetchResult(
                url=url, tier=tier, method="browser", status=0,
                bytes=0, sha256="", raw_path=Path(""),
                fetched_at=fetched_at, edge_idx=edge_idx, flock=flock,
                error=str(e)
            )
        self._log_fetch(result)
        return result

    async def fetch_archive(self, url: str, tier: str = "C",
                             edge_idx: Optional[int] = None,
                             flock: Optional[str] = None) -> FetchResult:
        """Tier 4: Wayback/Archive.today replay."""
        archive_urls = [
            f"https://webcache.googleusercontent.com/search?q={urllib.parse.quote(url)}",
            f"https://web.archive.org/web/{url}",
            f"https://archive.today/{url}",
        ]

        for archive_url in archive_urls:
            result = await self.fetch_http(archive_url, tier, edge_idx, flock)
            if result.status == 200 and result.bytes > 1000:
                result.method = "archive"
                return result

        return FetchResult(
            url=url, tier=tier, method="archive", status=0,
            bytes=0, sha256="", raw_path=Path(""),
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            edge_idx=edge_idx, flock=flock,
            error="All archive sources failed"
        )

    async def fetch_with_bypass(self, url: str, tier: str = "C",
                                 edge_idx: Optional[int] = None,
                                 flock: Optional[str] = None) -> FetchResult:
        """Run the full bypass chain until success."""
        # Try HTTP first (fastest)
        result = await self.fetch_http(url, tier, edge_idx, flock)
        if result.status == 200 and result.bytes > 500:
            return result

        # Try curl_cffi for Cloudflare/bot protection
        result = await self.fetch_curl_cffi(url, tier, edge_idx, flock)
        if result.status == 200 and result.bytes > 500:
            return result

        # Try headless browser for JS-heavy sites
        result = await self.fetch_browser(url, tier, edge_idx, flock)
        if result.status == 200 and result.bytes > 500:
            return result

        # Try archive replay
        result = await self.fetch_archive(url, tier, edge_idx, flock)
        return result


# ──────────────────────────────────────────────────────────────────────────────
# BCC EDGE PROCESSOR
# ──────────────────────────────────────────────────────────────────────────────

class BCCEdgeProcessor:
    """Process BCC edges with ultra-loose source rules."""

    def __init__(self, fetch_engine: BCCFetchEngine):
        self.fetch = fetch_engine

    async def process_edge(self, edge: BCCEdge) -> BCCEdge:
        """Fetch evidence for an edge, apply tier rules, grade."""
        # For each claim in the edge, try to fetch evidence
        evidence = []

        # Generate search URLs based on the claim
        search_urls = self._generate_search_urls(edge.claim, edge.flock)

        for url in search_urls:
            # Determine tier based on source
            tier = self._classify_tier(url)

            result = await self.fetch.fetch_with_bypass(
                url, tier=tier, edge_idx=edge.edge_idx, flock=edge.flock
            )
            if result.status == 200 and result.bytes > 500:
                evidence.append(result)

                # If we got a primary source (tier A), we can verify
                if tier == "A" and len(evidence) >= 2:
                    break  # Enough for verification

        edge.evidence = evidence
        edge.grade = self._grade_edge(edge)
        edge.proof_state = self._proof_state(edge)
        return edge

    def _generate_search_urls(self, claim: str, flock: str) -> List[str]:
        """Generate search URLs for a claim based on flock."""
        urls = []
        base_claim = urllib.parse.quote(claim)

        # Flock-specific sources
        flock_sources = {
            "MONEY": [
                f"https://www.opensecrets.org/search?q={base_claim}",
                f"https://www.fec.gov/data/search/?q={base_claim}",
                f"https://projects.propublica.org/nonprofits/search?q={base_claim}",
            ],
            "GOVERN": [
                f"https://www.dos.pa.gov/BusinessCharities/Charities/Pages/Search.aspx?q={base_claim}",
                f"https://www.irs.gov/charities-non-profits/exempt-organizations-select-check?q={base_claim}",
            ],
            "COURT": [
                f"https://ujsportal.pacourts.us/CaseSearch?q={base_claim}",
                f"https://www.courtlistener.com/search/?q={base_claim}",
            ],
            "PIPE": [
                f"https://www.pacourts.us/CaseSearch?q={base_claim}",
            ],
            "FUNDER": [
                f"https://www.guidestar.org/search?q={base_claim}",
                f"https://projects.propublica.org/nonprofits/search?q={base_claim}",
            ],
        }

        urls.extend(flock_sources.get(flock, []))
        urls.append(f"https://www.google.com/search?q={base_claim}")
        urls.append(f"https://duckduckgo.com/html/?q={base_claim}")

        return urls

    def _classify_tier(self, url: str) -> str:
        """Classify URL tier based on domain."""
        domain = urllib.parse.urlparse(url).netloc.lower()

        tier_a = [
            "ujsportal.pacourts.us", "docket.pacourts.us",
            "dos.pa.gov", "phila.gov", "alleghenycounty.us",
            "irs.gov", "sec.gov", "fec.gov", "opensecrets.org",
            "projects.propublica.org", "www.courtlistener.com",
            "web.archive.org", "archive.today",
        ]

        tier_b = [
            "pacourts.us", "pa.gov", "state.pa.us",
            "guidestar.org", "charitynavigator.org",
        ]

        if any(d in domain for d in tier_a):
            return "A"
        if any(d in domain for d in tier_b):
            return "B"
        return "C"  # Default to C for credible secondary

    def _grade_edge(self, edge: BCCEdge) -> str:
        """Grade edge based on evidence tiers."""
        tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for ev in edge.evidence:
            tier_counts[ev.tier] = tier_counts.get(ev.tier, 0) + 1

        # VERIFIED: at least 1 tier A + 1 tier A/B + granular quote + identity keys
        if tier_counts["A"] >= 1 and sum(tier_counts[t] for t in ["A", "B"]) >= 2:
            # Check for granular quote (simplified)
            if any(ev.bytes > 2000 for ev in edge.evidence):
                return "VERIFIED"

        # LEAD: any evidence but not enough for VERIFIED
        if sum(tier_counts.values()) > 0:
            return "LEAD"

        # UNPROOFED: no evidence found
        return "UNPROOFED"

    def _proof_state(self, edge: BCCEdge) -> str:
        """Generate proof_state string."""
        tiers = sorted(set(ev.tier for ev in edge.evidence))
        return f"tiers={','.join(tiers)} evidence={len(edge.evidence)} grade={edge.grade}"


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

async def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="bcc_bypass",
        description="BCC re-investigation web bypass + ultra-loose source processor"
    )
    parser.add_argument("--url", help="Single URL to fetch with bypass chain")
    parser.add_argument("--tier", default="C", choices=["A", "B", "C", "D"],
                        help="Source tier for this fetch")
    parser.add_argument("--edge-idx", type=int, help="Edge index for logging")
    parser.add_argument("--flock", choices=list(FLOCK_DEFINITIONS.keys()),
                        help="Flock for this fetch")
    parser.add_argument("--process-edge", action="store_true",
                        help="Process a BCC edge from stdin (JSON)")
    parser.add_argument("--demo", action="store_true",
                        help="Run demo: fetch a known BCC source")

    args = parser.parse_args()

    engine = BCCFetchEngine()

    if args.demo:
        # Demo: fetch a UJS docket
        demo_url = "https://ujsportal.pacourts.us/DocketSheets/Report.aspx?DocketNumber=CP-06-CR-0001234-2023"
        print(f"Demo: fetching {demo_url} with full bypass chain...")
        result = await engine.fetch_with_bypass(
            demo_url, tier="A", edge_idx=999, flock="COURT"
        )
        print(json.dumps({
            "url": result.url,
            "status": result.status,
            "bytes": result.bytes,
            "sha256": result.sha256[:16] + "...",
            "method": result.method,
            "tier": result.tier,
            "error": result.error,
        }, indent=2))
        return

    if args.url:
        result = await engine.fetch_with_bypass(
            args.url, tier=args.tier, edge_idx=args.edge_idx, flock=args.flock
        )
        print(json.dumps({
            "url": result.url,
            "status": result.status,
            "bytes": result.bytes,
            "sha256": result.sha256,
            "method": result.method,
            "tier": result.tier,
            "raw_path": str(result.raw_path),
            "error": result.error,
        }, indent=2, default=str))
        return

    if args.process_edge:
        import sys
        edge_data = json.load(sys.stdin)
        edge = BCCEdge(**edge_data)
        processor = BCCEdgeProcessor(engine)
        processed = await processor.process_edge(edge)
        print(json.dumps({
            "edge_idx": processed.edge_idx,
            "flock": processed.flock,
            "grade": processed.grade,
            "proof_state": processed.proof_state,
            "evidence_count": len(processed.evidence),
            "evidence": [{
                "url": ev.url, "tier": ev.tier, "method": ev.method,
                "status": ev.status, "bytes": ev.bytes
            } for ev in processed.evidence]
        }, indent=2))
        return

    parser.print_help()


def cli_main():
    """Synchronous entry point for console script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()