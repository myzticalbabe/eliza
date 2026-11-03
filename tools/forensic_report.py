#!/usr/bin/env python3
# coding: utf-8
"""
forensic_report.py — Court-Ready Forensic Report Generator.

Generates forensic examination reports suitable for court submission,
compliant with NIST SP 800-86, ISO/IEC 27037, and legal evidence standards.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import base64
import uuid
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
from enum import Enum
from typing import Any, Dict, List, Optional
# python-docx is required only for .docx export. Before 2026-11-03 these
# imports were unconditional, so importing this module ANYWHERE failed with
# ModuleNotFoundError when python-docx was missing and the whole selftest
# battery counted forensic_report as dead. They are now guarded; the docx
# writer raises a clear error only when actually invoked without the package.
try:
    from docx import Document
    from docx.shared import Inches, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    HAVE_DOCX = True
except ImportError:  # pragma: no cover - exercised in the battery without the package
    Document = None  # type: ignore[assignment]
    HAVE_DOCX = False
import zipfile
import tempfile


# ──────────────────────────────────────────────────────────────────────────────
# ENUMS & CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

class ReportFormat(Enum):
    """Report output formats."""
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"
    JSON = "json"
    MARKDOWN = "md"

class ReportClassification(Enum):
    """Report classification levels."""
    UNCLASSIFIED = "UNCLASSIFIED"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"
    TOP_SECRET = "TOP SECRET"
    LAW_ENFORCEMENT_SENSITIVE = "LAW ENFORCEMENT SENSITIVE"
    ATTORNEY_CLIENT_PRIVILEGED = "ATTORNEY-CLIENT PRIVILEGED"
    WORK_PRODUCT = "WORK PRODUCT"

class FindingSeverity(Enum):
    """Finding severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"

# ──────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CaseInfo:
    """Case identification information."""
    case_number: str = ""
    case_name: str = ""
    court: str = ""
    jurisdiction: str = ""
    lead_investigator: str = ""
    assigned_date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    classification: ReportClassification = ReportClassification.CONFIDENTIAL
    keywords: List[str] = field(default_factory=list)

@dataclass
class ExaminerInfo:
    """Forensic examiner information."""
    name: str = ""
    title: str = ""
    organization: str = ""
    badge_number: str = ""
    email: str = ""
    phone: str = ""
    certifications: List[str] = field(default_factory=list)
    qualifications: str = ""
    cv_path: str = ""

@dataclass
class EvidenceSummary:
    """Summary of evidence item."""
    evidence_id: str = ""
    description: str = ""
    evidence_type: str = ""
    collected_at: str = ""
    collected_by: str = ""
    hash_algorithm: str = "SHA-256"
    hash_value: str = ""
    size_bytes: int = 0
    location_collected: str = ""
    chain_of_custody_verified: bool = False
    seal_intact: bool = True
    legal_holds: List[str] = field(default_factory=list)

@dataclass
class ToolUsed:
    """Forensic tool used in examination."""
    name: str = ""
    version: str = ""
    vendor: str = ""
    hash_verified: bool = True
    hash_value: str = ""
    purpose: str = ""
    output_location: str = ""

@dataclass
class Finding:
    """Forensic finding."""
    id: str = field(default_factory=lambda: f"FND-{uuid.uuid4().hex[:8].upper()}")
    title: str = ""
    description: str = ""
    severity: FindingSeverity = FindingSeverity.INFORMATIONAL
    category: str = ""
    evidence_references: List[str] = field(default_factory=list)
    analysis_details: str = ""
    conclusion: str = ""
    confidence: str = "HIGH"  # HIGH, MEDIUM, LOW
    references: List[str] = field(default_factory=list)
    mitre_attack: List[str] = field(default_factory=list)  # MITRE ATT&CK mappings
    cvss_score: Optional[float] = None

@dataclass
class ExaminationTimeline:
    """Timeline of examination activities."""
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_event(self, timestamp: str, activity: str, examiner: str, 
                  details: str = "", evidence_id: str = ""):
        self.events.append({
            "timestamp": timestamp,
            "activity": activity,
            "examiner": examiner,
            "details": details,
            "evidence_id": evidence_id,
        })


# ──────────────────────────────────────────────────────────────────────────────
# FORENSIC REPORT
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ForensicReport:
    """Complete forensic examination report."""
    # Identification
    report_id: str = field(default_factory=lambda: f"FR-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}")
    version: str = "1.0"
    status: str = "DRAFT"  # DRAFT, FINAL, AMENDED, SUPERSEDED
    classification: ReportClassification = ReportClassification.CONFIDENTIAL
    
    # Case Information
    case_info: CaseInfo = field(default_factory=CaseInfo)
    
    # Examiner Information
    examiner: ExaminerInfo = field(default_factory=ExaminerInfo)
    
    # Evidence
    evidence_items: List[EvidenceSummary] = field(default_factory=list)
    
    # Tools Used
    tools_used: List[ToolUsed] = field(default_factory=list)
    
    # Findings
    findings: List[Finding] = field(default_factory=list)
    
    # Timeline
    timeline: ExaminationTimeline = field(default_factory=ExaminationTimeline)
    
    # Methodology
    methodology: str = ""
    scope: str = ""
    limitations: str = ""
    
    # Conclusions
    executive_summary: str = ""
    conclusions: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    # Technical Details
    environment: Dict[str, str] = field(default_factory=dict)
    tools_validated: bool = True
    hash_algorithms: List[str] = field(default_factory=lambda: ["SHA-256"])
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finalized_at: Optional[str] = None
    finalized_by: str = ""
    
    # Appendices
    appendices: Dict[str, str] = field(default_factory=dict)
    
    # ──────────────────────────────────────────────────────────────────────────
    # REPORT GENERATION
    # ──────────────────────────────────────────────────────────────────────────
    
    def generate_docx(self, output_path: Union[str, Path]) -> Path:
        """Generate DOCX report."""
        if not HAVE_DOCX:
            raise RuntimeError(
                "python-docx is not installed; `pip install python-docx` is "
                "required for DOCX export (JSON/markdown export works without it)"
            )
        doc = Document()
        
        # Set default font
        style = doc.styles['Normal']
        font = style.font
        font.name = 'Calibri'
        font.size = Pt(11)
        
        # ─── Cover Page ───
        self._add_cover_page(doc)
        doc.add_page_break()
        
        # ─── Table of Contents ───
        self._add_toc(doc)
        doc.add_page_break()
        
        # ─── Executive Summary ───
        self._add_executive_summary(doc)
        doc.add_page_break()
        
        # ─── Case Information ───
        self._add_case_info(doc)
        doc.add_page_break()
        
        # ─── Examiner Information ───
        self._add_examiner_info(doc)
        doc.add_page_break()
        
        # ─── Scope & Methodology ───
        self._add_methodology(doc)
        doc.add_page_break()
        
        # ─── Evidence Summary ───
        self._add_evidence_summary(doc)
        doc.add_page_break()
        
        # ─── Tools Used ───
        self._add_tools_used(doc)
        doc.add_page_break()
        
        # ─── Findings ───
        self._add_findings(doc)
        doc.add_page_break()
        
        # ─── Examination Timeline ───
        self._add_timeline(doc)
        doc.add_page_break()
        
        # ─── Conclusions & Recommendations ───
        self._add_conclusions(doc)
        doc.add_page_break()
        
        # ─── Appendices ───
        self._add_appendices(doc)
        
        # Save
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path)
        return output_path
    
    def _add_cover_page(self, doc: Document):
        """Add cover page."""
        # Classification banner
        for _ in range(3):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(self.classification.value)
            run.bold = True
            run.font.size = Pt(14)
            run.font.color.rgb = RGBColor(255, 0, 0)
            p.paragraph_format.space_after = Pt(6)
        
        # Title
        doc.add_paragraph("")
        title = doc.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title.add_run("FORENSIC EXAMINATION REPORT")
        run.bold = True
        run.font.size = Pt(28)
        run.font.color.rgb = RGBColor(0, 0, 0)
        
        doc.add_paragraph("")
        
        # Case info
        case_table = doc.add_table(rows=6, cols=2)
        case_table.style = 'Table Grid'
        case_data = [
            ("Case Number:", self.case_info.case_number),
            ("Case Name:", self.case_info.case_name),
            ("Court:", self.case_info.court),
            ("Jurisdiction:", self.case_info.jurisdiction),
            ("Lead Investigator:", self.case_info.lead_investigator),
            ("Classification:", self.classification.value),
        ]
        for i, (label, value) in enumerate(case_data):
            row = case_table.rows[i]
            row.cells[0].text = label
            row.cells[1].text = value
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(11)
                    if cell == row.cells[0]:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                run.bold = True
        
        doc.add_paragraph("")
        
        # Report info
        report_table = doc.add_table(rows=4, cols=2)
        report_table.style = 'Table Grid'
        report_data = [
            ("Report ID:", self.report_id),
            ("Version:", self.version),
            ("Status:", self.status),
            ("Date:", self.created_at[:10]),
        ]
        for i, (label, value) in enumerate(report_data):
            row = report_table.rows[i]
            row.cells[0].text = label
            row.cells[1].text = value
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(11)
                    if cell == row.cells[0]:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                run.bold = True
        
        doc.add_paragraph("")
        
        # Examiner info
        exam_table = doc.add_table(rows=3, cols=2)
        exam_table.style = 'Table Grid'
        exam_data = [
            ("Examiner:", self.examiner.name),
            ("Title:", self.examiner.title),
            ("Organization:", self.examiner.organization),
        ]
        for i, (label, value) in enumerate(exam_data):
            row = exam_table.rows[i]
            row.cells[0].text = label
            row.cells[1].text = value
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(11)
                    if cell == row.cells[0]:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                run.bold = True
        
        # Classification footer
        doc.add_paragraph("")
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(f"CLASSIFICATION: {self.classification.value}")
        run.bold = True
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(255, 0, 0)
    
    def _add_toc(self, doc: Document):
        """Add table of contents placeholder."""
        doc.add_heading('TABLE OF CONTENTS', level=1)
        p = doc.add_paragraph()
        p.add_run("Table of Contents will be generated by Word. Right-click and select 'Update Field'.").italic = True
    
    def _add_executive_summary(self, doc: Document):
        """Add executive summary."""
        doc.add_heading('EXECUTIVE SUMMARY', level=1)
        
        if self.executive_summary:
            doc.add_paragraph(self.executive_summary)
        else:
            p = doc.add_paragraph()
            p.add_run("[Executive summary to be completed by examiner]").italic = True
        
        # Key findings summary
        if self.findings:
            doc.add_heading('Key Findings', level=2)
            for finding in self.findings:
                p = doc.add_paragraph(style='List Bullet')
                severity_color = {
                    FindingSeverity.CRITICAL: RGBColor(255, 0, 0),
                    FindingSeverity.HIGH: RGBColor(255, 165, 0),
                    FindingSeverity.MEDIUM: RGBColor(255, 255, 0),
                    FindingSeverity.LOW: RGBColor(0, 128, 0),
                    FindingSeverity.INFORMATIONAL: RGBColor(0, 0, 255),
                }.get(finding.severity, RGBColor(0, 0, 0))
                
                run = p.add_run(f"[{finding.severity.value}] {finding.title}: ")
                run.bold = True
                run.font.color.rgb = severity_color
                p.add_run(finding.conclusion[:200] + ("..." if len(finding.conclusion) > 200 else ""))
    
    def _add_case_info(self, doc: Document):
        """Add case information section."""
        doc.add_heading('CASE INFORMATION', level=1)
        
        table = doc.add_table(rows=8, cols=2)
        table.style = 'Table Grid'
        data = [
            ("Case Number:", self.case_info.case_number),
            ("Case Name:", self.case_info.case_name),
            ("Court:", self.case_info.court),
            ("Jurisdiction:", self.case_info.jurisdiction),
            ("Lead Investigator:", self.case_info.lead_investigator),
            ("Assigned Date:", self.case_info.assigned_date[:10]),
            ("Classification:", self.classification.value),
            ("Keywords:", ", ".join(self.case_info.keywords)),
        ]
        for i, (label, value) in enumerate(data):
            row = table.rows[i]
            row.cells[0].text = label
            row.cells[1].text = value
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(11)
                    if cell == row.cells[0]:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                run.bold = True
    
    def _add_examiner_info(self, doc: Document):
        """Add examiner information section."""
        doc.add_heading('EXAMINER INFORMATION', level=1)
        
        table = doc.add_table(rows=7, cols=2)
        table.style = 'Table Grid'
        data = [
            ("Name:", self.examiner.name),
            ("Title:", self.examiner.title),
            ("Organization:", self.examiner.organization),
            ("Badge Number:", self.examiner.badge_number),
            ("Email:", self.examiner.email),
            ("Phone:", self.examiner.phone),
            ("Certifications:", ", ".join(self.examiner.certifications)),
        ]
        for i, (label, value) in enumerate(data):
            row = table.rows[i]
            row.cells[0].text = label
            row.cells[1].text = value
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(11)
                    if cell == row.cells[0]:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                run.bold = True
        
        if self.examiner.qualifications:
            doc.add_paragraph("")
            doc.add_heading('Qualifications', level=2)
            doc.add_paragraph(self.examiner.qualifications)
    
    def _add_methodology(self, doc: Document):
        """Add methodology section."""
        doc.add_heading('METHODOLOGY', level=1)
        
        doc.add_heading('Scope', level=2)
        if self.scope:
            doc.add_paragraph(self.scope)
        else:
            p = doc.add_paragraph()
            p.add_run("[Scope to be defined by examiner]").italic = True
        
        doc.add_heading('Methodology', level=2)
        if self.methodology:
            doc.add_paragraph(self.methodology)
        else:
            p = doc.add_paragraph()
            p.add_run("[Methodology to be documented by examiner]").italic = True
        
        doc.add_heading('Limitations', level=2)
        if self.limitations:
            doc.add_paragraph(self.limitations)
        else:
            p = doc.add_paragraph()
            p.add_run("[Limitations to be documented by examiner]").italic = True
        
        doc.add_heading('Environment', level=2)
        if self.environment:
            table = doc.add_table(rows=len(self.environment), cols=2)
            table.style = 'Table Grid'
            for i, (key, value) in enumerate(self.environment.items()):
                row = table.rows[i]
                row.cells[0].text = key
                row.cells[1].text = value
        else:
            p = doc.add_paragraph()
            p.add_run("[Environment details to be documented]").italic = True
        
        if self.tools_validated:
            doc.add_paragraph("")
            p = doc.add_paragraph("All forensic tools were validated against known baselines prior to use.")
            p.runs[0].bold = True
        
        doc.add_heading('Hash Algorithms Used', level=2)
        for algo in self.hash_algorithms:
            doc.add_paragraph(algo, style='List Bullet')
    
    def _add_evidence_summary(self, doc: Document):
        """Add evidence summary section."""
        doc.add_heading('EVIDENCE SUMMARY', level=1)
        
        if not self.evidence_items:
            doc.add_paragraph("No evidence items documented.")
            return
        
        for evidence in self.evidence_items:
            doc.add_heading(f"Evidence: {evidence.evidence_id}", level=2)
            
            table = doc.add_table(rows=10, cols=2)
            table.style = 'Table Grid'
            data = [
                ("Evidence ID:", evidence.evidence_id),
                ("Description:", evidence.description),
                ("Type:", evidence.evidence_type),
                ("Collected At:", evidence.collected_at[:19].replace('T', ' ')),
                ("Collected By:", evidence.collected_by),
                ("Location Collected:", evidence.location_collected),
                ("Hash Algorithm:", evidence.hash_algorithm),
                ("Hash Value:", evidence.hash_value[:32] + "..." if len(evidence.hash_value) > 32 else evidence.hash_value),
                ("Size (bytes):", str(evidence.size_bytes)),
                ("Chain of Custody Verified:", "Yes" if evidence.chain_of_custody_verified else "No"),
            ]
            for i, (label, value) in enumerate(data):
                row = table.rows[i]
                row.cells[0].text = label
                row.cells[1].text = str(value)
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(10)
                        if cell == row.cells[0]:
                            for paragraph in cell.paragraphs:
                                for run in paragraph.runs:
                                    run.bold = True
            
            # Seal status
            doc.add_paragraph("")
            p = doc.add_paragraph()
            seal_status = "INTACT" if evidence.seal_intact else "BROKEN"
            run = p.add_run(f"Seal Status: {seal_status}")
            run.bold = True
            run.font.color.rgb = RGBColor(0, 128, 0) if evidence.seal_intact else RGBColor(255, 0, 0)
            
            if evidence.legal_holds:
                doc.add_paragraph("")
                p = doc.add_paragraph("Legal Holds: ")
                p.add_run(", ".join(evidence.legal_holds))
        
        # Summary table
        doc.add_heading('Evidence Inventory', level=2)
        table = doc.add_table(rows=len(self.evidence_items) + 1, cols=6)
        table.style = 'Table Grid'
        headers = ["Evidence ID", "Description", "Type", "Hash (SHA-256)", "Size (bytes)", "Seal"]
        for i, header in enumerate(headers):
            table.rows[0].cells[i].text = header
            for paragraph in table.rows[0].cells[i].paragraphs:
                for run in paragraph.runs:
                    run.bold = True
                    run.font.size = Pt(10)
        
        for i, evidence in enumerate(self.evidence_items):
            row = table.rows[i + 1]
            row.cells[0].text = evidence.evidence_id
            row.cells[1].text = evidence.description[:40]
            row.cells[2].text = evidence.evidence_type
            row.cells[3].text = evidence.hash_value[:16] + "..."
            row.cells[4].text = str(evidence.size_bytes)
            row.cells[5].text = "✓" if evidence.seal_intact else "✗"
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(9)
    
    def _add_tools_used(self, doc: Document):
        """Add tools used section."""
        doc.add_heading('TOOLS USED', level=1)
        
        if not self.tools_used:
            doc.add_paragraph("No tools documented.")
            return
        
        table = doc.add_table(rows=len(self.tools_used) + 1, cols=6)
        table.style = 'Table Grid'
        headers = ["Tool", "Version", "Vendor", "Hash Verified", "Hash (SHA-256)", "Purpose"]
        for i, header in enumerate(headers):
            table.rows[0].cells[i].text = header
            for paragraph in table.rows[0].cells[i].paragraphs:
                for run in paragraph.runs:
                    run.bold = True
                    run.font.size = Pt(10)
        
        for i, tool in enumerate(self.tools_used):
            row = table.rows[i + 1]
            row.cells[0].text = tool.name
            row.cells[1].text = tool.version
            row.cells[2].text = tool.vendor
            row.cells[3].text = "✓" if tool.hash_verified else "✗"
            row.cells[4].text = tool.hash_value[:16] + "..."
            row.cells[5].text = tool.purpose
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(9)
    
    def _add_findings(self, doc: Document):
        """Add findings section."""
        doc.add_heading('FINDINGS', level=1)
        
        if not self.findings:
            doc.add_paragraph("No findings documented.")
            return
        
        # Group by severity
        severity_order = [
            FindingSeverity.CRITICAL,
            FindingSeverity.HIGH,
            FindingSeverity.MEDIUM,
            FindingSeverity.LOW,
            FindingSeverity.INFORMATIONAL,
        ]
        
        for severity in severity_order:
            severity_findings = [f for f in self.findings if f.severity == severity]
            if not severity_findings:
                continue
            
            doc.add_heading(f'{severity.value} FINDINGS', level=2)
            
            for finding in severity_findings:
                doc.add_heading(finding.title, level=3)
                
                # Severity badge
                p = doc.add_paragraph()
                run = p.add_run(f"Severity: {finding.severity.value}")
                run.bold = True
                severity_colors = {
                    FindingSeverity.CRITICAL: RGBColor(255, 0, 0),
                    FindingSeverity.HIGH: RGBColor(255, 165, 0),
                    FindingSeverity.MEDIUM: RGBColor(255, 255, 0),
                    FindingSeverity.LOW: RGBColor(0, 128, 0),
                    FindingSeverity.INFORMATIONAL: RGBColor(0, 0, 255),
                }
                run.font.color.rgb = severity_colors.get(finding.severity, RGBColor(0, 0, 0))
                
                doc.add_paragraph(f"Category: {finding.category}")
                doc.add_paragraph(f"Confidence: {finding.confidence}")
                
                doc.add_heading('Description', level=4)
                doc.add_paragraph(finding.description)
                
                doc.add_heading('Analysis Details', level=4)
                doc.add_paragraph(finding.analysis_details)
                
                doc.add_heading('Conclusion', level=4)
                doc.add_paragraph(finding.conclusion)
                
                if finding.evidence_references:
                    doc.add_heading('Evidence References', level=4)
                    for ref in finding.evidence_references:
                        doc.add_paragraph(ref, style='List Bullet')
                
                if finding.references:
                    doc.add_heading('References', level=4)
                    for ref in finding.references:
                        doc.add_paragraph(ref, style='List Bullet')
                
                if finding.mitre_attack:
                    doc.add_heading('MITRE ATT&CK Mapping', level=4)
                    for technique in finding.mitre_attack:
                        doc.add_paragraph(technique, style='List Bullet')
                
                if finding.cvss_score:
                    p = doc.add_paragraph()
                    run = p.add_run(f"CVSS Score: {finding.cvss_score}")
                    run.bold = True
                
                doc.add_paragraph("")
    
    def _add_timeline(self, doc: Document):
        """Add examination timeline."""
        doc.add_heading('EXAMINATION TIMELINE', level=1)
        
        if not self.timeline.events:
            doc.add_paragraph("No timeline events recorded.")
            return
        
        table = doc.add_table(rows=len(self.timeline.events) + 1, cols=5)
        table.style = 'Table Grid'
        headers = ["Timestamp", "Activity", "Examiner", "Evidence", "Details"]
        for i, header in enumerate(headers):
            table.rows[0].cells[i].text = header
            for paragraph in table.rows[0].cells[i].paragraphs:
                for run in paragraph.runs:
                    run.bold = True
                    run.font.size = Pt(10)
        
        for i, event in enumerate(self.timeline.events):
            row = table.rows[i + 1]
            row.cells[0].text = event.get("timestamp", "")[:19].replace('T', ' ')
            row.cells[1].text = event.get("activity", "")
            row.cells[2].text = event.get("examiner", "")
            row.cells[3].text = event.get("evidence_id", "")
            row.cells[4].text = event.get("details", "")[:100]
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(9)
    
    def _add_conclusions(self, doc: Document):
        """Add conclusions and recommendations."""
        doc.add_heading('CONCLUSIONS', level=1)
        
        if self.conclusions:
            for i, conclusion in enumerate(self.conclusions, 1):
                doc.add_paragraph(f"{i}. {conclusion}")
        else:
            p = doc.add_paragraph()
            p.add_run("[Conclusions to be completed by examiner]").italic = True
        
        doc.add_heading('RECOMMENDATIONS', level=1)
        
        if self.recommendations:
            for i, rec in enumerate(self.recommendations, 1):
                doc.add_paragraph(f"{i}. {rec}")
        else:
            p = doc.add_paragraph()
            p.add_run("[Recommendations to be completed by examiner]").italic = True
    
    def _add_appendices(self, doc: Document):
        """Add appendices."""
        if not self.appendices:
            return
        
        doc.add_heading('APPENDICES', level=1)
        
        for title, content in self.appendices.items():
            doc.add_heading(f'Appendix: {title}', level=2)
            doc.add_paragraph(content)
    
    def generate_json(self, output_path: Union[str, Path]) -> Path:
        """Generate JSON report."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = asdict(self)
        # Convert enums to strings
        def convert(obj):
            if isinstance(obj, Enum):
                return obj.value
            elif isinstance(obj, (datetime,)):
                return obj.isoformat()
            elif isinstance(obj, (list, tuple)):
                return [convert(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            elif hasattr(obj, '__dataclass_fields__'):
                return convert(asdict(obj))
            return obj
        
        converted = convert(data)
        
        output_path = Path(output_path)
        output_path.write_text(json.dumps(converted, indent=2, default=str))
        return output_path
    
    def generate_html(self, output_path: Union[str, Path]) -> Path:
        """Generate HTML report."""
        # Would use a template engine like Jinja2
        # Placeholder for now
        output_path = Path(output_path)
        output_path.write_text("<html><body><h1>Forensic Report</h1><p>HTML generation not yet implemented.</p></body></html>")
        return output_path
    
    def generate_pdf(self, output_path: Union[str, Path]) -> Path:
        """Generate PDF report via docx2pdf."""
        docx_path = Path(str(output_path).replace('.pdf', '.docx'))
        self.generate_docx(docx_path)
        # Would use docx2pdf or libreoffice to convert
        # For now, return docx path
        return docx_path
    
    def finalize(self, finalized_by: str = "") -> None:
        """Finalize report."""
        self.status = "FINAL"
        self.finalized_at = datetime.now(timezone.utc).isoformat()
        self.finalized_by = finalized_by
        self.updated_at = datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# REPORT BUILDER (FLUENT API)
# ──────────────────────────────────────────────────────────────────────────────

class ForensicReportBuilder:
    """Fluent builder for forensic reports."""
    
    def __init__(self):
        self.report = ForensicReport()
    
    def case(self, case_number: str, case_name: str = "", 
             court: str = "", jurisdiction: str = "",
             lead_investigator: str = "") -> "ForensicReportBuilder":
        self.report.case_info = CaseInfo(
            case_number=case_number, case_name=case_name,
            court=court, jurisdiction=jurisdiction,
            lead_investigator=lead_investigator
        )
        return self
    
    def examiner(self, name: str, title: str = "", organization: str = "",
                 badge_number: str = "", email: str = "", phone: str = "",
                 certifications: List[str] = None, qualifications: str = "") -> "ForensicReportBuilder":
        self.report.examiner = ExaminerInfo(
            name=name, title=title, organization=organization,
            badge_number=badge_number, email=email, phone=phone,
            certifications=certifications or [], qualifications=qualifications
        )
        return self
    
    def evidence(self, evidence_id: str, description: str, evidence_type: str,
                 hash_value: str, hash_algorithm: str = "SHA-256",
                 size_bytes: int = 0, collected_at: str = "",
                 collected_by: str = "", location: str = "",
                 chain_verified: bool = False, seal_intact: bool = True,
                 legal_holds: List[str] = None) -> "ForensicReportBuilder":
        self.report.evidence_items.append(EvidenceSummary(
            evidence_id=evidence_id, description=description, evidence_type=evidence_type,
            hash_value=hash_value, hash_algorithm=hash_algorithm,
            size_bytes=size_bytes, collected_at=collected_at or datetime.now(timezone.utc).isoformat(),
            collected_by=collected_by, location_collected=location,
            chain_of_custody_verified=chain_verified, seal_intact=seal_intact,
            legal_holds=legal_holds or []
        ))
        return self
    
    def tool(self, name: str, version: str, vendor: str = "",
             hash_verified: bool = True, hash_value: str = "",
             purpose: str = "") -> "ForensicReportBuilder":
        self.report.tools_used.append(ToolUsed(
            name=name, version=version, vendor=vendor,
            hash_verified=hash_verified, hash_value=hash_value, purpose=purpose
        ))
        return self
    
    def finding(self, title: str, description: str, severity: FindingSeverity,
                category: str = "", evidence_refs: List[str] = None,
                analysis: str = "", conclusion: str = "",
                confidence: str = "HIGH", references: List[str] = None,
                mitre: List[str] = None, cvss: float = None) -> "ForensicReportBuilder":
        self.report.findings.append(Finding(
            title=title, description=description, severity=severity,
            category=category, evidence_references=evidence_refs or [],
            analysis_details=analysis, conclusion=conclusion,
            confidence=confidence, references=references or [],
            mitre_attack=mitre or [], cvss_score=cvss
        ))
        return self
    
    def timeline_event(self, timestamp: str, activity: str, examiner: str,
                       details: str = "", evidence_id: str = "") -> "ForensicReportBuilder":
        self.report.timeline.add_event(timestamp, activity, examiner, details, evidence_id)
        return self
    
    def methodology(self, scope: str, methodology: str, limitations: str = "",
                    environment: Dict[str, str] = None,
                    hash_algorithms: List[str] = None) -> "ForensicReportBuilder":
        self.report.scope = scope
        self.report.methodology = methodology
        self.report.limitations = limitations
        self.report.environment = environment or {}
        self.report.hash_algorithms = hash_algorithms or ["SHA-256"]
        return self
    
    def executive_summary(self, summary: str) -> "ForensicReportBuilder":
        self.report.executive_summary = summary
        return self
    
    def conclusion(self, conclusion: str) -> "ForensicReportBuilder":
        self.report.conclusions.append(conclusion)
        return self
    
    def recommendation(self, recommendation: str) -> "ForensicReportBuilder":
        self.report.recommendations.append(recommendation)
        return self
    
    def appendix(self, title: str, content: str) -> "ForensicReportBuilder":
        self.report.appendices[title] = content
        return self
    
    def classify(self, classification: ReportClassification) -> "ForensicReportBuilder":
        self.report.classification = classification
        return self
    
    def build(self) -> ForensicReport:
        self.report.updated_at = datetime.now(timezone.utc).isoformat()
        return self.report


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def create_report(case_number: str, examiner_name: str) -> ForensicReportBuilder:
    """Create new forensic report builder."""
    builder = ForensicReportBuilder()
    builder.case(case_number).examiner(examiner_name)
    return builder


def create_finding(title: str, description: str, severity: FindingSeverity,
                   evidence_refs: List[str] = None) -> Finding:
    """Create forensic finding."""
    return Finding(
        title=title, description=description, severity=severity,
        evidence_references=evidence_refs or []
    )


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

def selftest() -> Tuple[int, List[str]]:
    """Run self-test of forensic report generator."""
    import tempfile
    lines = []
    failures = 0
    
    # Create report
    builder = create_report("CASE-2026-001", "Analyst John Doe")
    builder.examiner("John Doe", "Forensic Analyst", "Cyber Forensics Unit",
                    "BADGE-001", "john.doe@example.com", "555-0100",
                    ["CCFE", "GCFE", "GCFA"], "15 years digital forensics experience")
    builder.evidence("EVD-001", "Suspect's laptop", "laptop",
                    "a1b2c3d4e5f6...", "SHA-256", 500000000000,
                    "2026-11-03T10:00:00Z", "Analyst John Doe", "Evidence Room A",
                    True, True, ["HOLD-001"])
    builder.evidence("EVD-002", "External hard drive", "storage",
                    "d4e5f6a7b8c9...", "SHA-256", 2000000000000,
                    "2026-11-03T10:30:00Z", "Analyst Jane Smith", "Evidence Room B",
                    True, True, [])
    builder.tool("Volatility", "3.0", "Volatility Foundation", True,
                "a1b2c3d4...", "Memory analysis")
    builder.tool("Bulk Extractor", "1.6.0", "DoD Cyber Crime Center", True,
                "e5f6a7b8...", "File carving")
    builder.finding("Malware persistence via registry",
                   "Registry key HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run contains malicious entry",
                   FindingSeverity.HIGH, "Persistence",
                   ["EVD-001"],
                   "Registry analysis shows unauthorized auto-run entry pointing to malicious executable",
                   "Malware established persistence via registry run key",
                   "HIGH",
                   ["MITRE ATT&CK T1547.001"],
                   ["T1547.001"])
    builder.finding("Encrypted container detected",
                   "TrueCrypt container found in user's Documents folder",
                   FindingSeverity.MEDIUM, "Encryption",
                   ["EVD-002"],
                   "File entropy analysis indicates encrypted container",
                   "Encrypted container may contain evidence",
                   "HIGH",
                   ["NIST SP 800-86"], [])
    builder.timeline_event("2026-11-03T10:00:00Z", "Evidence acquired",
                          "Analyst John Doe", "Laptop imaged with dc3dd", "EVD-001")
    builder.timeline_event("2026-11-03T10:30:00Z", "Evidence acquired",
                          "Analyst Jane Smith", "External drive imaged with ewfacquire", "EVD-002")
    builder.timeline_event("2026-11-03T11:00:00Z", "Analysis started",
                          "Analyst John Doe", "Memory analysis with Volatility", "EVD-001")
    builder.methodology("Examination of suspect laptop and external drive for malware artifacts",
                       "Standard forensic process: acquire → preserve → analyze → report",
                       "Limited to logical acquisition; no physical memory dump obtained",
                       {"OS": "Windows 11", "RAM": "32GB", "Storage": "1TB SSD"},
                       ["SHA-256", "SHA-512"])
    builder.executive_summary("Examination of suspect's laptop and external drive revealed malware persistence mechanisms and an encrypted container. Malware established persistence via registry Run key (T1547.001). Encrypted container may contain exfiltrated data. Further analysis required.")
    builder.conclusion("Malware persistence confirmed via registry Run key modification.")
    builder.conclusion("Encrypted container discovered; contents unknown pending decryption.")
    builder.recommendation("Obtain decryption credentials for TrueCrypt container.")
    builder.recommendation("Expand scope to network traffic analysis for C2 communication.")
    builder.recommendation("Preserve original evidence under legal hold HOLD-001.")
    builder.classify(ReportClassification.CONFIDENTIAL)
    
    report = builder.build()
    
    # Test DOCX generation
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = Path(tmpdir) / "test_report.docx"
        try:
            report.generate_docx(docx_path)
            if docx_path.exists() and docx_path.stat().st_size > 10000:
                lines.append("PASS: DOCX generation")
            else:
                failures += 1
                lines.append("FAIL: DOCX generation (missing or too small)")
        except Exception as e:
            failures += 1
            lines.append(f"FAIL: DOCX generation error: {e}")
        
        # Test JSON generation
        json_path = Path(tmpdir) / "report.json"
        try:
            report.generate_json(json_path)
            if json_path.exists():
                lines.append("PASS: JSON generation")
            else:
                failures += 1
                lines.append("FAIL: JSON generation (missing)")
        except Exception as e:
            failures += 1
            lines.append(f"FAIL: JSON generation error: {e}")
    
    return failures, lines


if __name__ == "__main__":
    import tempfile
    failures, lines = selftest()
    for line in lines:
        print(line)
    print(f"\n{'PASS' if failures == 0 else 'FAIL'} ({failures} failures)")
    sys.exit(0 if failures == 0 else 1)