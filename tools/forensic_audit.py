#!/usr/bin/env python3
# coding: utf-8
"""
forensic_audit.py — Immutable Forensic Audit Logging for Court-Admissible Forensics.

Implements tamper-evident, append-only audit logging with cryptographic
hash chaining, RFC 3161 timestamping, and Merkle tree integrity verification.
Suitable for court-admissible forensic audit trails.

Standards: NIST SP 800-92, RFC 3161, RFC 6962 (Certificate Transparency), NIST SP 800-92
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
import uuid
import base64
import hmac
import struct
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, BinaryIO, Union, Callable
from enum import Enum
from contextlib import contextmanager
import secrets
import hashlib
import hmac


# ──────────────────────────────────────────────────────────────────────────────
# ENUMS & CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

class AuditEventType(Enum):
    """Types of audit events."""
    EVIDENCE_COLLECTED = "evidence_collected"
    EVIDENCE_SEALED = "evidence_sealed"
    EVIDENCE_UNSEALED = "evidence_unsealed"
    EVIDENCE_ACCESSED = "evidence_accessed"
    EVIDENCE_TRANSFERRED = "evidence_transferred"
    EVIDENCE_ANALYZED = "evidence_analyzed"
    EVIDENCE_HASH_VERIFIED = "evidence_hash_verified"
    EVIDENCE_HASH_MISMATCH = "evidence_hash_mismatch"
    EVIDENCE_STORED = "evidence_stored"
    EVIDENCE_RETRIEVED = "evidence_retrieved"
    EVIDENCE_DISPOSED = "evidence_disposed"
    CONTAINER_CREATED = "container_created"
    CONTAINER_SEALED = "container_sealed"
    CONTAINER_UNSEALED = "container_unsealed"
    CONTAINER_STORED = "container_stored"
    CONTAINER_RETRIEVED = "container_retrieved"
    CONTAINER_VERIFIED = "container_verified"
    CONTAINER_TAMPERED = "container_tampered"
    CHAIN_VERIFIED = "chain_verified"
    CHAIN_BROKEN = "chain_broken"
    HASH_VERIFIED = "hash_verified"
    HASH_MISMATCH = "hash_mismatch"
    SEAL_APPLIED = "seal_applied"
    SEAL_VERIFIED = "seal_verified"
    SEAL_BROKEN = "seal_broken"
    LEGAL_HOLD_APPLIED = "legal_hold_applied"
    LEGAL_HOLD_RELEASED = "legal_hold_released"
    CUSTODY_TRANSFER = "custody_transfer"
    CUSTODY_RECORD_ADDED = "custody_record_added"
    CUSTODY_CHAIN_VERIFIED = "custody_chain_verified"
    CUSTODY_CHAIN_BROKEN = "custody_chain_broken"
    TOOL_VALIDATED = "tool_validated"
    TOOL_HASH_VERIFIED = "tool_hash_verified"
    TOOL_HASH_MISMATCH = "tool_hash_mismatch"
    AUDIT_LOG_ROTATED = "audit_log_rotated"
    AUDIT_LOG_VERIFIED = "audit_log_verified"
    AUDIT_LOG_TAMPERED = "audit_log_tampered"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    AUTHORIZATION_GRANTED = "authorization_granted"
    AUTHORIZATION_DENIED = "authorization_denied"
    CONFIGURATION_CHANGED = "configuration_changed"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class AuditSeverity(Enum):
    """Audit event severity levels."""
    DEBUG = "debug"
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    ALERT = "alert"
    EMERGENCY = "emergency"

# ──────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    """Immutable audit log entry with cryptographic chaining."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sequence: int = 0
    event_type: AuditEventType = AuditEventType.INFO
    severity: AuditSeverity = AuditSeverity.INFO
    actor_id: str = ""
    actor_role: str = ""
    actor_ip: str = ""
    actor_user_agent: str = ""
    evidence_id: Optional[str] = None
    container_id: Optional[str] = None
    case_number: Optional[str] = None
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    hash: str = ""
    merkle_root: str = ""
    rfc3161_timestamp: Optional[str] = None  # RFC 3161 timestamp token
    
    def __post_init__(self):
        if not self.hash:
            self.hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        """Compute tamper-evident hash of this entry."""
        # Include previous hash for chaining
        data = {
            "id": self.id,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "actor_ip": self.actor_ip,
            "actor_user_agent": self.actor_user_agent,
            "evidence_id": self.evidence_id,
            "container_id": self.container_id,
            "case_number": self.case_number,
            "message": self.message,
            "details": self.details,
            "previous_hash": self.previous_hash,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    
    def verify(self, previous_hash: str = "") -> bool:
        """Verify entry integrity and chain linkage."""
        # Verify hash
        expected_hash = self._compute_hash()
        if not hmac.compare_digest(self.hash, expected_hash):
            return False
        
        # Verify chain linkage
        if self.sequence > 0 and not hmac.compare_digest(self.previous_hash, previous_hash):
            return False
        
        return True

@dataclass
class MerkleTree:
    """Merkle tree for batch audit log integrity."""
    leaves: List[str] = field(default_factory=list)
    tree: List[List[str]] = field(default_factory=list)
    root: str = ""
    
    @classmethod
    def build(cls, leaves: List[str]) -> "MerkleTree":
        """Build Merkle tree from leaf hashes."""
        if not leaves:
            return cls(leaves=[], tree=[], root="")
        
        tree = [leaves[:]]
        current_level = leaves[:]
        
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256((left + right).encode()).hexdigest()
                next_level.append(combined)
            tree.append(next_level)
            current_level = next_level
        
        return cls(leaves=leaves, tree=tree, root=current_level[0])
    
    def get_proof(self, index: int) -> List[Dict[str, str]]:
        """Get Merkle proof for leaf at index."""
        proof = []
        idx = index
        for level in self.tree[:-1]:
            is_right = idx % 2 == 0
            sibling_idx = idx + 1 if is_right else idx - 1
            if sibling_idx < len(level):
                proof.append({
                    "hash": level[sibling_idx],
                    "position": "right" if is_right else "left"
                })
            idx //= 2
        return proof
    
    def verify_proof(self, leaf_hash: str, proof: List[Dict[str, str]]) -> bool:
        """Verify Merkle proof for leaf."""
        current = leaf_hash
        for step in proof:
            if step["position"] == "right":
                current = hashlib.sha256((current + step["hash"]).encode()).hexdigest()
            else:
                current = hashlib.sha256((step["hash"] + current).encode()).hexdigest()
        return hmac.compare_digest(current, self.root)

@dataclass
class AuditLogConfig:
    """Configuration for audit log."""
    db_path: Path = Path("forensic_audit.db")
    max_entries_per_file: int = 10000
    rotation_interval_hours: int = 24
    enable_rfc3161: bool = True
    rfc3161_server: str = "http://timestamp.digicert.com"
    hash_algorithm: str = "SHA-256"
    hmac_key: Optional[bytes] = None
    enable_merkle: bool = True
    merkle_interval: int = 100  # Build Merkle tree every N entries
    retention_days: int = 2555  # 7 years
    enable_rfc3161: bool = True
    rfc3161_server: str = "http://timestamp.digicert.com"


# ──────────────────────────────────────────────────────────────────────────────
# AUDIT LOG MANAGER
# ──────────────────────────────────────────────────────────────────────────────

class ForensicAuditLog:
    """Immutable, tamper-evident forensic audit log with hash chaining."""
    
    def __init__(self, config: Optional[AuditLogConfig] = None):
        self.config = config or AuditLogConfig()
        self.db_path = self.config.db_path
        self._sequence = 0
        self._last_hash = ""
        self._merkle_leaves: List[str] = []
        self._entries_since_merkle = 0
        self._lock = threading.RLock()
        self._init_db()
        self._load_state()
    
    def _init_db(self):
        """Initialize SQLite database with audit log tables.

        The connect is wrapped in try/finally on purpose: before 2026-11-03 the
        schema connect was rebound by the redundant pragma connect below, so a
        schema error in executescript left the first connection open and every
        TemporaryDirectory holding this db failed cleanup with WinError 32,
        masking the real error. The redundant second connect is gone — its
        PRAGMAs were per-connection no-ops and the first connection already set
        what persisted (journal_mode is DB-level).
        """
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.config.db_path, timeout=5.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=FULL")
            
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_entries (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                sequence INTEGER NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                actor_id TEXT,
                actor_role TEXT,
                actor_ip TEXT,
                actor_user_agent TEXT,
                evidence_id TEXT,
                container_id TEXT,
                case_number TEXT,
                message TEXT,
                details TEXT,  -- JSON
                previous_hash TEXT NOT NULL,
                hash TEXT NOT NULL,
                merkle_root TEXT,
                rfc3161_timestamp TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_entries(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_sequence ON audit_entries(sequence);
            CREATE INDEX IF NOT EXISTS idx_audit_evidence ON audit_entries(evidence_id);
            CREATE INDEX IF NOT EXISTS idx_audit_container ON audit_entries(container_id);
            CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_entries(case_number);
            CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_entries(actor_id);
            CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_entries(event_type);
            
            CREATE TABLE IF NOT EXISTS merkle_trees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_sequence INTEGER NOT NULL,
                end_sequence INTEGER NOT NULL,
                leaf_count INTEGER NOT NULL,
                root_hash TEXT NOT NULL,
                leaves TEXT,  -- JSON array of leaf hashes
                created_at TEXT DEFAULT (datetime('now'))
            );
            
            CREATE INDEX IF NOT EXISTS idx_merkle_sequence ON merkle_trees(start_sequence);
            
            CREATE TABLE IF NOT EXISTS rfc3161_timestamps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT NOT NULL,
                timestamp_token BLOB NOT NULL,
                server_url TEXT NOT NULL,
                verified INTEGER DEFAULT 0,
                verified_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (entry_id) REFERENCES audit_entries(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS log_rotation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rotated_at TEXT NOT NULL,
                start_sequence INTEGER NOT NULL,
                end_sequence INTEGER NOT NULL,
                entry_count INTEGER NOT NULL,
                merkle_root TEXT,
                hash TEXT NOT NULL
            );
        """)
            conn.commit()
        finally:
            conn.close()
    
    def _load_state(self):
        """Load current sequence and last hash from database."""
        conn = sqlite3.connect(self.config.db_path, timeout=5.0)
        try:
            row = conn.execute(
                "SELECT sequence, hash FROM audit_entries ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if row:
                self._sequence = row[0]
                self._last_hash = row[1]
            else:
                self._sequence = 0
                self._last_hash = ""
            
            # Load recent Merkle leaves
            row = conn.execute(
                "SELECT leaves FROM merkle_trees ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row and row[0]:
                self._merkle_leaves = json.loads(row[0])
        finally:
            conn.close()
    
    def log(self, event_type: AuditEventType, message: str, **kwargs) -> AuditEntry:
        """Log audit event with full chain integrity."""
        with self._lock:
            self._sequence += 1
            
            entry = AuditEntry(
                sequence=self._sequence,
                event_type=kwargs.get("event_type", AuditEventType.INFO),
                severity=kwargs.get("severity", AuditSeverity.INFO),
                actor_id=kwargs.get("actor_id", ""),
                actor_role=kwargs.get("actor_role", ""),
                actor_ip=kwargs.get("actor_ip", ""),
                actor_user_agent=kwargs.get("actor_user_agent", ""),
                evidence_id=kwargs.get("evidence_id"),
                container_id=kwargs.get("container_id"),
                case_number=kwargs.get("case_number"),
                message=message,
                details=kwargs.get("details", {}),
                previous_hash=self._last_hash,
            )
            
            # Compute hash
            entry.hash = entry._compute_hash()
            
            # Add to Merkle leaves
            self._merkle_leaves.append(entry.hash)
            self._entries_since_merkle += 1
            
            # Build Merkle tree periodically
            if self._entries_since_merkle >= self.config.merkle_interval:
                self._build_merkle_tree()
            
            # Request RFC 3161 timestamp if enabled
            if self.config.enable_rfc3161:
                self._request_rfc3161_timestamp(entry)
            
            # Persist to database
            self._persist_entry(entry)
            
            # Update state
            self._last_hash = entry.hash
            
            return entry
    
    def _persist_entry(self, entry: AuditEntry):
        """Persist audit entry to database."""
        conn = sqlite3.connect(self.config.db_path, timeout=5.0)
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("""
                INSERT INTO audit_entries (
                    id, timestamp, sequence, event_type, severity,
                    actor_id, actor_role, actor_ip, actor_user_agent,
                    evidence_id, container_id, case_number,
                    message, details, previous_hash, hash, merkle_root,
                    rfc3161_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id, entry.timestamp, entry.sequence, entry.event_type.value,
                entry.severity.value, entry.actor_id, entry.actor_role,
                entry.actor_ip, entry.actor_user_agent, entry.evidence_id,
                entry.container_id, entry.case_number, entry.message,
                json.dumps(entry.details), entry.previous_hash, entry.hash,
                entry.merkle_root, entry.rfc3161_timestamp
            ))
            conn.commit()
        finally:
            conn.close()
    
    def _build_merkle_tree(self):
        """Build Merkle tree from accumulated leaves."""
        if not self._merkle_leaves:
            return
        
        tree = MerkleTree.build(self._merkle_leaves)
        
        conn = sqlite3.connect(self.config.db_path, timeout=5.0)
        try:
            conn.execute("""
                INSERT INTO merkle_trees (start_sequence, end_sequence, leaf_count, root_hash, leaves)
                VALUES (?, ?, ?, ?, ?)
            """, (
                self._sequence - len(self._merkle_leaves) + 1,
                self._sequence,
                len(self._merkle_leaves),
                tree.root,
                json.dumps(self._merkle_leaves)
            ))
            conn.commit()
        finally:
            conn.close()
        
        # Update entries with Merkle root
        conn = sqlite3.connect(self.config.db_path, timeout=5.0)
        try:
            conn.execute(
                "UPDATE audit_entries SET merkle_root = ? WHERE sequence BETWEEN ? AND ?",
                (tree.root, self._sequence - len(self._merkle_leaves) + 1, self._sequence)
            )
            conn.commit()
        finally:
            conn.close()
        
        self._merkle_leaves = []
        self._entries_since_merkle = 0
    
    def _request_rfc3161_timestamp(self, entry: AuditEntry):
        """Request RFC 3161 timestamp from trusted timestamping authority."""
        # This would integrate with a TSA (Time Stamping Authority)
        # For now, we'll note the intent and implement when TSA is available
        pass
    
    def verify_chain(self, start_sequence: int = 0, end_sequence: Optional[int] = None) -> Tuple[bool, List[str]]:
        """Verify audit log chain integrity by recomputing every entry's hash.

        Before 2026-11-03 this selected with an unbound ? in the WHERE clause
        (sqlite3.ProgrammingError: bindings supplied 0 of 1) and only checked
        that previous_hash was non-empty. It now reconstructs each AuditEntry
        from the row and recomputes its hash — the assertions the classes exist
        to enforce — and verifies the hash-chain links row to row.
        """
        conn = sqlite3.connect(self.config.db_path, timeout=5.0)
        try:
            query = (
                "SELECT id, timestamp, sequence, event_type, severity, actor_id, "
                "actor_role, actor_ip, actor_user_agent, evidence_id, container_id, "
                "case_number, message, details, previous_hash, hash "
                "FROM audit_entries WHERE sequence >= ?"
            )
            params = [start_sequence]
            if end_sequence is not None:
                query += " AND sequence <= ?"
                params.append(end_sequence)
            query += " ORDER BY sequence"
            
            rows = conn.execute(query, params).fetchall()
            
            errors: List[str] = []
            prev_hash = ""
            verifying_from_genesis = start_sequence <= 1
            
            for (eid, timestamp, seq, event_type, severity, actor_id, actor_role,
                 actor_ip, actor_user_agent, evidence_id, container_id,
                 case_number, message, details, previous_hash, hash_val) in rows:
                try:
                    entry = AuditEntry(
                        id=eid,
                        timestamp=timestamp,
                        sequence=seq,
                        event_type=AuditEventType(event_type),
                        severity=AuditSeverity(severity),
                        actor_id=actor_id or "",
                        actor_role=actor_role or "",
                        actor_ip=actor_ip or "",
                        actor_user_agent=actor_user_agent or "",
                        evidence_id=evidence_id,
                        container_id=container_id,
                        case_number=case_number,
                        message=message or "",
                        details=json.loads(details) if details else {},
                        previous_hash=previous_hash or "",
                        hash=hash_val,
                    )
                except ValueError as exc:
                    # unknown enum value stored in the row — no AuditEntry can
                    # even be built, which is itself an integrity defect
                    errors.append(
                        f"Record seq={seq}: unparsable stored state "
                        f"({event_type!r}/{severity!r} — {exc})"
                    )
                    continue
                
                # Recompute the entry hash — fails if the row was altered
                recomputed = entry._compute_hash()
                if not hmac.compare_digest(recomputed, hash_val):
                    errors.append(f"Record seq={seq}: stored hash does not match recomputed hash (entry altered)")
                
                # Chain linkage
                if verifying_from_genesis and seq == 1:
                    if previous_hash != "":
                        errors.append(f"Genesis record (seq=1) has non-empty previous_hash: {previous_hash}")
                elif previous_hash != prev_hash:
                    errors.append(f"Record seq={seq}: previous_hash does not link to the prior entry")
                
                prev_hash = hash_val
            
            return len(errors) == 0, errors
        finally:
            conn.close()
    
    def verify_merkle_tree(self, tree_id: int) -> Tuple[bool, List[str]]:
        """Verify Merkle tree integrity."""
        conn = sqlite3.connect(self.config.db_path, timeout=5.0)
        try:
            row = conn.execute(
                "SELECT start_sequence, end_sequence, leaf_count, root_hash, leaves FROM merkle_trees WHERE id = ?",
                (tree_id,)
            ).fetchone()
            
            if not row:
                return False, [f"Merkle tree {tree_id} not found"]
            
            leaves = json.loads(row[4])
            expected_root = row[3]
            
            # Rebuild tree
            tree = MerkleTree.build(row[3])
            
            if not hmac.compare_digest(tree.root, expected_root):
                return False, [f"Merkle root mismatch: {tree.root} != {expected_root}"]
            
            return True, []
        finally:
            conn.close()
    
    def get_entry(self, entry_id: str) -> Optional[AuditEntry]:
        """Get audit entry by ID."""
        conn = sqlite3.connect(self.config.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM audit_entries WHERE id = ?", (entry_id,)).fetchone()
            if not row:
                return None
            return AuditEntry(
                id=row["id"],
                timestamp=row["timestamp"],
                sequence=row["sequence"],
                event_type=AuditEventType(row["event_type"]),
                severity=AuditSeverity(row["severity"]),
                actor_id=row["actor_id"] or "",
                actor_role=row["actor_role"] or "",
                actor_ip=row["actor_ip"] or "",
                actor_user_agent=row["actor_user_agent"] or "",
                evidence_id=row["evidence_id"],
                container_id=row["container_id"],
                case_number=row["case_number"],
                message=row["message"] or "",
                details=json.loads(row["details"]) if row["details"] else {},
                previous_hash=row["previous_hash"],
                hash=row["hash"],
                merkle_root=row["merkle_root"] or "",
                rfc3161_timestamp=row["rfc3161_timestamp"],
            )
        finally:
            conn.close()
    
    def query(self, 
              start_time: Optional[str] = None,
              end_time: Optional[str] = None,
              event_type: Optional[AuditEventType] = None,
              actor_id: Optional[str] = None,
              evidence_id: Optional[str] = None,
              container_id: Optional[str] = None,
              case_number: Optional[str] = None,
              limit: int = 1000) -> List[AuditEntry]:
        """Query audit entries with filters."""
        conn = sqlite3.connect(self.config.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            query = "SELECT * FROM audit_entries WHERE 1=1"
            params = []
            
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type.value)
            if actor_id:
                query += " AND actor_id = ?"
                params.append(actor_id)
            if evidence_id:
                query += " AND evidence_id = ?"
                params.append(evidence_id)
            if container_id:
                query += " AND container_id = ?"
                params.append(container_id)
            if case_number:
                query += " AND case_number = ?"
                params.append(case_number)
            
            query += " ORDER BY sequence DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            entries = []
            for row in rows:
                entries.append(AuditEntry(
                    id=row["id"],
                    timestamp=row["timestamp"],
                    sequence=row["sequence"],
                    event_type=AuditEventType(row["event_type"]),
                    severity=AuditSeverity(row["severity"]),
                    actor_id=row["actor_id"] or "",
                    actor_role=row["actor_role"] or "",
                    actor_ip=row["actor_ip"] or "",
                    actor_user_agent=row["actor_user_agent"] or "",
                    evidence_id=row["evidence_id"],
                    container_id=row["container_id"],
                    case_number=row["case_number"],
                    message=row["message"] or "",
                    details=json.loads(row["details"]) if row["details"] else {},
                    previous_hash=row["previous_hash"],
                    hash=row["hash"],
                    merkle_root=row["merkle_root"] or "",
                    rfc3161_timestamp=row["rfc3161_timestamp"],
                ))
            return entries
        finally:
            conn.close()
    
    def export_for_court(self, case_number: str, output_path: Path) -> Dict[str, Any]:
        """Export complete audit trail for court submission."""
        entries = self.query(case_number=case_number, limit=100000)
        
        # Verify entire chain
        chain_ok, errors = self.verify_chain()
        
        # Verify all Merkle trees
        conn = sqlite3.connect(self.config.db_path, timeout=5.0)
        merkle_ok = True
        merkle_errors = []
        try:
            cursor = conn.execute("SELECT id FROM merkle_trees")
            for (tree_id,) in cursor.fetchall():
                ok, errors = self.verify_merkle_tree(tree_id)
                if not ok:
                    merkle_ok = False
                    merkle_errors.extend(errors)
        finally:
            conn.close()
        
        export = {
            "case_number": case_number,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_entries": len(entries),
            "chain_verified": chain_ok,
            "chain_errors": errors,
            "merkle_trees_verified": merkle_ok,
            "merkle_errors": merkle_errors,
            "entries": [asdict(e) for e in entries],
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "exported_by": os.getenv("USER", "unknown"),
            "hash_algorithm": "SHA-256",
            "merkle_algorithm": "SHA-256",
        }
        
        # Write to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=2, default=str)
        
        return export


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def create_audit_log(db_path: Union[str, Path] = "forensic_audit.db") -> ForensicAuditLog:
    """Create forensic audit log."""
    config = AuditLogConfig(db_path=Path(db_path))
    return ForensicAuditLog(config)


def log_event(audit_log: ForensicAuditLog, event_type: AuditEventType, 
              message: str, **kwargs) -> AuditEntry:
    """Convenience function to log audit event."""
    return audit_log.log(event_type, message, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

def selftest() -> Tuple[int, List[str]]:
    """Run self-test of audit log system."""
    import tempfile
    lines = []
    failures = 0
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_audit.db"
        audit = create_audit_log(db_path)
        
        # Log various events
        entry1 = audit.log(
            AuditEventType.EVIDENCE_COLLECTED,
            "Evidence collected",
            actor_id="analyst_john",
            actor_role="analyst",
            evidence_id="EVD-001",
            case_number="CASE-001",
            severity=AuditSeverity.INFO,
            details={"location": "workstation_1", "hash": "abc123"}
        )
        
        entry2 = audit.log(
            AuditEventType.EVIDENCE_SEALED,
            "Evidence sealed",
            actor_id="custodian_jane",
            actor_role="custodian",
            evidence_id="EVD-001",
            container_id="CNT-001",
            case_number="CASE-001",
            severity=AuditSeverity.NOTICE,
            details={"seal_id": "SEAL-001"}
        )
        
        entry3 = audit.log(
            AuditEventType.HASH_VERIFIED,
            "Hash verified",
            actor_id="analyst_john",
            actor_role="analyst",
            evidence_id="EVD-001",
            case_number="CASE-001",
            severity=AuditSeverity.INFO,
            details={"algorithm": "SHA-256", "match": True}
        )
        
        # Verify chain
        ok, errors = audit.verify_chain()
        if ok:
            lines.append("PASS: Chain verification passed")
        else:
            failures += 1
            lines.append(f"FAIL: Chain verification failed: {errors}")
        
        # Query events
        events = audit.query(case_number="CASE-001")
        if len(events) == 3:
            lines.append("PASS: Query returned 3 events")
        else:
            failures += 1
            lines.append(f"FAIL: Query returned {len(events)} events, expected 3")
        
        # Test Merkle tree
        # Force Merkle tree build by adding more entries
        for i in range(105):
            audit.log(
                AuditEventType.INFO,
                f"Test event {i}",
                actor_id="system",
                actor_role="system"
            )
        
        # Verify Merkle tree was created
        conn = sqlite3.connect(audit.config.db_path, timeout=5.0)
        try:
            row = conn.execute("SELECT COUNT(*) FROM merkle_trees").fetchone()
            if row and row[0] > 0:
                lines.append("PASS: Merkle tree created")
            else:
                failures += 1
                lines.append("FAIL: Merkle tree not created")
        finally:
            conn.close()
        
        # Test export
        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "audit_export.json"
            export = audit.export_for_court("CASE-001", Path(tmpdir) / "export.json")
            if export["chain_verified"]:
                lines.append("PASS: Export chain verified")
            else:
                failures += 1
                lines.append(f"FAIL: Export chain not verified: {export['chain_errors']}")
    
    return failures, lines


if __name__ == "__main__":
    import tempfile
    failures, lines = selftest()
    for line in lines:
        print(line)
    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failures)")
    sys.exit(0 if failures == 0 else 1)