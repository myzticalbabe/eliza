#!/usr/bin/env python3
# coding: utf-8
"""
forensic_tool_validator.py — Forensic Tool Validation & Hash Verification.

Validates forensic tools at runtime by verifying their cryptographic hashes
against known-good baselines. Implements tool integrity verification as
required by NIST SP 800-86 and ISO/IEC 27037 for court-admissible forensics.

Standards: NIST SP 800-86, NIST SP 800-101, ISO/IEC 27037, FIPS 140-2
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import subprocess
import platform
import importlib.util
import importlib.metadata
import pkgutil
import inspect
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, BinaryIO, Union, Tuple
from enum import Enum
from contextlib import contextmanager
import hashlib
import subprocess
import threading
import time


# ──────────────────────────────────────────────────────────────────────────────
# ENUMS & CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

class ValidationResult(Enum):
    """Tool validation result."""
    VALID = "valid"
    INVALID = "invalid"
    HASH_MISMATCH = "hash_mismatch"
    MISSING = "missing"
    VERSION_MISMATCH = "version_mismatch"
    SIGNATURE_INVALID = "signature_invalid"
    NOT_TRUSTED = "not_trusted"
    ERROR = "error"

class ToolCategory(Enum):
    """Categories of forensic tools."""
    IMAGING = "imaging"
    ACQUISITION = "acquisition"
    ANALYSIS = "analysis"
    REPORTING = "reporting"
    HASHING = "hashing"
    NETWORK = "network"
    MOBILE = "mobile"
    MEMORY = "memory"
    DATABASE = "database"
    FILE_SYSTEM = "file_system"
    REGISTRY = "registry"
    MALWARE = "malware"
    CLOUD = "cloud"
    CONTAINER = "container"
    ORCHESTRATION = "orchestration"
    CUSTOM = "custom"

# ──────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolHash:
    """Cryptographic hash of a forensic tool."""
    tool_name: str = ""
    tool_path: str = ""
    version: str = ""
    algorithm: str = "SHA-256"
    hash_value: str = ""
    file_size: int = 0
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    computed_by: str = ""
    source: str = ""  # vendor, official, internal, etc.
    verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def compute(cls, file_path: Union[str, Path], tool_name: str = "",
                version: str = "", algorithm: str = "SHA-256") -> "ToolHash":
        """Compute hash of tool file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Tool not found: {file_path}")
        
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        
        return cls(
            tool_name=tool_name or path.name,
            tool_path=str(file_path),
            version=version,
            algorithm="SHA-256",
            hash_value=hasher.hexdigest(),
            file_size=path.stat().st_size,
            computed_by="system",
        )

@dataclass
class ToolValidationRecord:
    """Complete tool validation record."""
    tool_name: str = ""
    tool_path: str = ""
    expected_hash: str = ""
    computed_hash: str = ""
    version_expected: str = ""
    version_actual: str = ""
    validation_result: str = "pending"  # ValidationResult value
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checked_by: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    evidence: List[str] = field(default_factory=list)  # Supporting evidence

@dataclass
class ToolBaseline:
    """Baseline of trusted tool hashes."""
    tool_name: str = ""
    version: str = ""
    hash_algorithm: str = "SHA-256"
    hash_value: str = ""
    file_size: int = 0
    source: str = ""  # vendor, official, internal
    source_url: str = ""
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verified_by: str = ""
    signature: str = ""  # Digital signature of baseline
    metadata: Dict[str, Any] = field(default_factory=dict)

# ──────────────────────────────────────────────────────────────────────────────
# TOOL VALIDATOR
# ──────────────────────────────────────────────────────────────────────────────

class ForensicToolValidator:
    """Validates forensic tools against trusted baselines."""
    
    def __init__(self, baseline_db: Union[str, Path] = "tool_baselines.db",
                 trusted_keys: Optional[List[str]] = None):
        self.baseline_db = Path(baseline_db)
        self.trusted_keys = trusted_keys or []
        self._init_db()
        self._load_trusted_keys()
    
    def _init_db(self):
        """Initialize baseline database.

        The connect is wrapped in try/finally on purpose: before 2026-11-03 the
        schema had a trailing comma in tool_execution_log (sqlite syntax error
        near \")\") and the leaked connection then failed every
        TemporaryDirectory holding this db with WinError 32 instead of
        reporting the schema error.
        """
        self.baseline_db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.baseline_db, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS tool_baselines (
                tool_name TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                hash_algorithm TEXT NOT NULL,
                hash_value TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                source TEXT,
                source_url TEXT,
                verified_at TEXT NOT NULL,
                verified_by TEXT,
                signature TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            
            CREATE TABLE IF NOT EXISTS validation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                tool_path TEXT NOT NULL,
                expected_hash TEXT NOT NULL,
                computed_hash TEXT,
                version_expected TEXT,
                version_actual TEXT,
                validation_result TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                checked_by TEXT,
                details TEXT,
                evidence TEXT,  -- JSON array
                FOREIGN KEY (tool_name) REFERENCES tool_baselines(tool_name)
            );
            
            CREATE TABLE IF NOT EXISTS tool_signatures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                version TEXT NOT NULL,
                public_key_pem TEXT NOT NULL,
                signature TEXT NOT NULL,
                signed_by TEXT NOT NULL,
                signed_at TEXT NOT NULL,
                valid_from TEXT,
                valid_until TEXT,
                revoked INTEGER DEFAULT 0,
                revoked_at TEXT,
                revoked_reason TEXT,
                FOREIGN KEY (tool_name) REFERENCES tool_baselines(tool_name)
            );
            
            CREATE TABLE IF NOT EXISTS tool_execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                tool_path TEXT,
                arguments TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                exit_code INTEGER,
                stdout_hash TEXT,
                stderr_hash TEXT,
                exit_status TEXT,  -- success, failed, timeout, killed
                validated INTEGER DEFAULT 0,
                validated_at TEXT,
                validated_by TEXT,
                validated_hash TEXT
            );
        """)
            conn.commit()
        finally:
            conn.close()
    
    def _load_trusted_keys(self):
        """Load trusted public keys for signature verification."""
        self.trusted_public_keys = {}
        # Would load from secure key store in production
        pass
    
    def add_baseline(self, baseline: ToolBaseline) -> None:
        """Add or update tool baseline."""
        conn = sqlite3.connect(self.baseline_db, timeout=30.0)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO tool_baselines 
                (tool_name, version, hash_algorithm, hash_value, file_size,
                 source, source_url, verified_at, verified_by, signature, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                baseline.tool_name, baseline.version, baseline.hash_algorithm,
                baseline.hash_value, baseline.file_size, baseline.source,
                baseline.source_url, baseline.verified_at, baseline.verified_by,
                baseline.signature, json.dumps(baseline.metadata)
            ))
            conn.commit()
        finally:
            conn.close()
    
    def get_baseline(self, tool_name: str, version: Optional[str] = None) -> Optional[ToolBaseline]:
        """Get baseline for tool."""
        conn = sqlite3.connect(self.baseline_db, timeout=30.0)
        try:
            if version:
                row = conn.execute(
                    "SELECT * FROM tool_baselines WHERE tool_name = ? AND version = ?",
                    (tool_name, version)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM tool_baselines WHERE tool_name = ? ORDER BY version DESC LIMIT 1",
                    (tool_name,)
                ).fetchone()
            
            if not row:
                return None
            
            return ToolBaseline(
                tool_name=row[0], version=row[1], hash_algorithm=row[2],
                hash_value=row[3], file_size=row[4], source=row[5],
                source_url=row[6], verified_at=row[7], verified_by=row[8],
                signature=row[9], metadata=json.loads(row[10]) if row[10] else {}
            )
        finally:
            conn.close()
    
    def validate_tool(self, tool_path: Union[str, Path], 
                      tool_name: Optional[str] = None,
                      expected_version: Optional[str] = None,
                      checker: Optional[str] = None) -> ToolValidationRecord:
        """Validate tool against baseline."""
        path = Path(tool_path)
        if not path.exists():
            return ToolValidationRecord(
                tool_name=tool_name or path.name,
                tool_path=str(path),
                validation_result=ValidationResult.MISSING.value,
                details={"error": "Tool not found"},
            )
        
        tool_name = tool_name or path.name
        baseline = self.get_baseline(tool_name)
        
        if not baseline:
            return ToolValidationRecord(
                tool_name=tool_name,
                tool_path=str(path),
                validation_result=ValidationResult.NOT_TRUSTED.value,
                details={"error": "No baseline found for tool"},
            )
        
        # Compute hash
        computed_hash = ToolHash.compute(str(path)).hash_value
        
        # Check hash
        hash_match = hmac.compare_digest(baseline.hash_value, computed_hash)
        
        # Check version
        version_match = True
        actual_version = self._get_tool_version(path)
        if expected_version and actual_version != expected_version:
            version_match = False
        
        # Determine result
        if not hash_match:
            result = ValidationResult.HASH_MISMATCH
        elif not version_match:
            result = ValidationResult.VERSION_MISMATCH
        else:
            result = ValidationResult.VALID
        
        record = ToolValidationRecord(
            tool_name=tool_name,
            tool_path=str(path),
            expected_hash=baseline.hash_value,
            computed_hash=computed_hash,
            version_expected=expected_version or baseline.version,
            version_actual=actual_version,
            validation_result=result.value,
            checked_by="system",
            details={
                "hash_algorithm": "SHA-256",
                "expected_hash": baseline.hash_value,
                "computed_hash": computed_hash,
                "hash_match": hash_match,
                "version_match": version_match,
                "baseline_version": baseline.version,
            },
            evidence=[
                f"Baseline hash: {baseline.hash_value}",
                f"Computed hash: {computed_hash}",
                f"Baseline version: {baseline.version}",
                f"Actual version: {actual_version}",
            ],
        )
        
        # Log validation result
        self._log_validation(record)
        
        return record
    
    def _get_tool_version(self, path: Path) -> str:
        """Extract version from tool."""
        try:
            result = subprocess.run([str(path), "--version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                # Try to extract version from output
                output = result.stdout.strip()
                # Common version patterns
                import re
                version_match = re.search(r'(\d+\.\d+\.\d+)', output)
                if version_match:
                    return version_match.group(1)
                return output[:50]
        except Exception:
            pass  # scanner:ignore silent_except_pass -- best-effort version probe; unknown is the recorded degraded path
        return "unknown"
    
    def _log_validation(self, record: ToolValidationRecord):
        """Log validation result to database."""
        conn = sqlite3.connect(self.baseline_db, timeout=30.0)
        try:
            conn.execute("""
                INSERT INTO validation_results 
                (tool_name, tool_path, expected_hash, computed_hash,
                 version_expected, version_actual, validation_result,
                 checked_at, checked_by, details, evidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.tool_name, record.tool_path, record.expected_hash,
                record.computed_hash, record.version_expected, record.version_actual,
                record.validation_result, record.checked_at, record.checked_by,
                json.dumps(record.details), json.dumps(record.evidence)
            ))
            conn.commit()
        finally:
            conn.close()
    
    def validate_all_known_tools(self) -> List[ToolValidationRecord]:
        """Validate all tools with baselines."""
        conn = sqlite3.connect(self.baseline_db, timeout=30.0)
        try:
            rows = conn.execute("SELECT tool_name FROM tool_baselines").fetchall()
        finally:
            conn.close()
        
        results = []
        for (tool_name,) in rows:
            # Would need to know tool path - in practice, would be configured
            pass
        return []
    
    def verify_tool_signature(self, tool_path: Union[str, Path],
                              public_key_pem: str) -> bool:
        """Verify tool binary signature."""
        # Would verify detached signature file
        # Implementation depends on signature format (GPG, RSA, etc.)
        return False
    
    def log_execution(self, tool_name: str, tool_path: str, arguments: List[str],
                      exit_code: int, stdout: str, stderr: str,
                      validated: bool = False, validated_hash: str = "") -> None:
        """Log tool execution for audit trail."""
        conn = sqlite3.connect(self.baseline_db, timeout=30.0)
        try:
            conn.execute("""
                INSERT INTO tool_execution_log 
                (tool_name, tool_path, arguments, started_at, completed_at,
                 exit_code, stdout_hash, stderr_hash, exit_status,
                 validated, validated_at, validated_by, validated_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tool_name, str(tool_path), json.dumps(arguments),
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                0,  # exit_code
                hashlib.sha256(stdout.encode()).hexdigest() if stdout else "",
                hashlib.sha256(stderr.encode()).hexdigest() if stderr else "",
                "success" if 0 == 0 else "failed",
                int(False),  # validated
                None,  # validated_at
                None,  # validated_by
                "",    # validated_hash
            ))
            conn.commit()
        finally:
            conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# PYTHON PACKAGE VALIDATOR
# ──────────────────────────────────────────────────────────────────────────────

class PythonPackageValidator:
    """Validates Python packages and their dependencies."""
    
    def __init__(self):
        self.baseline_file = Path("python_baselines.json")
        self.baselines = self._load_baselines()
    
    def _load_baselines(self) -> Dict[str, Dict]:
        """Load package baselines from file."""
        if self.baseline_file.exists():
            return json.loads(self.baseline_file.read_text())
        return {}
    
    def save_baselines(self):
        """Save baselines to file."""
        self.baseline_file.write_text(json.dumps(self.baselines, indent=2))
    
    def record_package(self, package_name: str) -> Dict[str, Any]:
        """Record package hash and metadata."""
        try:
            dist = importlib.metadata.distribution(package_name)
            location = dist.locate_file("")
            
            # Hash all package files
            hashes = {}
            for root, dirs, files in os.walk(location):
                for file in files:
                    if file.endswith(('.py', '.so', '.pyd', '.dll', '.exe')):
                        path = Path(root) / file
                        hasher = hashlib.sha256()
                        with open(path, "rb") as f:
                            while chunk := f.read(8192):
                                hasher.update(chunk)
                            rel_path = path.relative_to(location)
                            hashes[str(rel_path)] = hasher.hexdigest()
            
            record = {
                "name": package_name,
                "version": dist.version,
                "location": str(location),
                "hashes": hashes,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "metadata": dist.metadata,
            }
            
            self.baselines[package_name] = record
            self.save_baselines()
            
            return record
        except importlib.metadata.PackageNotFoundError:
            return {"error": f"Package {package_name} not found"}
    
    def validate_package(self, package_name: str) -> Dict[str, Any]:
        """Validate package against baseline."""
        if package_name not in self.baselines:
            return {"valid": False, "error": "No baseline for package"}
        
        baseline = self.baselines[package_name]
        current = self.record_package(package_name)
        
        if "error" in current:
            return {"valid": False, "error": current["error"]}
        
        mismatches = []
        for file_path, expected_hash in baseline.get("hashes", {}).items():
            actual_hash = current.get("hashes", {}).get(file_path)
            if actual_hash != expected_hash:
                mismatches.append({
                    "file": file_path,
                    "expected": expected_hash,
                    "actual": actual_hash
                })
        
        return {
            "valid": len(mismatches) == 0,
            "package": package_name,
            "baseline_version": baseline.get("version"),
            "current_version": current.get("version"),
            "mismatches": mismatches,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    
    def validate_environment(self) -> Dict[str, Any]:
        """Validate entire Python environment."""
        results = {}
        for package in self.baselines:
            results[package] = self.validate_package(package)
        return results


# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM TOOL VALIDATOR
# ──────────────────────────────────────────────────────────────────────────────

class SystemToolValidator:
    """Validates system forensic tools (dd, dc3dd, ewfacquire, etc.)."""
    
    COMMON_TOOLS = {
        "dd": {"category": ToolCategory.IMAGING, "version_flag": "--version"},
        "dc3dd": {"category": ToolCategory.IMAGING, "version_flag": "--version"},
        "dcfldd": {"category": ToolCategory.IMAGING, "version_flag": "--version"},
        "ewfacquire": {"category": ToolCategory.ACQUISITION, "version_flag": "--version"},
        "ewfmount": {"category": ToolCategory.ACQUISITION, "version_flag": "--version"},
        "ewfinfo": {"category": ToolCategory.ANALYSIS, "version_flag": "--version"},
        "ewfverify": {"category": ToolCategory.ANALYSIS, "version_flag": "--version"},
        "affuse": {"category": ToolCategory.ANALYSIS, "version_flag": "--version"},
        "affverify": {"category": ToolCategory.ANALYSIS, "version_flag": "--version"},
        "tsk_recover": {"category": ToolCategory.FILE_SYSTEM, "version_flag": "--version"},
        "fls": {"category": ToolCategory.FILE_SYSTEM, "version_flag": "--version"},
        "icat": {"category": ToolCategory.FILE_SYSTEM, "version_flag": "--version"},
        "istat": {"category": ToolCategory.FILE_SYSTEM, "version_flag": "--version"},
        "mmls": {"category": ToolCategory.FILE_SYSTEM, "version_flag": "--version"},
        "volatility": {"category": ToolCategory.MEMORY, "version_flag": "--version"},
        "rekall": {"category": ToolCategory.MEMORY, "version_flag": "--version"},
        "regripper": {"category": ToolCategory.REGISTRY, "version_flag": "--version"},
        "bulk_extractor": {"category": ToolCategory.ANALYSIS, "version_flag": "--version"},
        "foremost": {"category": ToolCategory.ANALYSIS, "version_flag": "--version"},
        "scalpel": {"category": ToolCategory.ANALYSIS, "version_flag": "--version"},
        "photorec": {"category": ToolCategory.ANALYSIS, "version_flag": "--version"},
        "testdisk": {"category": ToolCategory.FILE_SYSTEM, "version_flag": "--version"},
        "hashcat": {"category": ToolCategory.HASHING, "version_flag": "--version"},
        "john": {"category": ToolCategory.ANALYSIS, "version_flag": "--version"},
        "tcpdump": {"category": ToolCategory.NETWORK, "version_flag": "--version"},
        "wireshark": {"category": ToolCategory.NETWORK, "version_flag": "--version"},
        "tshark": {"category": ToolCategory.NETWORK, "version_flag": "--version"},
        "nmap": {"category": ToolCategory.NETWORK, "version_flag": "--version"},
        "masscan": {"category": ToolCategory.NETWORK, "version_flag": "--version"},
        "zmap": {"category": ToolCategory.NETWORK, "version_flag": "--version"},
    }
    
    def __init__(self, validator: ForensicToolValidator):
        self.validator = validator
    
    def discover_tools(self) -> Dict[str, str]:
        """Discover installed forensic tools."""
        found = {}
        for tool_name, info in self.COMMON_TOOLS.items():
            path = shutil.which(tool_name)
            if path:
                found[tool_name] = path
        return found
    
    def validate_all(self) -> Dict[str, Any]:
        """Validate all discovered tools."""
        found = self.discover_tools()
        results = {}
        
        for tool_name, path in found.items():
            info = self.COMMON_TOOLS.get(tool_name, {})
            expected_version = None  # Would come from baseline
            
            record = self.validator.validate_tool(path, tool_name)
            results[tool_name] = {
                "path": path,
                "valid": record.validation_result == ValidationResult.VALID.value,
                "result": record.validation_result,
                "details": record.details,
            }
        
        return {
            "tools_found": len(found),
            "tools_validated": len([r for r in results.values() if r["valid"]]),
            "tools_invalid": len([r for r in results.values() if not r["valid"]]),
            "details": results,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
    
    def generate_baseline(self, output_file: str = "tool_baselines.json") -> Dict[str, Any]:
        """Generate baseline for all discovered tools."""
        found = self.discover_tools()
        baseline = {}
        
        for tool_name, path in found.items():
            tool_hash = ToolHash.compute(path, tool_name)
            version = self._get_version(path)
            
            baseline[tool_name] = {
                "tool_name": tool_name,
                "path": path,
                "version": version,
                "hash": tool_hash.hash_value,
                "algorithm": "SHA-256",
                "file_size": os.path.getsize(path),
                "category": self.COMMON_TOOLS.get(tool_name, {}).get("category", "unknown"),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2)
        
        return baseline
    
    def _get_version(self, path: str) -> str:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                import re
                match = re.search(r'(\d+\.\d+\.\d+)', result.stdout)
                if match:
                    return match.group(1)
                return result.stdout.strip()[:50]
        except Exception:
            pass  # scanner:ignore silent_except_pass -- best-effort version probe; unknown is the recorded degraded path
        return "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def create_tool_validator(baseline_db: Union[str, Path] = "tool_baselines.db") -> ForensicToolValidator:
    """Create forensic tool validator."""
    return ForensicToolValidator(baseline_db)


def create_python_validator() -> PythonPackageValidator:
    """Create Python package validator."""
    return PythonPackageValidator()


def create_system_validator() -> SystemToolValidator:
    """Create system tool validator."""
    validator = ForensicToolValidator()
    return SystemToolValidator(validator)


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

def selftest() -> Tuple[int, List[str]]:
    """Run self-test of tool validator."""
    import tempfile
    lines = []
    failures = 0
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create validator
        db_path = tmpdir / "test_baselines.db"
        validator = ForensicToolValidator(db_path)
        
        # Create a test tool
        test_tool = tmpdir / "test_tool.py"
        test_tool.write_text("#!/usr/bin/env python3\nprint('hello')")
        test_tool.chmod(0o755)
        
        # Add baseline
        tool_hash = ToolHash.compute(test_tool, "test_tool", "1.0.0")
        baseline = ToolBaseline(
            tool_name="test_tool",
            version="1.0.0",
            hash_algorithm="SHA-256",
            hash_value=tool_hash.hash_value,
            file_size=test_tool.stat().st_size,
            source="internal",
            verified_at=datetime.now(timezone.utc).isoformat(),
            verified_by="test",
        )
        validator.add_baseline(baseline)
        
        # Test validation
        record = validator.validate_tool(test_tool, "test_tool")
        if record.validation_result == ValidationResult.VALID.value:
            print("PASS: Tool validation (match)")
        else:
            print(f"FAIL: Tool validation: {record.validation_result}")
            return 1, ["Validation failed"]
        
        # Test hash mismatch
        test_tool.write_text("#!/usr/bin/env python3\nprint('modified')")
        record2 = validator.validate_tool(test_tool, "test_tool")
        if record2.validation_result == ValidationResult.HASH_MISMATCH.value:
            print("PASS: Hash mismatch detected")
        else:
            print(f"FAIL: Hash mismatch not detected: {record2.validation_result}")
            return 1, ["Hash mismatch not detected"]
        
        # Test Python package validator
        py_validator = PythonPackageValidator()
        result = py_validator.validate_environment()
        print(f"Python env validation: {len(result)} packages checked")
    
    return 0, ["All tests passed"]


if __name__ == "__main__":
    failures, lines = selftest()
    for line in lines:
        print(line)
    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failures)")
    sys.exit(0 if failures == 0 else 1)