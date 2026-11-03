#!/usr/bin/env python3
# coding: utf-8
"""
forensic_hash.py — Cryptographic Hash Verification for Court-Admissible Forensics.

Implements multi-algorithm hash verification with NIST-approved algorithms,
HMAC-based integrity checking, and automated hash verification pipelines.
Standards: FIPS 180-4 (SHA-2), FIPS 198-1 (HMAC), NIST SP 800-107
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import sys
import threading
import secrets
import base64
import struct
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, BinaryIO, Union, Callable
from enum import Enum
from contextlib import contextmanager
import hashlib
import hmac
import concurrent.futures
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes as crypto_hashes


# ──────────────────────────────────────────────────────────────────────────────
# ENUMS & CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

class HashAlgorithm(Enum):
    """NIST-approved hash algorithms."""
    SHA_256 = "SHA-256"
    SHA_384 = "SHA-384"
    SHA_512 = "SHA-512"
    SHA_224 = "SHA-224"
    SHA_512_224 = "SHA-512/224"
    SHA_512_256 = "SHA-512/256"
    SHA3_256 = "SHA3-256"
    SHA3_384 = "SHA3-384"
    SHA3_512 = "SHA3-512"
    BLAKE2B = "BLAKE2b"
    BLAKE2S = "BLAKE2s"

class HashVerificationResult(Enum):
    """Result of hash verification."""
    MATCH = "match"
    MISMATCH = "mismatch"
    ERROR = "error"
    ALGORITHM_UNSUPPORTED = "algorithm_unsupported"

# ──────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class HashRecord:
    """Cryptographic hash record with metadata."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    algorithm: HashAlgorithm = HashAlgorithm.SHA_256
    value: str = ""
    source_path: str = ""
    source_size: int = 0
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    computed_by: str = ""
    verified: bool = False
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    verification_result: HashVerificationResult = HashVerificationResult.MATCH
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def compute(cls, data: bytes, algorithm: HashAlgorithm = HashAlgorithm.SHA_256,
                source_path: str = "", computed_by: str = "") -> "HashRecord":
        """Compute hash of data."""
        if algorithm == HashAlgorithm.SHA_256:
            h = hashlib.sha256(data).hexdigest()
        elif algorithm == HashAlgorithm.SHA_384:
            h = hashlib.sha384(data).hexdigest()
        elif algorithm == HashAlgorithm.SHA_512:
            h = hashlib.sha512(data).hexdigest()
        elif algorithm == HashAlgorithm.SHA_224:
            h = hashlib.sha224(data).hexdigest()
        elif algorithm == HashAlgorithm.SHA_512_224:
            h = hashlib.sha512_224(data).hexdigest()
        elif algorithm == HashAlgorithm.SHA_512_256:
            h = hashlib.sha512_256(data).hexdigest()
        elif algorithm == HashAlgorithm.SHA3_256:
            h = hashlib.sha3_256(data).hexdigest()
        elif algorithm == HashAlgorithm.SHA3_384:
            h = hashlib.sha3_384(data).hexdigest()
        elif algorithm == HashAlgorithm.SHA3_512:
            h = hashlib.sha3_512(data).hexdigest()
        elif algorithm == HashAlgorithm.BLAKE2B:
            h = hashlib.blake2b(data).hexdigest()
        elif algorithm == HashAlgorithm.BLAKE2S:
            h = hashlib.blake2s(data).hexdigest()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        
        return cls(
            algorithm=algorithm,
            value=h,
            source_size=len(data),
            computed_by="system",
        )
    
    def verify(self, data: bytes) -> HashVerificationResult:
        """Verify hash against data."""
        expected = HashRecord.compute(data, self.algorithm).value
        if hmac.compare_digest(self.value, expected):
            self.verified = True
            self.verified_at = datetime.now(timezone.utc).isoformat()
            return HashVerificationResult.MATCH
        else:
            self.verified = False
            self.verified_at = datetime.now(timezone.utc).isoformat()
            return HashVerificationResult.MISMATCH

@dataclass
class HMACRecord:
    """HMAC record for integrity verification."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    algorithm: str = "HMAC-SHA-256"
    key_id: str = ""
    hmac_value: str = ""
    data_hash: str = ""  # SHA-256 of data
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = ""
    verified: bool = False
    verified_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def compute(cls, data: bytes, key: bytes, key_id: str = "",
                algorithm: str = "HMAC-SHA-256", created_by: str = "") -> "HMACRecord":
        """Compute HMAC of data."""
        if algorithm == "HMAC-SHA-256":
            h = hmac.new(key, data, hashlib.sha256).hexdigest()
        elif algorithm == "HMAC-SHA-384":
            h = hmac.new(key, data, hashlib.sha384).hexdigest()
        elif algorithm == "HMAC-SHA-512":
            h = hmac.new(key, data, hashlib.sha512).hexdigest()
        else:
            raise ValueError(f"Unsupported HMAC algorithm: {algorithm}")
        
        data_hash = hashlib.sha256(data).hexdigest()
        
        return cls(
            algorithm=algorithm,
            key_id=key_id,
            hmac_value=h,
            data_hash=hashlib.sha256(data).hexdigest(),
            created_by="system",
        )
    
    def verify(self, data: bytes, key: bytes) -> bool:
        """Verify HMAC against data."""
        expected = HMACRecord.compute(data, key, self.key_id).hmac_value
        verified = hmac.compare_digest(self.hmac_value, expected)
        if verified:
            self.verified = True
            self.verified_at = datetime.now(timezone.utc).isoformat()
        return verified

@dataclass
class DigitalSignatureRecord:
    """Digital signature record for non-repudiation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    algorithm: str = "RSA-PSS-SHA256"
    signature: str = ""  # base64 encoded
    public_key_pem: str = ""
    signed_by: str = ""
    signed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data_hash: str = ""  # SHA-256 of signed data
    verified: bool = False
    verified_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def sign(cls, data: bytes, private_key_pem: str, signer: str) -> "DigitalSignatureRecord":
        """Sign data with private key."""
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )
        signature = private_key.sign(
            data,
            padding.PSS(
                mgf=padding.MGF1(crypto_hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            crypto_hashes.SHA256()
        )
        
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        
        return cls(
            algorithm="RSA-PSS-SHA256",
            signature=base64.b64encode(signature).decode(),
            public_key_pem=public_pem,
            signed_by=signer,
            data_hash=hashlib.sha256(data).hexdigest(),
        )
    
    def verify(self, data: bytes) -> bool:
        """Verify signature against data."""
        try:
            public_key = serialization.load_pem_public_key(
                self.public_key_pem.encode()
            )
            public_key.verify(
                base64.b64decode(self.signature),
                data,
                padding.PSS(
                    mgf=padding.MGF1(crypto_hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                crypto_hashes.SHA256()
            )
            return True
        except (InvalidSignature, UnsupportedAlgorithm, ValueError, TypeError):
            return False  # scanner:ignore except_return_default -- verification failure IS the False contract


# ──────────────────────────────────────────────────────────────────────────────
# HASH VERIFICATION MANAGER
# ──────────────────────────────────────────────────────────────────────────────

class ForensicHashManager:
    """Manages forensic hash records with SQLite backend."""
    
    def __init__(self, db_path: Union[str, Path] = "forensic_hashes.db"):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database.

        The connect is wrapped in try/finally on purpose: before 2026-11-03 a
        malformed schema here left the connection open on Windows and every
        TemporaryDirectory that held this db failed cleanup with WinError 32,
        masking the real schema error under the cleanup error.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=FULL")
            
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS hash_records (
                    id TEXT PRIMARY KEY,
                    algorithm TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source_path TEXT,
                    source_size INTEGER,
                    computed_at TEXT NOT NULL,
                    computed_by TEXT,
                    verified INTEGER DEFAULT 0,
                    verified_at TEXT,
                    verified_by TEXT,
                    verification_result TEXT,
                    metadata TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                
                CREATE TABLE IF NOT EXISTS hmac_records (
                    id TEXT PRIMARY KEY,
                    algorithm TEXT NOT NULL,
                    key_id TEXT,
                    hmac_value TEXT NOT NULL,
                    data_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT,
                    verified INTEGER DEFAULT 0,
                    verified_at TEXT,
                    metadata TEXT
                );
                
                CREATE TABLE IF NOT EXISTS signature_records (
                    id TEXT PRIMARY KEY,
                    algorithm TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    public_key_pem TEXT NOT NULL,
                    signed_by TEXT NOT NULL,
                    signed_at TEXT NOT NULL,
                    data_hash TEXT NOT NULL,
                    verified INTEGER DEFAULT 0,
                    verified_at TEXT,
                    metadata TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                
                CREATE TABLE IF NOT EXISTS hash_verification_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL,
                    record_type TEXT NOT NULL,  -- hash, hmac, signature
                    verified INTEGER NOT NULL,
                    verified_at TEXT,
                    verified_by TEXT,
                    result TEXT,
                    details TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                
                CREATE INDEX IF NOT EXISTS idx_hash_source ON hash_records(source_path);
                CREATE INDEX IF NOT EXISTS idx_hash_algorithm ON hash_records(algorithm);
                CREATE INDEX IF NOT EXISTS idx_hmac_key ON hmac_records(key_id);
                CREATE INDEX IF NOT EXISTS idx_sig_signer ON signature_records(signed_by);
                CREATE INDEX IF NOT EXISTS idx_verification_log ON hash_verification_log(record_id, record_type);
            """)
            conn.commit()
        finally:
            conn.close()
    
    def compute_file_hash(self, file_path: Union[str, Path],
                          algorithm: HashAlgorithm = HashAlgorithm.SHA_256,
                          chunk_size: int = 65536,
                          computed_by: str = "") -> HashRecord:
        """Compute hash of file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        hasher = self._get_hasher(algorithm)
        
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        
        hash_value = hasher.hexdigest()
        file_size = Path(file_path).stat().st_size
        
        record = HashRecord(
            algorithm=algorithm,
            value=hasher.hexdigest(),
            source_path=str(file_path),
            source_size=os.path.getsize(file_path),
            computed_by="system",
        )
        
        self._store_hash_record(record)
        return record
    
    def _get_hasher(self, algorithm: HashAlgorithm):
        """Get hasher for algorithm."""
        if algorithm == HashAlgorithm.SHA_256:
            return hashlib.sha256()
        elif algorithm == HashAlgorithm.SHA_384:
            return hashlib.sha384()
        elif algorithm == HashAlgorithm.SHA_512:
            return hashlib.sha512()
        elif algorithm == HashAlgorithm.SHA_224:
            return hashlib.sha224()
        elif algorithm == HashAlgorithm.SHA_512_224:
            return hashlib.sha512_224()
        elif algorithm == HashAlgorithm.SHA_512_256:
            return hashlib.sha512_256()
        elif algorithm == HashAlgorithm.SHA3_256:
            return hashlib.sha3_256()
        elif algorithm == HashAlgorithm.SHA3_384:
            return hashlib.sha3_384()
        elif algorithm == HashAlgorithm.SHA3_512:
            return hashlib.sha3_512()
        elif algorithm == HashAlgorithm.BLAKE2B:
            return hashlib.blake2b()
        elif algorithm == HashAlgorithm.BLAKE2S:
            return hashlib.blake2s()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    def _store_hash_record(self, record: HashRecord):
        """Store hash record in database."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("""
                INSERT INTO hash_records (id, algorithm, value, source_path, source_size,
                    computed_at, computed_by, verified, verified_at, verified_by,
                    verification_result, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.id, record.algorithm.value, record.value, record.source_path,
                record.source_size, record.computed_at, record.computed_by,
                int(record.verified), record.verified_at, record.verified_by,
                record.verification_result.value, json.dumps(record.metadata)
            ))
            conn.commit()
        finally:
            conn.close()
    
    def _log_verification(self, record_id: str, record_type: str,
                         verified: bool, verified_by: str, result: str,
                         details: Dict[str, Any]) -> None:
        """Append one row to hash_verification_log.

        Until 2026-11-03 verify_file called this method without this method
        existing — every verification raised AttributeError after already
        computing and comparing the hash. The implementation writes the row
        the schema (hash_verification_log) was created for; a failure to LOG
        must not hide a verification that already happened, so the write is
        guarded: the compare result returned to the caller stays the truth,
        the log row is best-effort and its failure is reported on stderr.
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute(
                "INSERT INTO hash_verification_log "
                "(record_id, record_type, verified, verified_at, verified_by, "
                " result, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record_id, record_type, 1 if verified else 0,
                 datetime.now(timezone.utc).isoformat(), verified_by,
                 result, json.dumps(details)),
            )
            conn.commit()
        except Exception as exc:
            print(f"[forensic_hash] verification log write failed: {exc}",
                  file=sys.stderr)
        finally:
            conn.close()

    def verify_file(self, file_path: Union[str, Path],
                    expected_hash: str,
                    algorithm: HashAlgorithm = HashAlgorithm.SHA_256) -> Tuple[bool, HashRecord]:
        """Verify file against expected hash.

        Before 2026-11-03 this recomputed the digest and compared the file to
        ITSELF, so any well-formed file always verified and the expected_hash
        argument was silently ignored. The comparison is now against
        expected_hash via hmac.compare_digest.
        """
        expected = (expected_hash or "").strip().lower()
        if not expected:
            raise ValueError("expected_hash is required (empty or whitespace-only)")
        
        computed = self.compute_file_hash(file_path, algorithm)
        
        ok = hmac.compare_digest(computed.value.strip().lower(), expected)
        result = HashVerificationResult.MATCH if ok else HashVerificationResult.MISMATCH
        
        # Log verification
        self._log_verification(computed.id, "hash",
                              ok,
                              "system",
                              result.value,
                              {"expected": expected, "computed": computed.value})
        
        return ok, computed
    
    def verify_multiple(self, file_hashes: List[Tuple[str, str, HashAlgorithm]],
                        max_workers: int = 4) -> Dict[str, Tuple[bool, HashRecord]]:
        """Verify multiple files in parallel."""
        results = {}
        
        def verify_one(args):
            path, expected, algo = args
            ok, record = self.verify_file(args[0], args[1], args[2])
            return args[0], (ok, record)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(verify_one, args): args[0] 
                      for args in file_hashes}
            for future in concurrent.futures.as_completed(futures):
                path = futures[future]
                results[path] = future.result()
        
        return results
    
    def compute_hmac(self, data: bytes, key: bytes, key_id: str = "",
                     algorithm: str = "HMAC-SHA-256") -> HMACRecord:
        """Compute HMAC of data."""
        record = HMACRecord.compute(data, key, key_id)
        self._store_hmac_record(record)
        return record
    
    def _store_hmac_record(self, record: HMACRecord):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("""
                INSERT INTO hmac_records (id, algorithm, key_id, hmac_value, data_hash,
                    created_at, created_by, verified, verified_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.id, record.algorithm, record.key_id, record.hmac_value,
                record.data_hash, record.created_at, record.created_by,
                int(record.verified), record.verified_at, json.dumps(record.metadata)
            ))
            conn.commit()
        finally:
            conn.close()
    
    def verify_hmac(self, data: bytes, key: bytes, key_id: str) -> bool:
        """Verify HMAC of data."""
        # Find HMAC record
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            row = conn.execute(
                "SELECT * FROM hmac_records WHERE key_id = ? ORDER BY created_at DESC LIMIT 1",
                (key_id,)
            ).fetchone()
            
            if not row:
                return False
            
            record = HMACRecord(
                id=row[0], algorithm=row[1], key_id=row[2],
                hmac_value=row[3], data_hash=row[4],
                created_at=row[5], created_by=row[6],
                verified=bool(row[7]), verified_at=row[8],
                metadata=json.loads(row[9]) if row[9] else {}
            )
        finally:
            conn.close()
        
        return record.verify(data, key)
    
    def sign_data(self, data: bytes, private_key_pem: str, signer: str) -> DigitalSignatureRecord:
        """Sign data with private key."""
        record = DigitalSignatureRecord.sign(data, private_key_pem, signer)
        self._store_signature_record(record)
        return record
    
    def _store_signature_record(self, record: DigitalSignatureRecord):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("""
                INSERT INTO signature_records (id, algorithm, signature, public_key_pem,
                    signed_by, signed_at, data_hash, verified, verified_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.id, record.algorithm, record.signature, record.public_key_pem,
                record.signed_by, record.signed_at, record.data_hash,
                int(record.verified), record.verified_at, json.dumps(record.metadata)
            ))
            conn.commit()
        finally:
            conn.close()
    
    def verify_signature(self, data: bytes, signature_id: str) -> bool:
        """Verify digital signature."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            row = conn.execute(
                "SELECT * FROM signature_records WHERE id = ?", (signature_id,)
            ).fetchone()
            
            if not row:
                return False
            
            record = DigitalSignatureRecord(
                id=row[0], algorithm=row[1], signature=row[2],
                public_key_pem=row[3], signed_by=row[4], signed_at=row[5],
                data_hash=row[6], verified=bool(row[7]), verified_at=row[8],
                metadata=json.loads(row[9]) if row[9] else {}
            )
        finally:
            conn.close()
        
        return record.verify(data)
    
    def get_file_hash(self, file_path: str, algorithm: HashAlgorithm = HashAlgorithm.SHA_256) -> Optional[str]:
        """Get stored hash for file."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            row = conn.execute(
                "SELECT value FROM hash_records WHERE source_path = ? AND algorithm = ? ORDER BY computed_at DESC LIMIT 1",
                (file_path, algorithm.value)
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    
    def get_verification_history(self, record_id: str, record_type: str) -> List[Dict]:
        """Get verification history for record."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            cursor = conn.execute(
                "SELECT * FROM hash_verification_log WHERE record_id = ? AND record_type = ? ORDER BY created_at DESC",
                (record_id, record_type)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# FILE INTEGRITY MONITOR
# ──────────────────────────────────────────────────────────────────────────────

class FileIntegrityMonitor:
    """Monitor file integrity with baseline hashes."""
    
    def __init__(self, hash_manager: ForensicHashManager,
                 baseline_db: Union[str, Path] = "file_integrity.db"):
        self.hash_manager = hash_manager
        self.baseline_db = Path(baseline_db)
        self._init_baseline_db()
    
    def _init_baseline_db(self):
        self.baseline_db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.baseline_db, timeout=30.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS baseline_hashes (
                file_path TEXT PRIMARY KEY,
                algorithm TEXT NOT NULL,
                hash_value TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()
    
    def create_baseline(self, paths: List[Union[str, Path]],
                        algorithm: HashAlgorithm = HashAlgorithm.SHA_256) -> Dict[str, str]:
        """Create baseline hashes for files."""
        results = {}
        for path in paths:
            record = self.hash_manager.compute_file_hash(path, algorithm)
            self._store_baseline(str(path), algorithm.value, record.value, 
                               os.path.getsize(path), os.path.getmtime(path))
            results[str(path)] = record.value
        return results
    
    def _store_baseline(self, path: str, algorithm: str, hash_value: str, 
                        size: int, mtime: float):
        conn = sqlite3.connect(self.baseline_db, timeout=30.0)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO baseline_hashes 
                (file_path, algorithm, hash_value, file_size, mtime, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (path, algorithm, hash_value, size, mtime))
            conn.commit()
        finally:
            conn.close()
    
    def verify_integrity(self, paths: Optional[List[Union[str, Path]]] = None,
                         algorithm: HashAlgorithm = HashAlgorithm.SHA_256) -> Dict[str, Any]:
        """Verify file integrity against baseline."""
        conn = sqlite3.connect(self.baseline_db, timeout=30.0)
        try:
            if paths:
                placeholders = ",".join("?" * len(paths))
                query = f"SELECT file_path, hash_value, file_size, mtime FROM baseline_hashes WHERE file_path IN ({','.join('?'*len(paths))})"
                cursor = conn.execute(query, [str(p) for p in paths])
            else:
                cursor = conn.execute("SELECT file_path, hash_value, file_size, mtime FROM baseline_hashes")
            
            baseline = {row[0]: {"hash": row[1], "size": row[2], "mtime": row[3]} 
                       for row in cursor.fetchall()}
        finally:
            conn.close()
        
        results = {
            "verified": [],
            "modified": [],
            "missing": [],
            "new": [],
            "errors": []
        }
        
        check_paths = [Path(p) for p in paths] if paths else [Path(p) for p in baseline.keys()]
        
        for path in check_paths:
            path_str = str(path)
            if path_str not in baseline:
                results["new"].append(path_str)
                continue
            
            if not Path(path).exists():
                results["missing"].append(path_str)
                continue
            
            # ALWAYS hash the current file. Until 2026-11-03 this method took a
            # fast path when |mtime - baseline_mtime| <= 1s and reported the
            # file as verified WITHOUT hashing it — content modified within
            # one second of the baseline (or within the same mtime tick) read
            # as INTACT. For a forensic integrity monitor "assume verified"
            # is exactly backwards: an unexamined file is only ever
            # "unknown-hashed", never "verified". mtime is kept as a
            # diagnostic only; the hash decides the verdict.
            current_mtime = Path(path).stat().st_mtime
            record = self.hash_manager.compute_file_hash(path)
            if hmac.compare_digest(record.value, baseline[path_str]["hash"]):
                results["verified"].append(path_str)
            else:
                results["modified"].append({
                    "path": path_str,
                    "expected": baseline[path_str]["hash"],
                    "actual": record.value,
                    "mtime_changed": abs(current_mtime - baseline[path_str]["mtime"]) > 1,
                })
        
        return results


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def create_hash_manager(db_path: Union[str, Path] = "forensic_hashes.db") -> ForensicHashManager:
    """Create forensic hash manager."""
    return ForensicHashManager(db_path)


def create_integrity_monitor(hash_manager: ForensicHashManager,
                            baseline_db: Union[str, Path] = "file_integrity.db") -> FileIntegrityMonitor:
    """Create file integrity monitor."""
    return FileIntegrityMonitor(hash_manager, baseline_db)


def compute_file_hash(file_path: Union[str, Path],
                      algorithm: HashAlgorithm = HashAlgorithm.SHA_256) -> str:
    """Compute hash of file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    hasher = _get_hasher(algorithm)
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def _get_hasher(algorithm: HashAlgorithm):
    """Get hasher for algorithm."""
    if algorithm == HashAlgorithm.SHA_256:
        return hashlib.sha256()
    elif algorithm == HashAlgorithm.SHA_384:
        return hashlib.sha384()
    elif algorithm == HashAlgorithm.SHA_512:
        return hashlib.sha512()
    elif algorithm == HashAlgorithm.SHA_224:
        return hashlib.sha224()
    elif algorithm == HashAlgorithm.SHA_512_224:
        return hashlib.sha512_224()
    elif algorithm == HashAlgorithm.SHA_512_256:
        return hashlib.sha512_256()
    elif algorithm == HashAlgorithm.SHA3_256:
        return hashlib.sha3_256()
    elif algorithm == HashAlgorithm.SHA3_384:
        return hashlib.sha3_384()
    elif algorithm == HashAlgorithm.SHA3_512:
        return hashlib.sha3_512()
    elif algorithm == HashAlgorithm.BLAKE2B:
        return hashlib.blake2b()
    elif algorithm == HashAlgorithm.BLAKE2S:
        return hashlib.blake2s()
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")


def verify_file_hash(file_path: Union[str, Path], expected_hash: str,
                     algorithm: HashAlgorithm = HashAlgorithm.SHA_256) -> bool:
    """Verify file hash against expected value."""
    computed = compute_file_hash(file_path, algorithm)
    return hmac.compare_digest(computed, expected_hash)


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

def selftest() -> Tuple[int, List[str]]:
    """Run self-test of hash verification system."""
    import tempfile
    lines = []
    failures = 0
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create test files
        test_file1 = tmpdir / "test1.txt"
        test_file1.write_text("Test content for hashing")
        
        test_file2 = tmpdir / "test2.bin"
        test_file2.write_bytes(secrets.token_bytes(1024))
        
        # Create hash manager
        hash_mgr = ForensicHashManager(Path(tmpdir) / "test_hashes.db")
        
        # Test single file hash
        record1 = hash_mgr.compute_file_hash(test_file1, HashAlgorithm.SHA_256)
        if record1.value and len(record1.value) == 64:  # SHA-256 = 64 hex chars
            lines.append("PASS: SHA-256 computation")
        else:
            failures += 1
            lines.append("FAIL: SHA-256 computation")
        
        # Test multiple algorithms
        for algo in [HashAlgorithm.SHA_256, HashAlgorithm.SHA_384, HashAlgorithm.SHA_512,
                     HashAlgorithm.SHA3_256, HashAlgorithm.BLAKE2B]:
            record = hash_mgr.compute_file_hash(test_file1, algo)
            if record.value:
                lines.append(f"PASS: {algo.value} computation")
            else:
                failures += 1
                lines.append(f"FAIL: {algo.value} computation")
        
        # Test verification
        ok, record = hash_mgr.verify_file(test_file1, record1.value, HashAlgorithm.SHA_256)
        if ok:
            lines.append("PASS: Hash verification (match)")
        else:
            failures += 1
            lines.append("FAIL: Hash verification (match)")
        
        # Test mismatch detection
        ok, _ = hash_mgr.verify_file(test_file1, "0" * 64, HashAlgorithm.SHA_256)
        if not ok:
            lines.append("PASS: Hash verification (mismatch detected)")
        else:
            failures += 1
            lines.append("FAIL: Hash verification (mismatch not detected)")
        
        # Test HMAC
        key = secrets.token_bytes(32)
        hmac_record = hash_mgr.compute_hmac(b"test data", key, "test-key")
        if hash_mgr.verify_hmac(b"test data", key, "test-key"):
            lines.append("PASS: HMAC verification")
        else:
            failures += 1
            lines.append("FAIL: HMAC verification")
        
        # Test digital signature
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
        
        sig_record = hash_mgr.sign_data(b"test message", private_pem, "test_signer")
        if hash_mgr.verify_signature(b"test message", sig_record.id):
            lines.append("PASS: Digital signature verification")
        else:
            failures += 1
            lines.append("FAIL: Digital signature verification")
        
        # Test file integrity monitor
        monitor = FileIntegrityMonitor(hash_mgr, Path(tempfile.mkdtemp()) / "integrity.db")
        baseline = monitor.create_baseline([test_file1], HashAlgorithm.SHA_256)
        results = monitor.verify_integrity([test_file1], HashAlgorithm.SHA_256)
        
        if str(test_file1) in results["verified"]:
            lines.append("PASS: File integrity monitor (verified)")
        else:
            failures += 1
            lines.append("FAIL: File integrity monitor")
        
        # Test tamper detection
        test_file1.write_text("Modified content")
        results = monitor.verify_integrity([test_file1], HashAlgorithm.SHA_256)
        
        if str(test_file1) in [m["path"] for m in results["modified"]]:
            lines.append("PASS: Tamper detection")
        else:
            failures += 1
            lines.append("FAIL: Tamper detection")
    
    return failures, lines


if __name__ == "__main__":
    import tempfile
    failures, lines = selftest()
    for line in lines:
        print(line)
    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failures)")
    sys.exit(0 if failures == 0 else 1)