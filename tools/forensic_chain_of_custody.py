#!/usr/bin/env python3
# coding: utf-8
"""
forensic_chain_of_custody.py — Rebuilt chain-of-custody module (closes FLAMING
SWORD ledger t-0002, 2026-11-03).

History
-------
Until 2026-11-03 this file was a 21-line fragment that started mid-function
(an ownerless `with get_db_transaction(...)` block writing into a
`digital_signatures` table); no git history and no duplicate on any tree. The
rebuild below keeps what the fragment proves existed, preserving its exact
DB-write shape:

  * the `get_db_transaction(...)` context manager, with sqlite3 semantics:
    commit on clean exit, rollback+re-raise on error, always close;
  * the `digital_signatures` INSERT with exactly the recovered column list,
    `record.digital_signature.*`, `record.id`, `record.evidence_id`,
    `record.actor_id`, `record.actor_role.value`, `record.action.value` and
    `record.description` field names as recovered;
  * the `_log_audit(...)` tail and `return record` of the fragment.

One documented deviation from the fragment: the fragment called
`conn.commit()` AFTER the with-block on an already-detached connection. The
rebuilt commit happens inside the managed block — the fragment's placement
cannot survive a context manager that owns the connection. The fragment is
preserved byte-exact below as FRAGMENT (see recovered_fragment()).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


# ──────────────────────────────────────────────────────────────────────────────
# RECOVERED FRAGMENT (evidence, preserved byte-exact)
# ──────────────────────────────────────────────────────────────────────────────

FRAGMENT: str = '''\
        with get_db_transaction(self.db_path) as conn:
            conn.execute("""
                INSERT INTO digital_signatures (id, record_id, algorithm, signature,
                    public_key_pem, signed_at, signed_by, verified, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), record.id, record.digital_signature.algorithm,
                record.digital_signature.signature, record.digital_signature.public_key_pem,
                record.digital_signature.signed_at, record.digital_signature.signed_by,
                0, None
            ))

        conn.commit()

        # Log audit entry
        self._log_audit(record.evidence_id, record.actor_id, record.actor_role.value,
                        f"custody_record_{record.action.value.lower()}",
                        f"Added custody record: {record.description}")

        return record
'''


def recovered_fragment() -> str:
    """The surviving fragment, byte-exact. Evidence accessor, not dead data:
    add_custody_record's DB write must match it column-for-column."""
    return FRAGMENT


# ──────────────────────────────────────────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────────────────────────────────────────

class ActorRole(Enum):
    EVIDENCE_CUSTODIAN = "evidence_custodian"
    ANALYST = "analyst"
    EVIDENCE_CLERK = "evidence_clerk"
    WITNESS = "witness"
    EXTERNAL_AGENT = "external_agent"


class CustodyAction(Enum):
    COLLECTED = "COLLECTED"
    SEIZED = "SEIZED"
    OPENED = "OPENED"
    ANALYZED = "ANALYZED"
    RESEALED = "RESEALED"
    TRANSFERRED = "TRANSFERRED"
    RELEASED = "RELEASED"
    RETURNED = "RETURNED"
    DESTROYED = "DESTROYED"


# ──────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DigitalSignature:
    """Detached signature over the custody record's canonical form."""
    algorithm: str = "Ed25519"
    signature: str = ""
    public_key_pem: str = ""
    signed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signed_by: str = ""


@dataclass
class CustodyRecord:
    """One custody link for one piece of evidence.

    `record_hash` chains the record: sha256 over the canonical form (plain
    fields + previous_record_hash). Tampering with any stored field breaks
    both the recomputed hash and the digital signature.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    evidence_id: str = ""
    sequence: int = 0
    actor_id: str = ""
    actor_role: ActorRole = ActorRole.EVIDENCE_CUSTODIAN
    action: CustodyAction = CustodyAction.COLLECTED
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    description: str = ""
    location: str = ""
    notes: Dict[str, Any] = field(default_factory=dict)
    previous_record_hash: str = ""
    record_hash: str = ""
    digital_signature: Optional[DigitalSignature] = None

    def canonical(self) -> bytes:
        """Canonical bytes hashed and signed — sort_keys + tight separators."""
        data = {
            "id": self.id,
            "evidence_id": self.evidence_id,
            "sequence": self.sequence,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role.value,
            "action": self.action.value,
            "timestamp": self.timestamp,
            "description": self.description,
            "location": self.location,
            "notes": self.notes,
            "previous_record_hash": self.previous_record_hash,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# SIGNING
# ──────────────────────────────────────────────────────────────────────────────

class CustodySigner:
    """Ed25519 signer for custody records.

    Every ChainOfCustody holds one; production callers must keep the private
    key outside the database (the db stores only the public PEM, the
    signature and a boolean verify state).
    """

    def __init__(self, label: str = "custody"):
        self.label = label
        self._private: Ed25519PrivateKey = Ed25519PrivateKey.generate()
        self._public_pem = (
            self._private.public_key()
            .public_bytes(serialization.Encoding.PEM,
                          serialization.PublicFormat.SubjectPublicKeyInfo)
            .decode("utf-8")
        )

    @property
    def public_key_pem(self) -> str:
        return self._public_pem

    def sign_bytes(self, data: bytes) -> str:
        """Raw Ed25519 over data, base64-encoded (64-byte ed521-free signature)."""
        import base64
        return base64.b64encode(self._private.sign(data)).decode("ascii")

    def verify_bytes(self, data: bytes, public_key_pem: str,
                     signature: str) -> bool:
        """Verify with a given public PEM — the tamper path."""
        import base64
        try:
            pub = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
            if not isinstance(pub, Ed25519PublicKey):
                return False
            pub.verify(base64.b64decode(signature), data)
            return True
        except (InvalidSignature, UnsupportedAlgorithm, ValueError, TypeError):
            return False  # scanner:ignore except_return_default -- verification failure IS the False contract


# ──────────────────────────────────────────────────────────────────────────────
# TRANSACTION HELPER (named by the recovered fragment)
# ──────────────────────────────────────────────────────────────────────────────

@contextmanager
def get_db_transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    """sqlite3 connection as a managed transaction.

    Commit on clean exit, rollback + re-raise on error, always close — the
    close is the point: a leaked connection on this codebase's Windows hosts
    wedges every TemporaryDirectory holding the db with WinError 32.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# CHAIN OF CUSTODY
# ──────────────────────────────────────────────────────────────────────────────

class ChainOfCustody:
    """Tamper-evident, per-evidence chain of custody.

    Each add CustodyRecord is Ed25519-signed and hash-chained to its
    predecessor for the same evidence_id. verify_custody_chain recomputes
    every hash and re-verifies every signature; anything altered after the
    fact is reported, not silently accepted.
    """

    def __init__(self, db_path = Path("custody.db"), signer: Optional[CustodySigner] = None):
        self.db_path = Path(db_path)
        self.signer = signer or CustodySigner()
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        """Initialize the custody database (try/finally: never leak a conn)."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(
                """
                    CREATE TABLE IF NOT EXISTS custody_records (
                        id TEXT PRIMARY KEY,
                        evidence_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        actor_id TEXT NOT NULL,
                        actor_role TEXT NOT NULL,
                        action TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        description TEXT,
                        location TEXT,
                        notes TEXT,
                        previous_record_hash TEXT NOT NULL,
                        record_hash TEXT NOT NULL,
                        verified INTEGER DEFAULT 0,
                        verified_at TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        UNIQUE (evidence_id, sequence)
                    );

                    CREATE TABLE IF NOT EXISTS digital_signatures (
                        id TEXT PRIMARY KEY,
                        record_id TEXT NOT NULL,
                        algorithm TEXT NOT NULL,
                        signature TEXT NOT NULL,
                        public_key_pem TEXT NOT NULL,
                        signed_at TEXT NOT NULL,
                        signed_by TEXT NOT NULL,
                        verified INTEGER DEFAULT 0,
                        verified_at TEXT,
                        FOREIGN KEY (record_id) REFERENCES custody_records(id)
                    );

                    CREATE TABLE IF NOT EXISTS custody_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        evidence_id TEXT,
                        actor_id TEXT,
                        actor_role TEXT,
                        event TEXT,
                        details TEXT,
                        timestamp TEXT DEFAULT (datetime('now')),
                        event_hash TEXT
                    );

                    CREATE INDEX IF NOT EXISTS idx_custody_evidence
                        ON custody_records(evidence_id, sequence);
                    CREATE INDEX IF NOT EXISTS idx_custody_sig_record
                        ON digital_signatures(record_id);
                """
            )
            conn.commit()
        finally:
            conn.close()

    # ── CORE WRITE PATH — the recovered fragment's shape, kept verbatim ──

    def add_custody_record(self, record: CustodyRecord) -> CustodyRecord:
        """Sign, chain, store and audit one custody record.

        Called with an unsaved CustodyRecord (no id/hash/sig needed — those
        are set here, not by callers, so callers cannot forge a half-built
        record). Returns the persisted record with hash and signature set.
        """
        if record.id is None or not record.id.strip():
            record.id = str(uuid.uuid4())
        if not record.evidence_id.strip():
            raise ValueError("evidence_id is required for a custody record")

        with self._lock:
            # 1. Chain: previous record_hash for this evidence (or "" at start)
            prev = self._last_record_hash(record.evidence_id)
            record.previous_record_hash = prev
            record.sequence = self._next_sequence(record.evidence_id)

            # 2. Hash the canonical form (the digest that also proves sequence)
            record.record_hash = hashlib.sha256(record.canonical()).hexdigest()

            # 3. Sign the same canonical bytes with our Ed25519 key
            signature = DigitalSignature(
                signature=self.signer.sign_bytes(record.canonical()),
                public_key_pem=self.signer.public_key_pem,
                signed_by=self.signer.label or "ChainOfCustody",
            )
            record.digital_signature = signature

            with get_db_transaction(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO custody_records (id, evidence_id, sequence,
                        actor_id, actor_role, action, timestamp, description,
                        location, notes, previous_record_hash, record_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.id, record.evidence_id, record.sequence,
                    record.actor_id, record.actor_role.value, record.action.value,
                    record.timestamp, record.description or "",
                    record.location or "", json.dumps(record.notes),
                    record.previous_record_hash, record.record_hash,
                ))
                conn.execute("""
                    INSERT INTO digital_signatures (id, record_id, algorithm, signature,
                        public_key_pem, signed_at, signed_by, verified, verified_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()), record.id, signature.algorithm,
                    signature.signature, signature.public_key_pem,
                    signature.signed_at, signature.signed_by,
                    0, None
                ))
                conn.commit()

        # Log audit entry
        self._log_audit(record.evidence_id, record.actor_id, record.actor_role.value,
                        f"custody_record_{record.action.value.lower()}",
                        f"Added custody record: {record.description}")

        return record

    def _last_record_hash(self, evidence_id: str) -> str:
        with get_db_transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT record_hash FROM custody_records "
                "WHERE evidence_id = ? ORDER BY sequence DESC LIMIT 1",
                (evidence_id,)
            ).fetchone()
            return row[0] if row else ""

    def _next_sequence(self, evidence_id: str) -> int:
        with get_db_transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(sequence) FROM custody_records WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
            return (row[0] or 0) + 1

    def _log_audit(self, evidence_id: str, actor_id: str, actor_role: str,
                   event: str, details: str) -> None:
        """Local audit row with its own tamper-evident digest (closure hash)."""
        with get_db_transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT event_hash FROM custody_audit "
                "WHERE evidence_id IS NULL OR evidence_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (evidence_id,),
            ).fetchone()
            previous = row[0] if row else ""
            payload = f"{evidence_id}|{actor_id}|{actor_role}|{event}|{details}|{previous}"
            event_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            conn.execute(
                "INSERT INTO custody_audit (evidence_id, actor_id, actor_role, "
                "event, details, event_hash) VALUES (?, ?, ?, ?, ?, ?)",
                (evidence_id, actor_id, actor_role, event, details, event_hash),
            )

    # ── READ PATH ──────────────────────────────────────────────────────────

    def _row_to_record(self, row: sqlite3.Row) -> CustodyRecord:
        rec = CustodyRecord(
            id=row["id"],
            evidence_id=row["evidence_id"],
            sequence=row["sequence"],
            actor_id=row["actor_id"],
            actor_role=ActorRole(row["actor_role"]),
            action=CustodyAction(row["action"]),
            timestamp=row["timestamp"],
            description=row["description"],
            location=row["location"],
            notes=json.loads(row["notes"]) if row["notes"] else {},
            previous_record_hash=row["previous_record_hash"],
            record_hash=row["record_hash"],
        )
        return rec

    def records_for_evidence(self, evidence_id: str, with_signatures: bool = False) -> List[CustodyRecord]:
        """Custody records for one evidence_id, in chain order.

        `with_signatures=True` also attaches each record's DigitalSignature,
        so verify_signature can be called on the returned objects directly.
        """
        with get_db_transaction(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM custody_records WHERE evidence_id = ? "
                "ORDER BY sequence",
                (evidence_id,)
            ).fetchall()
            records = [self._row_to_record(r) for r in rows]
        if with_signatures:
            for rec in records:
                sig_row = self._signature_row(rec.id)
                if sig_row is not None:
                    rec.digital_signature = DigitalSignature(
                        algorithm=sig_row["algorithm"],
                        signature=sig_row["signature"],
                        public_key_pem=sig_row["public_key_pem"],
                        signed_at=sig_row["signed_at"],
                        signed_by=sig_row["signed_by"],
                    )
        return records

    def _signature_row(self, record_id: str) -> Optional[sqlite3.Row]:
        with get_db_transaction(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT * FROM digital_signatures WHERE record_id = ?",
                (record_id,),
            ).fetchone()

    # ── VERIFICATION ───────────────────────────────────────────────────────

    def _recompute_hash(self, rec: CustodyRecord) -> str:
        """Hash of a record as if reconstructed from its stored row."""
        return hashlib.sha256(rec.canonical()).hexdigest()

    def verify_signature(self, record: CustodyRecord) -> bool:
        """True iff the stored Ed25519 signature verifies against the
        record's canonical form with the stored public PEM."""
        if record.digital_signature is None:
            return False
        return self.signer.verify_bytes(
            record.canonical(),
            record.digital_signature.public_key_pem,
            record.digital_signature.signature,
        )

    def verify_custody_chain(self, evidence_id: str) -> Tuple[bool, List[str]]:
        """Verify every custody hash link and every signature for evidence_id.

        Recomputes each record's hash from the row (any field altered breaks
        it), requires the previous_record_hash to link to the prior record's
        hash, and re-verifies the detached signature. Empty evidence chain
        is vacuously ok (negative control in the selftest covers a tampered
        chain being reported).
        """
        records = self.records_for_evidence(evidence_id)
        if not records:
            return True, []
        errors: List[str] = []
        prev_hash = ""
        for i, rec in enumerate(records):
            if rec.sequence != i + 1:
                errors.append(f"record {rec.id}: sequence {rec.sequence} "
                              f"expected {i+1} (chain gap)")
            if i == 0:
                if rec.previous_record_hash != "":
                    errors.append(f"record {rec.id}: genesis previous_record_hash "
                                  f"must be empty, got {rec.previous_record_hash!r}")
            else:
                if rec.previous_record_hash != prev_hash:
                    errors.append(f"record {rec.id}: previous_record_hash does "
                                  f"not link to record {prev_hash}")
            recomputed = self._recompute_hash(rec)
            if not hmac.compare_digest(recomputed, rec.record_hash):
                errors.append(f"record {rec.id}: record_hash recomputed to "
                              f"{recomputed} but stored {rec.record_hash}")
            sig_row = self._signature_row(rec.id)
            if sig_row is None:
                errors.append(f"record {rec.id}: digital signature missing")
            else:
                sig = DigitalSignature(
                    algorithm=sig_row["algorithm"],
                    signature=sig_row["signature"],
                    public_key_pem=sig_row["public_key_pem"],
                    signed_at=sig_row["signed_at"],
                    signed_by=sig_row["signed_by"],
                )
                with_sig = rec
                with_sig.digital_signature = sig
                with_sig.digital_signature = sig
                if not self.verify_signature(with_sig):
                    errors.append(f"record {rec.id}: signature does not verify "
                                  f"against record canonical bytes")
            if sig_row is None and rec.record_hash == "":
                errors.append(f"record {rec.id}: empty record_hash and no signature")
            prev_hash = rec.record_hash
        return (len(errors) == 0), errors

    def mark_verified(self, evidence_id: str) -> None:
        """Flip verified/verified_at on all digital_signatures rows for records
        of this evidence_id after a successful verify_custody_chain call.

        The signature row's `verified` flag reading 0 on disk is what court
        processes look for at intake; call after a real verification, not
        before.
        """
        ok, errors = self.verify_custody_chain(evidence_id)
        if not ok:
            raise ValueError(f"cannot mark verified: {errors}")
        with get_db_transaction(self.db_path) as conn:
            conn.execute("""
                UPDATE digital_signatures SET verified = 1, verified_at = ?
                WHERE record_id IN (
                    SELECT id FROM custody_records WHERE evidence_id = ?
                )
            """, (datetime.now(timezone.utc).isoformat(), evidence_id))


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE
# ──────────────────────────────────────────────────────────────────────────────

def create_chain_of_custody(db_path = Path("custody.db"),
                            signer: Optional[CustodySigner] = None) -> ChainOfCustody:
    return ChainOfCustody(db_path=db_path, signer=signer)


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST (0B-C: positive + negative controls)
# ──────────────────────────────────────────────────────────────────────────────

def selftest() -> Tuple[int, List[str]]:
    """Self-test of the chain-of-custody module. Positive controls: a real
    chain verifies; signatures verify. Negative controls: a tampered record
    and an inserted forged record are both reported, never accepted."""
    import tempfile
    lines: List[str] = []
    failures = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        signer = CustodySigner(label="selftest-analyst")
        coc = ChainOfCustody(db_path=tmp / "custody.db", signer=signer)

        ev = "EVD-TEST-001"
        records = [
            CustodyRecord(evidence_id=ev, actor_id="clint",
                          actor_role=ActorRole.EVIDENCE_CUSTODIAN,
                          action=CustodyAction.COLLECTED,
                          description="Evidence collected from workstation_1",
                          location="workstation_1", notes={"hash": "abc123"}),
            CustodyRecord(evidence_id=ev, actor_id="jane",
                          actor_role=ActorRole.ANALYST,
                          action=CustodyAction.ANALYZED,
                          description="Disk image analysed",
                          location="lab_a", notes={"tool": "volatility"}),
            CustodyRecord(evidence_id=ev, actor_id="jane",
                          actor_role=ActorRole.EVIDENCE_CUSTODIAN,
                          action=CustodyAction.TRANSFERRED,
                          description="Custody transferred back to vault",
                          location="vault"),
        ]
        for rec in records:
            coc.add_custody_record(rec)

        ok, errors = coc.verify_custody_chain(ev)
        if ok:
            lines.append("PASS: full chain verifies (3 records)")
        else:
            failures += 1
            lines.append(f"FAIL: chain verify reported {errors}")

        # Positive: signature of the last record verifies
        recs = coc.records_for_evidence(ev, with_signatures=True)
        if recs[2].digital_signature and coc.verify_signature(recs[2]):
            lines.append("PASS: signature verifies for a genuine record")
        else:
            failures += 1
            lines.append("FAIL: signature verify failed on an honest record")

        # Negative 0B-C #1: tamper the middle record's description in the DB
        with get_db_transaction(coc.db_path) as conn:
            conn.execute("UPDATE custody_records SET description = 'tampered' "
                         "WHERE sequence = 2 AND evidence_id = ?", (ev,))
        ok2, errors2 = coc.verify_custody_chain(ev)
        if not ok2:
            lines.append("PASS: tampered description detected in chain verify")
        else:
            failures += 1
            lines.append("FAIL: tampered record accepted by verify_custody_chain")

        # Negative 0B-C #2: a record inserted without going through
        # add_custody_record has no signature → must be reported.
        forged = CustodyRecord(evidence_id="EVD-FORGED",
                               actor_id="attacker",
                               action=CustodyAction.RELEASED,
                               description="forged release")
        coc.add_custody_record(forged)
        with get_db_transaction(coc.db_path) as conn:
            conn.execute("DELETE FROM digital_signatures WHERE record_id = ?",
                         (forged.id,))
        ok3, errors3 = coc.verify_custody_chain("EVD-FORGED")
        if not ok3 and any("signature" in e for e in errors3):
            lines.append("PASS: forged record without signature is reported")
        else:
            failures += 1
            lines.append(f"FAIL: forged record not caught: {errors3}")

        # Honest-skip state — the marker the old stub used to report.
        lines.append(f"recovered+rebuilt: module now owns the custody chain "
                     f"(t-0002 closed 2026-11-03)")

    return failures, lines


if __name__ == "__main__":
    import sys
    failures, lines = selftest()
    for line in lines:
        print(line)
    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failures)")
    sys.exit(0 if failures == 0 else 1)
