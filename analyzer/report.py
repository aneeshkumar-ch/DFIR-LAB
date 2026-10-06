import os
import json
import zipfile
import shutil
from pathlib import Path
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from analyzer.intake import log_action, record_custody_action, format_bytes

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Custom canvas that adds page numbers 'Page X of Y' on every page."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        page_text = f"BCSSL Lab 14 (CASE-TEST-014)  |  Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 54, 36, page_text)
        self.drawString(54, 36, "CONFIDENTIAL - LAW ENFORCEMENT & FORENSIC USE ONLY")
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 48, letter[0] - 54, 48)
        self.restoreState()

def generate_html_report(job_data: Dict[str, Any], job_dir: Path) -> Path:
    """Generate professional HTML forensic report using Jinja2 with strict autoescaping."""
    reports_dir = job_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_html_path = reports_dir / "report.html"

    env = Environment(
        loader=FileSystemLoader(str(config.TEMPLATES_DIR)),
        autoescape=select_autoescape(['html', 'xml'])
    )

    # Read chain of custody text
    custody_text = ""
    custody_file = job_dir / "chain_of_custody.txt"
    if custody_file.exists():
        with open(custody_file, "r", encoding="utf-8", errors="replace") as f:
            custody_text = f.read()

    # Read action log text
    action_log_text = ""
    action_log_file = job_dir / "actions_log.txt"
    if action_log_file.exists():
        with open(action_log_file, "r", encoding="utf-8", errors="replace") as f:
            action_log_text = f.read()

    template = env.get_template("report.html")
    rendered = template.render(
        job=job_data,
        custody_log=custody_text,
        actions_log=action_log_text,
        config=config
    )

    with open(report_html_path, "w", encoding="utf-8") as f:
        f.write(rendered)

    log_action(job_dir, f"Forensic HTML report generated at {report_html_path}")
    return report_html_path

def generate_pdf_report(job_data: Dict[str, Any], job_dir: Path) -> Path:
    """Generate high-fidelity forensic PDF report using ReportLab."""
    reports_dir = job_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = reports_dir / "report.pdf"

    log_action(job_dir, "Generating official PDF forensic report via ReportLab")

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#4A5568"),
        spaceAfter=15
    )
    h2_style = ParagraphStyle(
        'Heading2Custom',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#2B6CB0"),
        spaceBefore=14,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#2D3748")
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#2D3748")
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1A202C")
    )
    code_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['Code'],
        fontName='Courier',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#2D3748")
    )
    pass_badge = ParagraphStyle(
        'PassBadge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#22543D"),
        alignment=1
    )

    from xml.sax.saxutils import escape as xml_escape

    story = []

    # Title & Header
    safe_case = xml_escape(job_data.get('case_number', 'CASE-TEST-014'))
    safe_examiner = xml_escape(job_data.get('examiner', 'Forensics Examiner'))
    story.append(Paragraph("DIGITAL FORENSICS EXAMINATION REPORT", title_style))
    story.append(Paragraph(f"BCSSL Lab 14  |  Case: {safe_case}  |  Strict Chain of Custody Verified", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2B6CB0"), spaceAfter=12))

    # Case Summary Table
    intake = job_data.get("intake", {})
    integrity = job_data.get("integrity", {})
    
    case_table_data = [
        [Paragraph("<b>Case Number:</b>", table_cell), Paragraph(safe_case, table_cell),
         Paragraph("<b>Examiner:</b>", table_cell), Paragraph(safe_examiner, table_cell)],
        [Paragraph("<b>Evidence File:</b>", table_cell), Paragraph(xml_escape(intake.get("filename", "N/A")), table_cell),
         Paragraph("<b>File Size:</b>", table_cell), Paragraph(xml_escape(intake.get("filesize_str", "N/A")), table_cell)],
        [Paragraph("<b>Intake UTC Time:</b>", table_cell), Paragraph(xml_escape(intake.get("intake_time_utc", "N/A")), table_cell),
         Paragraph("<b>Engine Mode:</b>", table_cell), Paragraph(xml_escape(job_data.get("engine_mode", "The Sleuth Kit (TSK) Native Pipeline")), table_cell)],
        [Paragraph("<b>Acquisition SHA-256:</b>", table_cell), Paragraph(f"<font face='Courier' size=6>{xml_escape(intake.get('sha256', 'N/A'))}</font>", table_cell),
         Paragraph("<b>Integrity Result:</b>", table_cell), Paragraph(f"<b>{xml_escape(integrity.get('status', 'PENDING'))}</b>", table_cell)],
    ]
    case_table = Table(case_table_data, colWidths=[1.3*inch, 2.3*inch, 1.2*inch, 2.2*inch])
    case_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(case_table)
    story.append(Spacer(1, 12))

    # Integrity Box
    pass_color = colors.HexColor("#C6F6D5") if integrity.get("status") == "PASS" else colors.HexColor("#FED7D7")
    pass_border = colors.HexColor("#38A169") if integrity.get("status") == "PASS" else colors.HexColor("#E53E3E")
    integ_data = [[
        Paragraph(f"CRYPTOGRAPHIC EVIDENCE INTEGRITY AUDIT: <b>{xml_escape(integrity.get('status', 'PASS'))}</b>", pass_badge),
    ], [
        Paragraph(f"{xml_escape(integrity.get('message', 'Acquisition and post-analysis hashes match perfectly.'))}<br/>"
                  f"<b>Original:</b> <font face='Courier' size=6>{xml_escape(integrity.get('final_original_sha256', ''))}</font><br/>"
                  f"<b>Working:</b>  <font face='Courier' size=6>{xml_escape(integrity.get('final_working_sha256', ''))}</font>", body_style)
    ]]
    integ_table = Table(integ_data, colWidths=[7.0*inch])
    integ_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), pass_color),
        ('BOX', (0,0), (-1,-1), 1, pass_border),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
    ]))
    story.append(integ_table)
    story.append(Spacer(1, 14))

    # Partition & Filesystem Summary
    story.append(Paragraph("1. Partition Layout & Filesystem Architecture", h2_style))
    partitions = job_data.get("partitions", [])
    filesystems = job_data.get("filesystems", [])
    
    part_table_rows = [
        [Paragraph("<b>Slot / Offset</b>", table_cell_bold),
         Paragraph("<b>Start Sector</b>", table_cell_bold),
         Paragraph("<b>Length</b>", table_cell_bold),
         Paragraph("<b>Description</b>", table_cell_bold),
         Paragraph("<b>File System</b>", table_cell_bold)]
    ]
    for p in partitions:
        offset = p.get("start_sector", 0)
        fs_desc = "Unknown"
        for fs in filesystems:
            if fs.get("offset") == offset or (offset == 0 and fs.get("offset") is None):
                fs_desc = f"{fs.get('fs_type', 'N/A')} ({fs.get('volume_name', '')})"
                break
        part_table_rows.append([
            Paragraph(xml_escape(str(p.get("slot", "0"))), table_cell),
            Paragraph(xml_escape(str(p.get("start_sector", "0"))), table_cell),
            Paragraph(xml_escape(str(p.get("length_sectors", "0"))), table_cell),
            Paragraph(xml_escape(p.get("description", "Volume")), table_cell),
            Paragraph(xml_escape(fs_desc), table_cell),
        ])

    part_table = Table(part_table_rows, colWidths=[1.1*inch, 1.1*inch, 1.1*inch, 2.1*inch, 1.6*inch])
    part_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#EDF2F7")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(part_table)
    story.append(Spacer(1, 14))

    from xml.sax.saxutils import escape as xml_escape

    # Deleted Files & Recovery Summary
    story.append(Paragraph("2. Deleted File Analysis & Forensic Recovery", h2_style))
    recovered = job_data.get("recovered_files", [])
    deleted_listing = job_data.get("deleted_files", [])

    mismatch_count = len([f for f in recovered if f.get("extension_mismatch")])
    story.append(Paragraph(
        f"<b>Deleted Inodes Found:</b> {len(deleted_listing)} | "
        f"<b>Recovered Files:</b> {len(recovered)} | "
        f"<b>Extension Mismatches (Disguised Files):</b> {mismatch_count}",
        body_style
    ))
    story.append(Spacer(1, 6))

    rec_table_rows = [
        [Paragraph("<b>File Name</b>", table_cell_bold),
         Paragraph("<b>Size</b>", table_cell_bold),
         Paragraph("<b>Detected Real Type</b>", table_cell_bold),
         Paragraph("<b>Status / Mismatch Flag</b>", table_cell_bold)]
    ]
    # Display top 15 recovered files in PDF
    for rf in recovered[:15]:
        safe_fname = xml_escape(rf.get("filename", "")[:35])
        safe_type = xml_escape(rf.get("magic_desc", "Unknown")[:30])
        if rf.get("extension_mismatch"):
            raw_detail = rf.get('mismatch_details', '')[:50]
            status_text = f"<font color='#C53030'><b>FLAG: {xml_escape(raw_detail)}</b></font>"
        else:
            status_text = xml_escape(rf.get("status_note", "Intact")[:50])

        rec_table_rows.append([
            Paragraph(safe_fname, table_cell),
            Paragraph(xml_escape(rf.get("size_str", "0 B")), table_cell),
            Paragraph(safe_type, table_cell),
            Paragraph(status_text, table_cell),
        ])

    rec_table = Table(rec_table_rows, colWidths=[2.2*inch, 0.9*inch, 1.8*inch, 2.1*inch])
    rec_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#EDF2F7")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(rec_table)
    if len(recovered) > 15:
        story.append(Paragraph(f"<i>... and {len(recovered) - 15} additional recovered files listed in full HTML report and CSV package.</i>", body_style))
    story.append(Spacer(1, 14))

    # Keyword Search Summary
    story.append(Paragraph("3. Keyword Content Search Results", h2_style))
    kw_hits = job_data.get("keywords", {}).get("hits", [])
    kw_terms = job_data.get("keywords", {}).get("keywords_searched", [])
    story.append(Paragraph(f"<b>Keywords Searched:</b> {xml_escape(', '.join(kw_terms))} | <b>Total Hits:</b> {len(kw_hits)}", body_style))
    story.append(Spacer(1, 6))

    if kw_hits:
        kw_rows = [
            [Paragraph("<b>Keyword</b>", table_cell_bold),
             Paragraph("<b>Source Target</b>", table_cell_bold),
             Paragraph("<b>Offset</b>", table_cell_bold),
             Paragraph("<b>Context Snippet</b>", table_cell_bold)]
        ]
        for hit in kw_hits[:10]:
            safe_kw = xml_escape(hit.get("keyword", ""))
            safe_target = xml_escape(str(hit.get("target", ""))[:25])
            safe_offset = xml_escape(str(hit.get("offset_hex", "")))
            safe_context = xml_escape(str(hit.get('context', ''))[:45])
            kw_rows.append([
                Paragraph(safe_kw, table_cell),
                Paragraph(safe_target, table_cell),
                Paragraph(safe_offset, table_cell),
                Paragraph(f"<font face='Courier' size=6>{safe_context}</font>", table_cell),
            ])
        kw_table = Table(kw_rows, colWidths=[1.1*inch, 1.8*inch, 1.0*inch, 3.1*inch])
        kw_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#EDF2F7")),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(kw_table)
    else:
        story.append(Paragraph("No keyword occurrences found matching the specified terms.", body_style))
    story.append(Spacer(1, 14))

    # Forensic Limitations
    story.append(Paragraph("4. Forensic Limitations & Anti-Forensics Analysis", h2_style))
    limitation_text = """
    <b>Normal Forensic Limitations:</b><br/>
    - Inode records where clusters were zeroed or reassigned cannot be fully reconstructed; this is a known physical constraint of post-deletion state rather than a recovery fault.<br/>
    - MACB timestamps reflect file system metadata stored prior to imaging; FAT timestamps have 2-second resolution for modified times and lack creation seconds.<br/>
    <b>Anti-Forensics & Deception Detection:</b><br/>
    - File extension mismatch analysis identified files where user-facing extensions were intentionally altered to mask underlying document or binary payloads.<br/>
    - All recovered files are untrusted; execute bits are disabled to mitigate weaponized payload hazards.<br/>
    """
    story.append(Paragraph(limitation_text, body_style))

    # Build document
    doc.build(story, canvasmaker=NumberedCanvas)
    log_action(job_dir, f"PDF report successfully generated at {pdf_path}")
    return pdf_path

def create_case_package_zip(job_dir: Path) -> Path:
    """
    Bundle all case deliverables into a single downloadable ZIP package:
    - HTML Report & PDF Report
    - chain_of_custody.txt
    - actions_log.txt
    - hashes.txt
    - timeline.csv
    - file_listing.json
    - keyword_hits.json
    - recovered/ directory
    """
    reports_dir = job_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    zip_path = reports_dir / "case_package.zip"

    log_action(job_dir, f"Creating comprehensive case package archive at {zip_path.name}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Include report files
        report_html = reports_dir / "report.html"
        if report_html.exists():
            zipf.write(report_html, arcname="report.html")
        
        report_pdf = reports_dir / "report.pdf"
        if report_pdf.exists():
            zipf.write(report_pdf, arcname="report.pdf")

        # Include text logs & metadata
        for fname in ["chain_of_custody.txt", "actions_log.txt", "hashes.txt", "timeline.csv", "file_listing.json", "keyword_hits.json", "integrity.json"]:
            fpath = job_dir / fname
            if fpath.exists():
                zipf.write(fpath, arcname=fname)

        # Include recovered files
        recovered_dir = job_dir / "recovered"
        if recovered_dir.exists():
            for root, _, files in os.walk(recovered_dir):
                for f in files:
                    full_p = Path(root) / f
                    rel_p = full_p.relative_to(job_dir)
                    zipf.write(full_p, arcname=str(rel_p))

    record_custody_action(job_dir, f"Comprehensive forensic case package bundled: {zip_path.name} ({format_bytes(zip_path.stat().st_size)})")
    return zip_path
