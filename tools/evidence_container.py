#!/usr/bin/env python3
# coding: utf-8
"""
evidence_container.py — Tamper-Evident Evidence Containers for Court-Admissible Forensics.

Implements tamper-evident evidence containers with cryptographic sealing,
AES-GCM encryption, and authenticated encryption with associated data (AEAD).
Suitable for court-admissible digital evidence storage.

Standards: NIST SP 800-86, ISO/IEC 27037, FIPS 140-2, FIPS 197 (AES)
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import secrets
import base64
import sys
import uuid
import zlib
import hmac
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, BinaryIO, Union
from enum import Enum
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
import secrets


# ──────────────────────────────────────────────────────────────────────────────
# ENUMS & CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

class ContainerState(Enum):
    """State of evidence container."""
    OPEN = "open"
    SEALED = "sealed"
    LOCKED = "locked"
    COMPROMISED = "compromised"
    EXPIRED = "expired"

class CompressionAlgorithm(Enum):
    """Compression algorithms."""
    NONE = "none"
    ZLIB = "zlib"
    LZ4 = "lz4"
    ZSTD = "zstd"

class EncryptionAlgorithm(Enum):
    """Encryption algorithms."""
    AES_256_GCM = "AES-256-GCM"
    AES_256_CBC_HMAC_SHA256 = "AES-256-CBC-HMAC-SHA256"
    CHACHA20_POLY1305 = "CHACHA20-POLY1305"


# ──────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ContainerMetadata:
    """Metadata for evidence container."""
    container_id: str = field(default_factory=lambda: f"CNT-{uuid.uuid4().hex[:12].upper()}")
    case_number: str = ""
    evidence_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = ""
    description: str = ""
    original_filename: str = ""
    original_size: int = 0
    mime_type: str = ""
    file_hash: str = ""  # SHA-256 of original file
    file_hash_algorithm: str = "SHA-256"
    encryption_algorithm: str = EncryptionAlgorithm.AES_256_GCM.value
    compression: str = CompressionAlgorithm.ZLIB.value
    encryption_key_id: str = ""
    key_derivation: str = "PBKDF2-HMAC-SHA256"
    key_iterations: int = 100000
    salt: str = ""
    nonce: str = ""  # For GCM
    tag: str = ""  # GCM authentication tag
    compression_level: int = 6
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContainerSeal:
    """Tamper-evident seal for container."""
    seal_id: str = field(default_factory=lambda: f"SEAL-{uuid.uuid4().hex[:16].upper()}")
    sealed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sealed_by: str = ""
    seal_hash: str = ""  # HMAC-SHA256 of container state
    hmac_key_id: str = ""
    verified: bool = False
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None


@dataclass
class EvidenceContainer:
    """Tamper-evident evidence container with AEAD encryption."""
    metadata: ContainerMetadata = field(default_factory=ContainerMetadata)
    seal: Optional[ContainerSeal] = None
    encrypted_data: bytes = b""
    state: str = "open"  # open, sealed, locked, compromised
    _master_key: Optional[bytes] = None
    _hmac_key: Optional[bytes] = None
    
    # ──────────────────────────────────────────────────────────────────────────
    # KEY DERIVATION
    # ──────────────────────────────────────────────────────────────────────────
    
    @classmethod
    def derive_keys(cls, password: bytes, salt: bytes, iterations: int = 100000) -> tuple:
        """Derive encryption and HMAC keys from password."""
        # Use HKDF for key derivation
        kdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,  # 32 bytes for AES-256 + 32 bytes for HMAC
            salt=salt,
            info=b"eliza-forensic-container-v1",
        )
        key_material = kdf.derive(password)
        enc_key = key_material[:32]
        hmac_key = key_material[32:]
        return enc_key, hmac_key
    
    @classmethod
    def generate_keys(cls) -> tuple:
        """Generate random encryption and HMAC keys."""
        enc_key = AESGCM.generate_key(bit_length=256)
        hmac_key = secrets.token_bytes(32)
        return enc_key, hmac_key
    
    # ──────────────────────────────────────────────────────────────────────────
    # CONTAINER CREATION
    # ──────────────────────────────────────────────────────────────────────────
    
    @classmethod
    def create(cls, 
               file_path: Union[str, Path, BinaryIO],
               case_number: str,
               evidence_id: str,
               created_by: str,
               password: Optional[bytes] = None,
               passphrase: Optional[str] = None,
               metadata: Optional[Dict[str, Any]] = None) -> "EvidenceContainer":
        """Create new evidence container from file."""
        # Read source file
        if isinstance(file_path, (str, Path)):
            path = Path(file_path)
            with open(path, "rb") as f:
                data = f.read()
            original_filename = path.name
        else:
            data = file_path.read()
            original_filename = "stream.bin"
        
        # Compute file hash
        file_hash = hashlib.sha256(data).hexdigest()
        
        # Compress data
        compressed = zlib.compress(data, level=6)
        
        # Generate or derive keys. A passphrase (str) or password (bytes) is
        # required for a REOPENABLE container; without one the keys are random
        # and unescrowed — key_derivation is then "random" and decrypt() will
        # refuse loudly rather than preserve the container forever unreadable.
        if password is not None or passphrase is not None:
            secret = passphrase.encode() if passphrase is not None else password
            salt = secrets.token_bytes(32)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=64,
                salt=salt,
                iterations=100000,
            )
            key_material = kdf.derive(secret)
            enc_key = key_material[:32]
            hmac_key = key_material[32:]
            derivation = "PBKDF2-HMAC-SHA256"
        else:
            enc_key, hmac_key = EvidenceContainer.generate_keys()
            salt = secrets.token_bytes(32)
            derivation = "random"
        
        # Encrypt with AES-GCM
        aesgcm = AESGCM(enc_key)
        nonce = secrets.token_bytes(12)
        aad = b"eliza-forensic-container-v1"
        ciphertext = aesgcm.encrypt(nonce, compressed, aad)
        tag = ciphertext[-16:]
        ciphertext = ciphertext[:-16]
        
        # Create container
        container = EvidenceContainer()
        
        # Metadata
        container.metadata = ContainerMetadata(
            evidence_id=evidence_id,
            case_number=case_number,
            original_filename=metadata.get("original_filename", "evidence.bin") if metadata else "evidence.bin",
            original_size=len(data),
            mime_type=metadata.get("mime_type", "application/octet-stream") if metadata else "application/octet-stream",
            file_hash=file_hash,
            container_id=secrets.token_hex(16),
            encryption_algorithm="AES-256-GCM",
            compression="zlib",
            key_derivation=derivation,
            salt=salt.hex(),
            key_iterations=100000,
            nonce=nonce.hex(),
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=created_by,
        )
        
        # Store encrypted data
        container.encrypted_data = nonce + ciphertext + tag
        container.state = "open"
        
        # Apply seal
        container.apply_seal(created_by)
        
        return container
    
    # ──────────────────────────────────────────────────────────────────────────
    # SEALING & VERIFICATION
    # ──────────────────────────────────────────────────────────────────────────
    
    def apply_seal(self, sealed_by: str, hmac_key: Optional[bytes] = None) -> None:
        """Apply tamper-evident seal to container."""
        if self.state != "open":
            raise ValueError("Container already sealed")
        
        # Generate timestamp once for consistency
        sealed_at = datetime.now(timezone.utc).isoformat()
        
        # Compute HMAC of container state
        hmac_key = hashlib.sha256(sealed_by.encode()).digest()
        
        # Create canonical representation for sealing. The seal covers a hash
        # of encrypted_data itself — until 2026-11-03 it covered only its
        # LENGTH, so flipping a ciphertext byte undetected (tamper test failed).
        seal_data = {
            "container_id": self.metadata.container_id,
            "evidence_id": self.metadata.evidence_id,
            "file_hash": self.metadata.file_hash,
            "encrypted_size": len(self.encrypted_data),
            "encrypted_data_sha256": hashlib.sha256(self.encrypted_data).hexdigest(),
            "sealed_at": sealed_at,
            "sealed_by": sealed_by,
        }
        canonical = json.dumps(seal_data, sort_keys=True, separators=(",", ":")).encode()
        
        # HMAC-SHA256 as seal
        hmac_obj = hmac.new(hmac_key, canonical, hashlib.sha256)
        seal_hash = hmac_obj.hexdigest()
        
        # Create seal record with the same timestamp
        self.seal = ContainerSeal(
            seal_id=secrets.token_hex(16),
            sealed_at=sealed_at,
            sealed_by=sealed_by,
            seal_hash=seal_hash,
            hmac_key_id=hashlib.sha256(b"container-hmac-key").hexdigest()[:16],
        )
        
        self.state = "sealed"
    
    def verify_seal(self, sealed_by: str = "") -> bool:
        """Verify container seal integrity against the CURRENT container data.

        The seal covers container_id, evidence_id, file_hash, encrypted_size,
        encrypted_data_sha256, sealed_at and sealed_by. The verification key is
        the sealed_by recorded in the seal, as applied; the sealed_by argument
        is accepted for call-site compatibility and recorded as the verifier.
        """
        if not self.seal:
            return False
        
        canonical = json.dumps({
            "container_id": self.metadata.container_id,
            "evidence_id": self.metadata.evidence_id,
            "file_hash": self.metadata.file_hash,
            "encrypted_size": len(self.encrypted_data),
            "encrypted_data_sha256": hashlib.sha256(self.encrypted_data).hexdigest(),
            "sealed_at": self.seal.sealed_at,
            "sealed_by": self.seal.sealed_by,
        }, sort_keys=True, separators=(",", ":")).encode()
        
        hmac_key = hashlib.sha256(self.seal.sealed_by.encode()).digest()
        computed_hash = hmac.new(hmac_key, canonical, hashlib.sha256).hexdigest()
        
        self.seal.verified = hmac.compare_digest(self.seal.seal_hash, computed_hash)
        if self.seal.verified:
            self.seal.verified_at = datetime.now(timezone.utc).isoformat()
            self.seal.verified_by = sealed_by or self.seal.sealed_by
        return self.seal.verified
    
    # ──────────────────────────────────────────────────────────────────────────
    # DECRYPTION & EXTRACTION
    # ──────────────────────────────────────────────────────────────────────────
    
    def decrypt(self, password: Optional[bytes] = None, passphrase: Optional[str] = None) -> bytes:
        """Decrypt and decompress container data."""
        if self.state not in ("sealed", "locked"):
            raise ValueError("Container not sealed")
        
        # Verify seal first
        if not self.verify_seal(self.metadata.created_by):
            raise ValueError("Container seal verification failed - possible tampering")
        
        # Derive keys
        if self.metadata.key_derivation == "PBKDF2-HMAC-SHA256":
            if not password and not passphrase:
                raise ValueError("Password or passphrase required for PBKDF2")
            salt = bytes.fromhex(self.metadata.salt)
            secret = passphrase.encode() if passphrase is not None else (
                password if isinstance(password, (bytes, bytearray)) else password.encode())
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=64,
                salt=salt,
                iterations=self.metadata.key_iterations,
            )
            key_material = kdf.derive(secret)
            enc_key = key_material[:32]
            hmac_key = key_material[32:]
        else:
            # Random keys - would need to be stored/retrieved securely
            raise ValueError("Random key derivation requires key escrow")
        
        # Parse encrypted data
        nonce = bytes.fromhex(self.metadata.nonce)
        # encrypted_data format: nonce (12 bytes) + ciphertext + tag (16 bytes)
        ciphertext = self.encrypted_data[12:-16]  # Skip nonce (12 bytes), remove tag (16 bytes)
        tag = self.encrypted_data[-16:]
        full_ciphertext = ciphertext + tag
        
        # Decrypt
        aesgcm = AESGCM(enc_key)
        aad = b"eliza-forensic-container-v1"
        try:
            compressed = aesgcm.decrypt(nonce, full_ciphertext, aad)
        except Exception as e:
            raise ValueError(f"Decryption failed - possible tampering: {e}")
        
        # Decompress
        try:
            data = zlib.decompress(compressed)
        except Exception as e:
            raise ValueError(f"Decompression failed: {e}")
        
        # Verify file hash (against the DIGEST, not the bytes —
        # hmac.compare_digest raises TypeError on mixed bytes/str)
        computed_hash = hashlib.sha256(data).hexdigest()
        if not hmac.compare_digest(computed_hash, self.metadata.file_hash):
            raise ValueError(f"File hash mismatch - data corrupted or tampered")
        
        return data
    
# ──────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ──────────────────────────────────────────────────────────────────────────
    
    def to_file(self, path: Union[str, Path]) -> None:
        """Write container to file."""
        data = {
            "metadata": asdict(self.metadata),
            "encrypted_data": base64.b64encode(self.encrypted_data).decode(),
        }
        if self.seal:
            data["seal"] = asdict(self.seal)
        Path(path).write_bytes(json.dumps(data, indent=2).encode())
    
    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "EvidenceContainer":
        data = json.loads(Path(path).read_text())
        container = EvidenceContainer()
        container.metadata = ContainerMetadata(**data["metadata"])
        container.encrypted_data = base64.b64decode(data["encrypted_data"])
        container.state = "sealed"
        if data.get("seal"):
            container.seal = ContainerSeal(**data["seal"])
        return container
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceContainer":
        """Create container from dictionary."""
        container = EvidenceContainer()
        container.metadata = ContainerMetadata(**data["metadata"])
        # Handle both base64 string and raw bytes for encrypted_data
        encrypted_data = data["encrypted_data"]
        if isinstance(encrypted_data, str):
            container.encrypted_data = base64.b64decode(encrypted_data)
        else:
            container.encrypted_data = encrypted_data
        container.state = "sealed"
        if data.get("seal"):
            container.seal = ContainerSeal(**data["seal"])
        return container
    
    def export_manifest(self) -> Dict[str, Any]:
        """Export container manifest for chain of custody."""
        return {
            "metadata": asdict(self.metadata),
            "sealed": self.seal is not None,
            "seal_info": asdict(self.seal) if self.seal else None,
            "encrypted_size": len(self.encrypted_data),
            "state": self.state,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# EVIDENCE VAULT - SECURE STORAGE
# ──────────────────────────────────────────────────────────────────────────────

class EvidenceVault:
    """Secure, tamper-evident evidence vault with access control."""
    
    def __init__(self, vault_path: Union[str, Path], master_key: Optional[bytes] = None):
        self.vault_path = Path(vault_path)
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.master_key = master_key or secrets.token_bytes(32)
        self._init_vault()
    
    def _init_vault(self):
        """Initialize vault structure."""
        (self.vault_path / "evidence").mkdir(exist_ok=True)
        (self.vault_path / "logs").mkdir(exist_ok=True)
        (self.vault_path / "keys").mkdir(exist_ok=True)
        
        # Vault manifest
        manifest_path = self.vault_path / "manifest.json"
        if not manifest_path.exists():
            manifest = {
                "vault_id": secrets.token_hex(16),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0",
                "containers": [],
            }
            Path(self.vault_path / "manifest.json").write_text(json.dumps(manifest, indent=2))
    
    def store(self, container: EvidenceContainer, access_level: str = "restricted") -> str:
        """Store sealed container in vault."""
        if container.state != "sealed":
            raise ValueError("Container must be sealed before storage")
        
        # Verify seal
        if not container.verify_seal(container.metadata.created_by):
            raise ValueError("Container seal verification failed")
        
        # Generate storage ID
        storage_id = secrets.token_hex(16)
        container_path = self.vault_path / "evidence" / f"{container.metadata.container_id}.enc"
        
        # Write container file
        container.to_file(container_path)
        
        # Update manifest
        manifest_path = self.vault_path / "manifest.json"
        manifest = json.loads(Path(self.vault_path / "manifest.json").read_text())
        manifest["containers"].append({
            "container_id": container.metadata.container_id,
            "evidence_id": container.metadata.evidence_id,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "access_level": "restricted",
            "size": len(container.encrypted_data),
        })
        Path(self.vault_path / "manifest.json").write_text(json.dumps(manifest, indent=2))
        
        # Audit log
        self._log("STORE", container.metadata.container_id, "stored")
        
        return storage_id
    
    def retrieve(self, container_id: str, requestor: str, authorization: str) -> EvidenceContainer:
        """Retrieve container from vault with authorization check."""
        manifest = json.loads(Path(self.vault_path / "manifest.json").read_text())
        
        # Find container
        container_info = None
        for c in manifest["containers"]:
            if c["container_id"] == container_id:
                container_info = c
                break
        
        if not container_info:
            raise ValueError(f"Container {container_id} not found")
        
        # Check authorization (simplified - would use proper RBAC)
        if authorization != "authorized":
            raise PermissionError("Insufficient authorization")
        
        # Load container
        container_path = self.vault_path / "evidence" / f"{container_id}.enc"
        container = EvidenceContainer.from_file(container_path)
        
        # Verify seal
        if not container.verify_seal(container.metadata.created_by):
            raise ValueError("Container seal verification failed - possible tampering")
        
        # Audit log
        self._log("RETRIEVE", container_id, f"retrieved by {requestor}")
        
        return container
    
    def _log(self, action: str, container_id: str, details: str):
        """Write audit log entry."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "container_id": container_id,
            "details": details,
            "hash": hashlib.sha256(f"{action}{container_id}{details}{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
        }
        log_path = self.vault_path / "logs" / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def create_evidence_container(
    file_path: Union[str, Path],
    case_number: str,
    evidence_id: str,
    created_by: str,
    passphrase: Optional[str] = None,
) -> EvidenceContainer:
    """Create sealed evidence container from file."""
    return EvidenceContainer.create(
        file_path=file_path,
        case_number=case_number,
        evidence_id=evidence_id,
        created_by=created_by,
        passphrase=passphrase,
    )


def open_evidence_vault(vault_path: Union[str, Path]) -> EvidenceVault:
    """Open or create evidence vault."""
    return EvidenceVault(vault_path)


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

def selftest() -> Tuple[int, List[str]]:
    """Run self-test of evidence container system."""
    import tempfile
    lines = []
    failures = 0
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create test file
        test_file = Path(tmpdir) / "test_evidence.txt"
        test_file.write_text("This is test evidence content for forensic container.")
        
        # Create container
        container = EvidenceContainer.create(
            file_path=test_file,
            case_number="CASE-2026-001",
            evidence_id="EVD-TEST-001",
            created_by="analyst_test",
            passphrase="test_passphrase_123",
        )
        
        if container.state == "sealed" and container.seal:
            lines.append("PASS: Container created and sealed")
        else:
            failures += 1
            lines.append("FAIL: Container not sealed properly")
        
        # Verify seal
        if container.verify_seal("analyst_test"):
            lines.append("PASS: Seal verification passed")
        else:
            failures += 1
            lines.append("FAIL: Seal verification failed")
        
        # Test decryption
        try:
            data = container.decrypt(passphrase="test_passphrase_123")
            if b"test evidence" in data:
                lines.append("PASS: Decryption successful")
            else:
                failures += 1
                lines.append(f"FAIL: Decrypted data mismatch: {data[:50]}")
        except Exception as e:
            failures += 1
            lines.append(f"FAIL: Decryption failed: {e}")
        
        # Test tamper detection
        tampered = EvidenceContainer.from_dict(asdict(container))
        tampered.encrypted_data = tampered.encrypted_data[:-1] + b"X"
        if not tampered.verify_seal("test_user"):
            lines.append("PASS: Tamper detection works")
        else:
            failures += 1
            lines.append("FAIL: Tamper detection failed")
        
        # Test vault
        with tempfile.TemporaryDirectory() as vault_dir:
            vault = EvidenceVault(Path(tmpdir) / "vault")
            storage_id = vault.store(container, "restricted")
            if storage_id:
                lines.append("PASS: Vault storage successful")
            else:
                failures += 1
                lines.append("FAIL: Vault storage failed")
            
            retrieved = vault.retrieve(container.metadata.container_id, "analyst", "authorized")
            if retrieved and retrieved.metadata.container_id == container.metadata.container_id:
                lines.append("PASS: Vault retrieval successful")
            else:
                failures += 1
                lines.append("FAIL: Vault retrieval failed")
    
    return failures, lines


if __name__ == "__main__":
    import tempfile
    failures, lines = selftest()
    for line in lines:
        print(line)
    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failures)")
    sys.exit(0 if failures == 0 else 1)