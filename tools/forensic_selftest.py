#!/usr/bin/env python3
# coding: utf-8
"""
forensic_selftest.py — Comprehensive self-test for all forensic components.
"""

import sys
import tempfile
from pathlib import Path

def test_forensic_chain_of_custody():
    """Test forensic chain of custody."""
    print("Testing forensic_chain_of_custody...")
    sys.path.insert(0, str(Path(__file__).parent))
    from forensic_chain_of_custody import selftest
    failures, lines = selftest()
    for line in lines:
        print(f"  {line}")
    return failures

def test_evidence_container():
    """Test evidence container."""
    print("Testing evidence_container...")
    sys.path.insert(0, str(Path(__file__).parent))
    from evidence_container import selftest
    failures, lines = selftest()
    for line in lines:
        print(f"  {line}")
    return failures

def test_forensic_audit():
    """Test forensic audit log."""
    print("Testing forensic_audit...")
    sys.path.insert(0, str(Path(__file__).parent))
    from forensic_audit import selftest
    failures, lines = selftest()
    for line in lines:
        print(f"  {line}")
    return failures

def test_forensic_hash():
    """Test forensic hash verification."""
    print("Testing forensic_hash...")
    sys.path.insert(0, str(Path(__file__).parent))
    from forensic_hash import selftest
    failures, lines = selftest()
    for line in lines:
        print(f"  {line}")
    return failures

def test_forensic_tool_validator():
    """Test forensic tool validator."""
    print("Testing forensic_tool_validator...")
    sys.path.insert(0, str(Path(__file__).parent))
    from forensic_tool_validator import selftest
    failures, lines = selftest()
    for line in lines:
        print(f"  {line}")
    return failures

def test_forensic_report():
    """Test forensic report generator."""
    print("Testing forensic_report...")
    sys.path.insert(0, str(Path(__file__).parent))
    from forensic_report import selftest
    failures, lines = selftest()
    for line in lines:
        print(f"  {line}")
    return failures


def main():
    """Run all forensic self-tests."""
    print("=" * 60)
    print("FORENSIC COMPONENTS COMPREHENSIVE SELF-TEST")
    print("=" * 60)
    
    total_failures = 0
    
    # Test each component
    tests = [
        ("Chain of Custody", test_forensic_chain_of_custody),
        ("Evidence Container", test_evidence_container),
        ("Forensic Audit Log", test_forensic_audit),
        ("Forensic Hash Verification", test_forensic_hash),
        ("Tool Validator", test_forensic_tool_validator),
        ("Forensic Report Generator", test_forensic_report),
    ]
    
    total_failures = 0
    for name, test_func in tests:
        print(f"\n{'='*60}")
        try:
            failures = test_func()
            total_failures += failures
            if failures == 0:
                print(f"[PASS] {name}")
            else:
                print(f"[FAIL] {name}: FAIL ({failures} failures)")
        except Exception as e:
            print(f"[ERROR] {name}: ERROR - {e}")
            total_failures += 1
    
    print(f"\n{'='*60}")
    if total_failures == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"TOTAL FAILURES: {total_failures}")
    
    print("=" * 60)
    return total_failures


if __name__ == "__main__":
    failures = main()
    sys.exit(failures)