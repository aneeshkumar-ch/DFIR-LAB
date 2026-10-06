import os
import re
import sys
from pathlib import Path

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

# --- FORBIDDEN TEXT CHECKER ---
FORBIDDEN_PATTERNS = [
    "D:", "C:", ":\\", "\\", "127.0.0.1", "localhost", "5000", "http://",
    "SHA-256", "SHA256", "sha256"
]
HEX_32_REGEX = re.compile(r'[0-9a-fA-F]{32,}')

def audit_document_text(doc, doc_name):
    """Scan all paragraphs, tables, headers, and footers for forbidden strings."""
    violations = []
    
    def check_text(text, location):
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                violations.append(f"[{doc_name}] Found forbidden '{pattern}' in {location}: {text[:80]}")
        hex_match = HEX_32_REGEX.search(text)
        if hex_match:
            violations.append(f"[{doc_name}] Found 32+ hex string '{hex_match.group(0)[:15]}...' in {location}")

    for i, p in enumerate(doc.paragraphs):
        check_text(p.text, f"Paragraph {i+1}")

    for t_idx, table in enumerate(doc.tables):
        for r_idx, row in enumerate(table.rows):
            for c_idx, cell in enumerate(row.cells):
                for p_idx, p in enumerate(cell.paragraphs):
                    check_text(p.text, f"Table {t_idx+1} Row {r_idx+1} Col {c_idx+1} P {p_idx+1}")

    for s_idx, section in enumerate(doc.sections):
        for p in section.header.paragraphs:
            check_text(p.text, f"Section {s_idx+1} Header")
        for table in section.header.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        check_text(p.text, f"Section {s_idx+1} Header Table")
        for p in section.footer.paragraphs:
            check_text(p.text, f"Section {s_idx+1} Footer")
        for table in section.footer.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        check_text(p.text, f"Section {s_idx+1} Footer Table")

    return violations


# --- XML STYLING UTILITIES (NO BACKSLASHES IN ANY TEXT) ---
def setup_doc_layout(doc, margin_in=0.8):
    for section in doc.sections:
        section.page_width = Inches(8.27)
        section.page_height = Inches(11.69)
        section.top_margin = Inches(margin_in)
        section.bottom_margin = Inches(margin_in)
        section.left_margin = Inches(margin_in)
        section.right_margin = Inches(margin_in)

    normal = doc.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(11)
    normal.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.space_before = Pt(0)

def setup_header_and_footer(doc, header_text, footer_label):
    for section in doc.sections:
        # Header
        hdr = section.header
        p_hdr = hdr.paragraphs[0]
        p_hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_hdr.text = header_text
        p_hdr.style.font.name = 'Calibri'
        p_hdr.style.font.size = Pt(8.5)
        p_hdr.style.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

        # Footer
        ftr = section.footer
        p_ftr = ftr.paragraphs[0]
        p_ftr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_ftr.text = footer_label + "  |  Page "
        p_ftr.style.font.name = 'Calibri'
        p_ftr.style.font.size = Pt(8.5)
        p_ftr.style.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

        fld_page = OxmlElement('w:fldSimple')
        fld_page.set(qn('w:instr'), 'PAGE')
        p_ftr._p.append(fld_page)

        run_of = p_ftr.add_run(" of ")
        run_of.font.name = 'Calibri'
        run_of.font.size = Pt(8.5)
        run_of.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

        fld_num = OxmlElement('w:fldSimple')
        fld_num.set(qn('w:instr'), 'NUMPAGES')
        p_ftr._p.append(fld_num)

def set_cell_bg(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_pad(cell, top=70, bottom=70, left=100, right=100):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)

def set_tbl_borders(table, color="CBD5E1"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        f'<w:left w:val="none"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        f'<w:right w:val="none"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

def add_title_block(doc, title, subtitle, audience, case_id="CASE-TEST-014"):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    set_cell_bg(cell, "F8FAFC")
    set_cell_pad(cell, top=130, bottom=130, left=160, right=160)

    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f'<w:left w:val="single" w:sz="36" w:space="0" w:color="1E3A8A"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f'<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)

    p0 = cell.paragraphs[0]
    p0.paragraph_format.space_after = Pt(2)
    r_tag = p0.add_run(f"BCSSL LAB 14  |  CASE: {case_id}  |  {audience.upper()}")
    r_tag.font.name = 'Calibri'
    r_tag.font.size = Pt(9)
    r_tag.font.bold = True
    r_tag.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)

    p1 = cell.add_paragraph()
    p1.paragraph_format.space_after = Pt(2)
    p1.paragraph_format.space_before = Pt(2)
    r_title = p1.add_run(title)
    r_title.font.name = 'Calibri'
    r_title.font.size = Pt(16)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)

    p2 = cell.add_paragraph()
    p2.paragraph_format.space_after = Pt(0)
    r_sub = p2.add_run(subtitle)
    r_sub.font.name = 'Calibri'
    r_sub.font.size = Pt(10)
    r_sub.font.color.rgb = RGBColor(0x47, 0x55, 0x69)

    doc.add_paragraph()

def add_heading_1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(11)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.size = Pt(13.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)
    return p

def add_heading_2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.size = Pt(11.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
    return p

def add_heading_3(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.size = Pt(10.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x33, 0x41, 0x55)
    return p

def add_callout(doc, text, title="NOTE", callout_type="info"):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    fill_hex = "EFF6FF" if callout_type == "info" else ("FFFBEB" if callout_type == "warning" else "F8FAFC")
    border_hex = "2563EB" if callout_type == "info" else ("D97706" if callout_type == "warning" else "64748B")
    
    set_cell_bg(cell, fill_hex)
    set_cell_pad(cell, top=60, bottom=60, left=100, right=100)

    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="none"/>'
        f'<w:left w:val="single" w:sz="24" w:space="0" w:color="{border_hex}"/>'
        f'<w:bottom w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)

    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing = 1.12
    r_t = p.add_run(f"[{title}] ")
    r_t.font.name = 'Calibri'
    r_t.font.size = Pt(9.5)
    r_t.font.bold = True
    r_t.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A) if callout_type == "info" else RGBColor(0x92, 0x40, 0x0E)

    r_msg = p.add_run(text)
    r_msg.font.name = 'Calibri'
    r_msg.font.size = Pt(9.5)
    r_msg.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)

def add_code_box(doc, code_str):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    set_cell_bg(cell, "F1F5F9")
    set_cell_pad(cell, top=50, bottom=50, left=90, right=90)

    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f'<w:left w:val="single" w:sz="12" w:space="0" w:color="64748B"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f'<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)

    lines = code_str.strip().split('\n')
    for idx, line in enumerate(lines):
        p = cell.paragraphs[0] if idx == 0 else cell.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.line_spacing = 1.05
        run = p.add_run(line)
        run.font.name = 'Consolas'
        run.font.size = Pt(9.0)
        run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

def add_clean_table(doc, headers, data_rows, col_widths=None):
    table = doc.add_table(rows=len(data_rows) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_tbl_borders(table, color="CBD5E1")

    hdr_cells = table.rows[0].cells
    for i, h_text in enumerate(headers):
        hdr_cells[i].text = h_text
        set_cell_bg(hdr_cells[i], "1E3A8A")
        set_cell_pad(hdr_cells[i], top=70, bottom=70, left=80, right=80)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.runs[0].font.name = 'Calibri'
        p.runs[0].font.size = Pt(9.5)
        p.runs[0].font.bold = True
        p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    for row_idx, row_data in enumerate(data_rows):
        row_cells = table.rows[row_idx + 1].cells
        bg_color = "F8FAFC" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx, cell_value in enumerate(row_data):
            row_cells[col_idx].text = str(cell_value)
            set_cell_bg(row_cells[col_idx], bg_color)
            set_cell_pad(row_cells[col_idx], top=50, bottom=50, left=80, right=80)
            p = row_cells[col_idx].paragraphs[0]
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1.1
            if len(p.runs) > 0:
                p.runs[0].font.name = 'Calibri'
                p.runs[0].font.size = Pt(9.0)
                p.runs[0].font.color.rgb = RGBColor(0x1F, 0x29, 0x37)

    if col_widths:
        for row in table.rows:
            for i, w in enumerate(col_widths):
                row.cells[i].width = Inches(w)

    return table

def add_answer_box(doc, height_lines=2):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    set_cell_bg(cell, "FAFAFA")
    set_cell_pad(cell, top=60, bottom=60, left=90, right=90)

    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="94A3B8"/>'
        f'<w:left w:val="single" w:sz="6" w:space="0" w:color="94A3B8"/>'
        f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="94A3B8"/>'
        f'<w:right w:val="single" w:sz="6" w:space="0" w:color="94A3B8"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)

    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("Answer: ")
    r.font.name = 'Calibri'
    r.font.size = Pt(9.5)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0x47, 0x55, 0x69)

    for _ in range(height_lines - 1):
        p_line = cell.add_paragraph()
        p_line.paragraph_format.space_after = Pt(2)
        p_line.paragraph_format.line_spacing = 1.2


# ==============================================================================
# DOCUMENT 1: PROJECT BUILDING GUIDE (8 to 10 pages)
# ==============================================================================
def build_document_1():
    doc = docx.Document()
    setup_doc_layout(doc, margin_in=0.75)
    setup_header_and_footer(doc, "BCSSL Lab 14 | Project Building Guide", "1_Project_Building_Guide")

    add_title_block(
        doc,
        title="Document 1: Project Building Guide",
        subtitle="Step-by-step setup and architecture guide for instructors and lab builders",
        audience="Instructor and Lab Developer",
        case_id="CASE-TEST-014"
    )

    # Section 1: What We Are Building
    add_heading_1(doc, "1. What We Are Building")
    doc.add_paragraph(
        "We are building a web-based digital forensics investigation tool called Digital Forensics Analyzer (DFA-14). "
        "Digital forensics means using software to inspect storage drives after an incident, "
        "much like detectives search a physical room for clues. "
        "When an examiner uploads a disk image—which is an exact digital photocopy of an entire storage drive—the tool "
        "automatically runs nine forensic steps without needing any manual clicks. "
        "It protects the original evidence so it cannot be altered, calculates file fingerprints to prove integrity, "
        "recovers deleted files from disk metadata, builds an activity timeline, and creates a structured forensic report."
    )

    p_diag = doc.add_paragraph("High-Level Pipeline Workflow:")
    p_diag.runs[0].font.bold = True
    
    diagram_box = (
        "[ Evidence Disk Image ]  -->  [ Flask Web Application ]  -->  [ 9 Automated Phases ]  -->  [ Structured Reports and ZIP ]\n"
        " (Raw or Expert Witness)      (Local Browser Portal)          (Integrity, Recovery, Search)   (Printable PDF, HTML, Archive)"
    )
    add_code_box(doc, diagram_box)

    add_callout(
        doc,
        "All pipeline procedures are modeled on ISO/IEC 27037 principles. "
        "This standard gives international guidelines for handling digital evidence properly so findings are accurate and reliable.",
        title="STANDARDS NOTE",
        callout_type="info"
    )

    add_heading_2(doc, "The Five-Stage Evidence Handling Lifecycle")
    doc.add_paragraph(
        "To maintain strict scientific integrity, the analyzer processes every evidence image through a five-stage lifecycle:"
    )
    headers_life = ["Lifecycle Stage", "Key Forensic Action", "Integrity Assurance Goal"]
    rows_life = [
        ["1. Intake and Staging", "Receives uploaded disk image and assigns unique case identifier.", "Ensures evidence is isolated in a dedicated case directory."],
        ["2. Preservation Locking", "Applies software read-only attributes to the original image.", "Prevents accidental modification, deletion, or tampering."],
        ["3. Baseline Fingerprinting", "Calculates cryptographic file fingerprints on evidence.", "Establishes a mathematical baseline before any analysis begins."],
        ["4. Forensic Examination", "Executes partition scanning, file listing, recovery, and timeline.", "Extracts all clues and artifacts from an isolated working copy."],
        ["5. Final Verification", "Calculates post-analysis fingerprints and compiles reports.", "Proves the evidence remained unaltered and delivers structured findings."]
    ]
    add_clean_table(doc, headers_life, rows_life, [1.6, 2.7, 2.4])

    add_heading_2(doc, "Manual Forensics vs. Automated Pipeline")
    doc.add_paragraph(
        "In a traditional manual investigation, an examiner must type dozens of complex terminal commands by hand. "
        "This manual process takes several hours and leaves room for human typing mistakes. "
        "The Digital Forensics Analyzer automates every repetitive step while keeping the exact same scientific accuracy."
    )
    headers_comp = ["Investigation Task", "Traditional Manual Forensics", "Automated Forensics Analyzer (DFA-14)"]
    rows_comp = [
        ["Evidence Protection", "Examiner manually sets read-only switches or uses hardware devices.", "Tool automatically applies software read-only attributes upon upload."],
        ["Hashing and Verification", "Examiner runs hashing commands and writes down long numbers.", "File fingerprints are computed automatically before and after."],
        ["Deleted File Recovery", "Examiner inspects directories and extracts deleted entries one by one.", "The Sleuth Kit extracts all deleted files automatically into a safe folder."],
        ["Timeline Creation", "Examiner exports a bodyfile and runs timeline scripts by hand.", "Activity spreadsheet and chronological events are generated seamlessly."],
        ["Report Generation", "Examiner pastes text into documents over several hours.", "Produces an interactive web report and printable PDF in seconds."]
    ]
    add_clean_table(doc, headers_comp, rows_comp, [1.5, 2.6, 2.6])

    # Section 2: What You Need
    add_heading_1(doc, "2. What You Need")
    doc.add_paragraph(
        "Before building and running the tool, make sure your computer has the following hardware and software installed. "
        "The project runs on a standard 64-bit Windows laptop or desktop."
    )

    headers_req = ["Component", "Version", "How to Obtain", "Purpose in Project"]
    rows_req = [
        ["Operating System", "Windows 10 or 11 (64-bit)", "Microsoft Windows", "Host operating system for all tools and scripts."],
        ["Python", "3.10 or higher (tested 3.13.15)", "Standard Python Installer", "Runs the web server, pipeline, and test scripts."],
        ["Flask", "3.1.0", "Install via requirements.txt", "Provides the web interface and background job manager."],
        ["The Sleuth Kit", "4.15.0 (Win32)", "Install The Sleuth Kit binaries", "Native tools for inspecting partitions and recovering files."],
        ["Autopsy", "4.23.1 (64-bit)", "Install Autopsy on your computer", "Forensic GUI engine tried first during Phase 8."],
        ["Perl", "5.42 or higher", "Standard Perl Interpreter", "Executes the timeline script to sort file dates (fallback included)."],
        ["ReportLab / WeasyPrint", "Latest", "Install via requirements.txt", "Compiles the structured forensic report into a PDF."],
        ["Memory (RAM)", "8 GB or higher", "System Hardware", "Ensures smooth processing of large disk images."],
        ["Free Storage", "10 GB minimum", "Local Hard Drive", "Holds disk images, recovered files, and case archives."]
    ]
    add_clean_table(doc, headers_req, rows_req, [1.4, 1.3, 2.0, 2.0])

    add_callout(
        doc,
        "Install The Sleuth Kit and Autopsy, and make sure the commands work in PowerShell. "
        "Ensure Python and Perl are available in your system path so the scripts run smoothly.",
        title="INSTALLATION TIP",
        callout_type="info"
    )

    # Section 3: The Files in the Project
    add_heading_1(doc, "3. The Files in the Project")
    doc.add_paragraph(
        "The project consists of twenty-four specialized files working together. "
        "The table below lists each file name and its exact role in the investigation system."
    )

    headers_files = ["File Name", "Component Group", "Purpose in One Simple Line"]
    rows_files = [
        ["app.py", "Web Application", "Runs the local web server and handles user uploads and status requests."],
        ["config.py", "Configuration", "Stores settings, tool timeouts, and upload size limits."],
        ["requirements.txt", "Dependencies", "Lists required Python packages for one-step installation."],
        ["README.md", "Documentation", "Provides operational security guidelines and safety rules."],
        ["evidence.py", "Forensic Engine", "Phase 1: Handles image intake and sets read-only protection."],
        ["hashing.py", "Forensic Engine", "Phase 2: Computes baseline cryptographic file fingerprints."],
        ["partition.py", "Forensic Engine", "Phase 3: Detects partition tables and starting sector offsets."],
        ["file_listing.py", "Forensic Engine", "Phase 4: Enumerates active and deleted file system records."],
        ["recovery.py", "Forensic Engine", "Phase 5: Restores deleted files using metadata cluster pointers."],
        ["strings.py", "Forensic Engine", "Phase 6: Extracts readable ASCII and Unicode text words."],
        ["timeline.py", "Forensic Engine", "Phase 7: Reconstructs chronological file activity events."],
        ["heuristics.py", "Forensic Engine", "Phase 8: Scans for disguised file extensions and search terms."],
        ["reporting.py", "Forensic Engine", "Phase 9: Assembles HTML, PDF, and ZIP case deliverables."],
        ["pipeline.py", "Orchestration", "Coordinates all nine phases in strict sequential order."],
        ["autopsy_runner.py", "Forensic Engine", "Runs the Autopsy engine with an automatic 25-second timeout."],
        ["index.html", "Web Templates", "Upload form web page where examiners enter case details."],
        ["job.html", "Web Templates", "Live progress dashboard showing checkmarks as phases complete."],
        ["report.html", "Web Templates", "Interactive structured forensic report viewed in web browsers."],
        ["style.css", "Static Assets", "Stylesheet providing clean visual layouts for the web pages."],
        ["practice_evidence.dd", "Test Evidence", "Practice disk image used for student exercises and pipeline tests."],
        ["make_practice_image.py", "Test Utilities", "Script used to generate the practice evidence disk image."],
        ["test_pipeline.py", "Verification", "Automated test script verifying the full nine-phase pipeline."],
        ["test_web_endpoints.py", "Verification", "Automated test script verifying web routes and file downloads."],
        ["test_e01.py", "Verification", "Integration test validating analysis on large disk images."]
    ]
    add_clean_table(doc, headers_files, rows_files, [1.8, 1.4, 3.5])

    # Section 4: The 3 Parts of the Project
    add_heading_1(doc, "4. The Three Parts of the Project")
    doc.add_paragraph(
        "The project is organized into three cooperating layers: the Flask web application, "
        "the Python automation pipeline, and the underlying forensic tools."
    )

    # Part C: Flask
    add_heading_2(doc, "Part A - Flask Web Application")
    doc.add_paragraph(
        "Flask is a lightweight Python web framework. It acts like a digital receptionist. "
        "It runs locally on your computer so outside network computers cannot connect to it. "
        "When an examiner opens the web page, they can fill in the case number, examiner name, and choose an evidence file. "
        "When they click Submit, Flask saves the file to a temporary staging area and starts the analysis in a background thread. "
        "A thread is like a separate worker running in the background. "
        "Because the worker runs separately, the web browser never freezes and can show live progress updates."
    )

    p_ex1 = doc.add_paragraph("Upload Route Excerpt (from app.py, max 15 lines):")
    p_ex1.runs[0].font.bold = True
    code_upload = (
        "@app.route('/upload', methods=['POST'])\n"
        "def upload_image():\n"
        "    file = request.files.get('image')\n"
        "    case_num = request.form.get('case_number', 'CASE-TEST-014')\n"
        "    examiner = request.form.get('examiner', 'Analyst')\n"
        "    job_id = create_unique_job_id()\n"
        "    staging_file = save_upload_to_staging(file)\n"
        "    thread = threading.Thread(\n"
        "        target=run_analysis_pipeline,\n"
        "        args=(job_id, staging_file, file.filename, examiner, case_num)\n"
        "    )\n"
        "    thread.start()\n"
        "    return redirect(url_for('job_status', job_id=job_id))"
    )
    add_code_box(doc, code_upload)

    p_routes = doc.add_paragraph("Application URL Endpoints and Forensic Functions:")
    headers_routes = ["URL Route", "HTTP Method", "Function and Forensic Purpose"]
    rows_routes = [
        ["/", "GET", "Displays the main upload dashboard where examiners enter case information."],
        ["/upload", "POST", "Validates the uploaded disk image, creates case workspace, and starts pipeline."],
        ["/job/<job_id>", "GET", "Displays the live progress monitor with real-time status bars."],
        ["/job/<job_id>/status", "GET", "Returns machine-readable status indicating current phase and errors."],
        ["/job/<job_id>/report", "GET", "Renders the full structured forensic report in the web browser."],
        ["/job/<job_id>/download/pdf", "GET", "Downloads the compiled structured forensic report as a PDF document."],
        ["/job/<job_id>/download/zip", "GET", "Downloads the complete case deliverables package as a ZIP archive."],
        ["/job/<job_id>/download/custody", "GET", "Downloads the raw Chain of Custody audit ledger text file."],
        ["/job/<job_id>/download/report.json", "GET", "Downloads machine-readable case summary data in JSON format."]
    ]
    add_clean_table(doc, headers_routes, rows_routes, [2.3, 1.1, 3.3])

    # Part B: Python Automation
    add_heading_2(doc, "Part B - Python Automation (The 9 Phases)")
    doc.add_paragraph(
        "The file pipeline.py is the conductor of the forensic orchestra. "
        "It executes nine specialized analysis phases in strict sequential order. "
        "If any step fails or detects evidence tampering, the pipeline records the issue immediately."
    )

    headers_phases = ["Phase Number and Name", "What It Does in One Simple Line", "Python File"]
    rows_phases = [
        ["1. Evidence Intake", "Locks evidence with read-only protection and makes a working copy.", "evidence.py"],
        ["2. Baseline Fingerprints", "Calculates cryptographic file fingerprints to prove integrity.", "hashing.py"],
        ["3. Partition Inspection", "Finds partition layouts (MBR or GPT) and starting sector numbers.", "partition.py"],
        ["4. File System Listing", "Reads directory tables and lists all active and deleted files.", "file_listing.py"],
        ["5. Metadata Recovery", "Extracts deleted files using catalog records and cluster pointers.", "recovery.py"],
        ["6. String Extraction", "Scans disk bytes for readable text words with exact byte offsets.", "strings.py"],
        ["7. Timeline Synthesis", "Sorts file activity into a chronological security schedule.", "timeline.py"],
        ["8. Heuristics & Keywords", "Flags disguised files (fake extensions) and matches key terms.", "heuristics.py"],
        ["9. Deliverables Assembly", "Generates the HTML report, PDF document, and ZIP case package.", "reporting.py"]
    ]
    add_clean_table(doc, headers_phases, rows_phases, [1.8, 3.4, 1.5])

    p_ex2 = doc.add_paragraph("Pipeline Execution Excerpt (from pipeline.py, max 15 lines):")
    p_ex2.runs[0].font.bold = True
    code_pipe = (
        "def run_analysis_pipeline(job_id, staging_file, filename, examiner, case_num):\n"
        "    phase1_intake(job_id, staging_file, filename)\n"
        "    phase2_baseline_fingerprints(job_id)\n"
        "    part_offset = phase3_partition_analysis(job_id)\n"
        "    phase4_file_listing(job_id, part_offset)\n"
        "    phase5_file_recovery(job_id, part_offset)\n"
        "    phase6_string_extraction(job_id)\n"
        "    phase7_timeline_reconstruction(job_id)\n"
        "    phase8_heuristics_analysis(job_id)\n"
        "    phase9_deliverables_assembly(job_id, examiner, case_num)\n"
        "    update_job_status(job_id, 'completed')"
    )
    add_code_box(doc, code_pipe)

    doc.add_paragraph(
        "During execution, pipeline.py updates a status file in your case folder. "
        "The web browser checks this file every two seconds to update the progress bar smoothly."
    )
    headers_state = ["Status Field", "Data Type", "Role in Live Dashboard"]
    rows_state = [
        ["overall_status", "Text", "Indicates if the pipeline is active, completed, or encountered an error."],
        ["engine_mode", "Text", "Reports whether Autopsy or The Sleuth Kit is currently processing."],
        ["phase_progress", "Dictionary", "Tracks individual status for each of the nine forensic phases."],
        ["integrity_audit", "Dictionary", "Records pre and post-analysis fingerprints and PASS or FAIL outcome."],
        ["recovered_summary", "List", "Stores extracted file records and flags for disguised extensions."]
    ]
    add_clean_table(doc, headers_state, rows_state, [1.6, 1.4, 3.7])

    # Part C: Forensic Tools & Deliverables
    add_heading_2(doc, "Part C - Forensic Tools and Deliverables")
    doc.add_paragraph(
        "Rather than reinventing wheel mechanisms, our Python code calls established forensic binaries. "
        "The Sleuth Kit is a widely respected set of open-source forensic tools created by Brian Carrier. "
        "Autopsy is a graphical analysis platform built on top of The Sleuth Kit. "
        "The table below shows each tool used and what it does."
    )

    headers_tools = ["Tool / Command", "Source / Suite", "Purpose in One Simple Line"]
    rows_tools = [
        ["mmls", "The Sleuth Kit", "Displays partition layout and starting sector numbers on the disk."],
        ["fsstat", "The Sleuth Kit", "Shows file system details such as block size and volume label."],
        ["fls", "The Sleuth Kit", "Lists files in directory trees and marks deleted files with an asterisk (*)."],
        ["icat", "The Sleuth Kit", "Extracts file contents directly from a specific inode (catalog number)."],
        ["tsk_recover", "The Sleuth Kit", "Automatically recovers all unallocated and deleted files to a folder."],
        ["srch_strings", "The Sleuth Kit", "Extracts ASCII and Unicode readable words with byte locations."],
        ["autopsy64", "Autopsy Engine", "Tries automated ingest first; if it exceeds 25s, falls back to TSK."],
        ["hashlib", "Python Standard Library", "Computes cryptographic file fingerprints to prove integrity."],
        ["mactime", "The Sleuth Kit / Perl", "Converts raw bodyfile timestamps into a chronological spreadsheet."]
    ]
    add_clean_table(doc, headers_tools, rows_tools, [1.5, 1.8, 3.4])

    doc.add_paragraph(
        "When the pipeline finishes, it gathers all results into the case deliverables described below:"
    )
    headers_deliv = ["Deliverable Item", "Output File Name", "Description and Contents"]
    rows_deliv = [
        ["HTML Report", "report.html", "Interactive browser report with summary cards, tables, and alerts."],
        ["PDF Report", "report.pdf", "Printable structured forensic report modeled on ISO/IEC 27037 principles."],
        ["Case Package", "case_package.zip", "Complete ZIP archive containing all reports, logs, and artifacts."],
        ["Activity Timeline", "timeline.csv", "Chronological table tracking file modified, accessed, and created dates."],
        ["Extracted Strings", "strings_ascii.txt", "Text file containing all readable words found across the disk."],
        ["Chain of Custody", "chain_of_custody.txt", "Audit ledger recording who handled the evidence and exact timestamps."],
        ["Recovered Files", "recovered_files", "Folder containing all deleted files extracted from the disk."]
    ]
    add_clean_table(doc, headers_deliv, rows_deliv, [1.5, 1.8, 3.4])

    # Section 5: How to Run It
    add_heading_1(doc, "5. How to Run It")
    doc.add_paragraph(
        "Follow these five simple steps to start the web application and begin investigating an evidence image."
    )

    steps_run = [
        ("Step 1: Configure Antivirus Exclusion",
         "Your antivirus scanner may try to quarantine recovered test files. Open PowerShell as Administrator and run the exclusion command for your project folder:",
         'Add-MpPreference -ExclusionPath "<your-project-folder>"'),
        ("Step 2: Open PowerShell in Your Project Folder",
         "Open a standard PowerShell terminal and move into your project folder where the application files are located:",
         "cd <your-project-folder>"),
        ("Step 3: Start the Web Application",
         "Launch the local server by running the main Python file:",
         "python app.py"),
        ("Step 4: Open Your Web Browser",
         "Open your preferred web browser and navigate to the tool's local page (your instructor will tell you how).",
         "# Open the web page in Google Chrome, Microsoft Edge, or Firefox"),
        ("Step 5: Upload an Image and Start Analysis",
         "Fill in Case Number (CASE-TEST-014), enter your name as Examiner, select practice_evidence.dd, and click Start Analysis.",
         "# Click the green 'Start Analysis' button on the web page")
    ]

    for title, desc, cmd in steps_run:
        add_heading_3(doc, title)
        p = doc.add_paragraph(desc)
        p.paragraph_format.space_after = Pt(2)
        add_code_box(doc, cmd)

    # Section 6: How to Test It
    add_heading_1(doc, "6. How to Test It")
    doc.add_paragraph(
        "The project includes three automated test scripts. "
        "You can run each script directly from PowerShell to verify that the tool works properly before students use it."
    )

    headers_test = ["Test Script", "Command to Run", "What It Tests", "Real Result in Our Testing"]
    rows_test = [
        ["test_pipeline.py", "python test_pipeline.py", "Runs all 9 phases on practice_evidence.dd", "PASS (35.41s). 12 files recovered, 2 disguised files detected, integrity PASS."],
        ["test_web_endpoints.py", "python test_web_endpoints.py", "Tests all web routes and downloads", "PASS (0.85s). All routes returned successful status codes. PDF and ZIP verified."],
        ["test_e01.py", "python test_e01.py", "Full run on 309 MB Expert Witness image", "PASS (246.62s). Sector 65664 detected, 3,982 files recovered, 343 MB ZIP created."]
    ]
    add_clean_table(doc, headers_test, rows_test, [1.5, 1.8, 1.7, 1.7])

    # Section 7: Problems to Fix
    add_heading_1(doc, "7. Problems to Fix and Important Nuances")
    doc.add_paragraph(
        "During live testing on Windows, we discovered several technical nuances. "
        "Keep these solutions in mind if you run into unexpected behavior."
    )

    issues = [
        ("1. Autopsy Takes Too Long to Start Up (25-Second Timeout)",
         "In our live tests on Windows, launching Autopsy took longer than 25 seconds because the graphical interface initializes dozens of modules. "
         "Our tool uses a 25-second timer in its configuration settings. "
         "When the timer expires, the tool stops waiting and automatically uses The Sleuth Kit command-line tools instead. "
         "This fallback is completely normal and ensures the analysis always finishes quickly and accurately."),
        ("2. Partition Offsets (MBR vs. GPT)",
         "Older hard drives use Master Boot Record partitioning where the first partition starts at sector 2048. "
         "Modern drives use GUID Partition Table partitioning where the main data partition often begins at sector 65664. "
         "Always check the output of mmls to find the exact starting sector before running fls or icat."),
        ("3. Deleted Directory Entries vs. Total Recovered Files",
         "Students may notice that fls lists 839 deleted directory entries, while tsk_recover extracts 3,982 files. "
         "Both numbers are correct. The listing command only counts deleted file names listed in folder directories. "
         "The recovery tool extracts every recoverable data cluster across the entire drive, including unlinked file fragments."),
        ("4. False Alarms on Benign Plain-Text Files",
         "Our file disguise detector checks magic bytes (the hidden signature at the start of a file). "
         "It flags any file whose contents look like plain text if its extension is not .txt or .log. "
         "Files like web shortcuts and software manifests are actually plain text, so they trigger a warning. "
         "Students should examine the file contents to confirm whether it is a real disguise or a normal system file."),
        ("5. Antivirus File Locking",
         "If an evidence image contains simulated attack scripts or malware tests, your antivirus may try to lock or delete them. "
         "Make sure to apply the folder exclusion command before running tests."),
        ("6. Memory Management for Large Forensic Images",
         "When calculating file fingerprints on multi-gigabyte forensic images, reading the entire file into RAM at once will cause system memory exhaustion. "
         "Our analyzer reads files in streaming 64-kilobyte buffers. "
         "This streaming design keeps system memory usage below 50 megabytes regardless of how large the evidence disk image is."),
        ("7. Handling Damaged or Corrupted File Systems",
         "In real-world incidents, suspect storage drives may have damaged partition headers or corrupted file system tables. "
         "When mmls or fls encounters unreadable sectors, our tool catches the error, records the failure in the actions log, and continues analyzing the remaining readable partitions.")
    ]

    for title, desc in issues:
        add_heading_3(doc, title)
        p = doc.add_paragraph(desc)
        p.paragraph_format.space_after = Pt(3)

    # Section 8: Checklist
    add_heading_1(doc, "8. Pre-Flight Verification Checklist")
    doc.add_paragraph(
        "Use this final checklist to make sure your lab computer is completely ready for student use."
    )

    headers_chk = ["Verification Item", "Verification Command or Action", "Status"]
    rows_chk = [
        ["Python 3.10+ Installed", "Run: python --version (verify output is 3.10 or higher)", "[  ] READY"],
        ["Sleuth Kit Binaries Present", "Verify mmls and fls commands run in PowerShell", "[  ] READY"],
        ["Autopsy Installed", "Verify Autopsy executable starts on your computer", "[  ] READY"],
        ["Perl Installed", "Run: perl -v (or verify Python timeline fallback)", "[  ] READY"],
        ["Python Packages Installed", "Run: pip install -r requirements.txt", "[  ] READY"],
        ["Antivirus Exclusion Applied", "Exclude your project and case folders in antivirus settings", "[  ] READY"],
        ["Practice Image Present", "Verify practice_evidence.dd is in your project files", "[  ] READY"],
        ["Pipeline Unit Test Passes", "Run: python test_pipeline.py (must report ALL TESTS PASSED)", "[  ] READY"],
        ["Web Endpoints Test Passes", "Run: python test_web_endpoints.py (all routes return success)", "[  ] READY"],
        ["Flask App Starts Cleanly", "Run: python app.py and open the tool page in your browser", "[  ] READY"],
        ["HTML Report Generated", "Verify report.html is created in your case deliverables folder", "[  ] READY"],
        ["PDF Report Compiled", "Verify report.pdf opens cleanly in a standard PDF viewer", "[  ] READY"],
        ["ZIP Archive Assembled", "Verify case_package.zip contains all case reports and artifacts", "[  ] READY"],
        ["Timeline CSV Produced", "Verify timeline.csv opens cleanly in a spreadsheet viewer", "[  ] READY"],
        ["Extracted Strings Indexed", "Verify strings_ascii.txt contains indexed readable words", "[  ] READY"]
    ]
    add_clean_table(doc, headers_chk, rows_chk, [2.0, 3.7, 1.0])

    p_end = doc.add_paragraph()
    p_end.paragraph_format.space_before = Pt(14)
    r_end = p_end.add_run("The full code is in the project files provided by your instructor.")
    r_end.font.bold = True
    r_end.font.size = Pt(11)
    r_end.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)

    return doc


# ==============================================================================
# DOCUMENT 2: PROJECT STUDENT GUIDE (6 to 8 pages)
# ==============================================================================
def build_document_2():
    doc = docx.Document()
    setup_doc_layout(doc, margin_in=0.75)
    setup_header_and_footer(doc, "BCSSL Lab 14 | Student Lab Guide", "2_Project_Student_Guide")

    add_title_block(
        doc,
        title="Document 2: Project Student Guide",
        subtitle="Beginner hands-on lab manual for digital forensics investigation and automated analysis",
        audience="Student Lab Manual",
        case_id="CASE-TEST-014"
    )

    # Section 1: What You Will Learn
    add_heading_1(doc, "1. What You Will Learn")
    doc.add_paragraph(
        "Welcome to your first digital forensics lab! Digital forensics is the science of finding clues on computers "
        "and storage drives. In this lab, you will step into the shoes of a cyber investigator solving Case CASE-TEST-014. "
        "By the end of this lab, you will know how to:"
    )
    learn_points = [
        "Safely copy and protect digital evidence without altering a single byte of data.",
        "Calculate cryptographic file fingerprints to prove evidence has not been changed.",
        "Find and recover deleted files using The Sleuth Kit command-line tools.",
        "Explore an evidence drive visually using the Autopsy graphical forensic tool.",
        "Run an automated web tool that executes nine forensic phases and creates a structured forensic report."
    ]
    for pt in learn_points:
        p_pt = doc.add_paragraph()
        p_pt.paragraph_format.left_indent = Inches(0.25)
        p_pt.paragraph_format.space_after = Pt(2)
        r_bullet = p_pt.add_run("•  ")
        r_bullet.bold = True
        r_bullet.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)
        p_pt.add_run(pt)

    add_callout(
        doc,
        "You do not need any prior forensics experience. Every step is clearly explained with simple examples and commands.",
        title="WELCOME BEGINNERS",
        callout_type="info"
    )

    # Section 2: Big Picture
    add_heading_1(doc, "2. The Big Picture: How an Investigation Works")
    doc.add_paragraph(
        "Every digital forensics investigation follows a strict, orderly path. "
        "We never examine original evidence directly. Instead, we protect the original, make an exact copy, "
        "and perform all our tests on the copy. Here is the big picture from start to finish:"
    )

    diag_big = (
        "[ 1. Disk Image ]  -->  [ 2. Upload ]  -->  [ 3. Protect & Fingerprint ]\n"
        " (Exact photocopy)       (Send to tool)       (Lock & fingerprint)\n"
        "                                                          |\n"
        "                                                          v\n"
        "[ 6. Report & ZIP ] <--  [ 5. Timeline ]   <--  [ 4. Recover Files ]\n"
        " (Final evidence)        (Chronological log)   (Extract deleted data)"
    )
    add_code_box(doc, diag_big)

    doc.add_paragraph(
        "First, we take a disk image (a complete digital copy of the suspect drive). "
        "Next, we upload it and lock it so nobody can change it. "
        "Then, we calculate digital fingerprints to prove it is authentic. "
        "After that, we search for hidden or deleted files and build a timeline of events. "
        "Finally, we gather all our facts into a structured forensic report."
    )

    # Section 3: Words You Need to Know
    add_heading_1(doc, "3. Words You Need to Know (Forensic Glossary)")
    doc.add_paragraph(
        "Forensic examiners use specialized terms. Here are the 10 most important words you will meet in this lab, "
        "explained with simple everyday examples:"
    )

    headers_words = ["Forensic Term", "Simple Explanation", "Everyday Life Example"]
    rows_words = [
        ["Disk Image", "An exact bit-for-bit copy of an entire storage drive.", "Like a complete photocopy of a diary, including all blank pages."],
        ["File Fingerprint", "A unique mathematical signature generated from file contents.", "Like a human fingerprint; if even one letter changes, the fingerprint changes completely."],
        ["Read-Only Protection", "Locking a file so its contents cannot be modified or erased.", "Like putting an important document inside a locked glass display case."],
        ["Partition", "Dividing a single physical hard drive into separate logical storage sections.", "Like putting up dividing walls inside a large warehouse to make separate rooms."],
        ["Sector", "The smallest addressable chunk of storage on a disk (usually 512 bytes).", "Like an individual numbered parking space painted in a large parking lot."],
        ["File System", "The organized index the operating system uses to track file locations.", "Like a library catalog that records the shelf number for every book in the library."],
        ["Inode / Metadata", "A catalog record storing a file's size, creation dates, and sector pointers.", "Like a library book card showing the author, publish date, and call number."],
        ["Deleting a File", "Removing the file's catalog entry while leaving its actual data on disk.", "Like removing a book's card from the catalog while the book stays on the shelf."],
        ["Recovery", "Using file system metadata and cluster pointers to restore deleted files.", "Like using a librarian's checkout log to find a book that lost its index card."],
        ["Timeline (MACB)", "A chronological schedule showing when files were Modified, Accessed, Changed, or Born.", "Like a building security guard's logbook recording when someone entered a room."]
    ]
    add_clean_table(doc, headers_words, rows_words, [1.5, 2.6, 2.6])

    # Section 4: Step 1 Protect the Evidence
    add_heading_1(doc, "4. Step 1: Protect the Evidence")
    doc.add_paragraph(
        "In forensics, evidence integrity is the number one rule. "
        "If you accidentally change even one letter in an evidence file, your findings may be rejected. "
        "We protect evidence by making a working copy, applying read-only protection, and calculating its file fingerprint."
    )

    add_heading_2(doc, "Hands-On Step 1A: Copy the Practice Evidence Image")
    doc.add_paragraph("What to do: Open Windows PowerShell and copy the practice evidence file to your working folder.")
    add_code_box(doc, 'Copy-Item "<image-file>" "<working-copy>"')
    doc.add_paragraph("What you should see: PowerShell runs silently and creates the duplicate file in your chosen working folder.")

    add_heading_2(doc, "Hands-On Step 1B: Apply Read-Only Protection")
    doc.add_paragraph("What to do: Set the software read-only attribute on the file so Windows prevents accidental changes.")
    add_code_box(doc, 'Set-ItemProperty "<working-copy>" -Name IsReadOnly -Value $true')
    doc.add_paragraph("What you should see: Verify the read-only attribute by checking its property in PowerShell:")
    add_code_box(doc, '(Get-Item "<working-copy>").IsReadOnly\n# Output should be: True')

    add_heading_2(doc, "Hands-On Step 1c - Calculate the File Fingerprint")
    doc.add_paragraph("What to do: Calculate the cryptographic fingerprint of your working copy using PowerShell's built-in command.")
    add_code_box(doc, 'Get-FileHash "<working-copy>"')
    doc.add_paragraph("What you should see: A table displaying the calculated algorithm and fingerprint string. Save a screenshot for your worksheet!")

    doc.add_paragraph(
        "Why this matters: If a single byte in the file is modified, the fingerprint changes completely. "
        "This property is called the avalanche effect. Comparing pre-analysis and post-analysis fingerprints proves in an investigation "
        "that the evidence was never altered during examination."
    )

    # Section 5: Step 2 Find and Recover Deleted Files with The Sleuth Kit
    add_heading_1(doc, "5. Step 2: Find and Recover Deleted Files with The Sleuth Kit")
    doc.add_paragraph(
        "The Sleuth Kit is a collection of command-line tools that let you see deep inside a disk image. "
        "We will use four Sleuth Kit tools: mmls, fls, icat, and tsk_recover."
    )

    add_heading_2(doc, "Hands-On Step 2A: Inspect Partitions with mmls")
    doc.add_paragraph(
        "What to do: Run mmls to see how the disk is divided into sections. "
        "In digital forensics, disk drives are divided into sectors of 512 bytes each. "
        "To find the byte offset of a partition, you multiply its starting sector by 512."
    )
    add_code_box(doc, "mmls <image-file>")
    doc.add_paragraph("What you should see: A table listing partition slots and start sectors. If the image is a floppy disk without partitions, it will report 'Cannot determine partition type', meaning the file system starts at sector 0.")

    add_heading_2(doc, "Hands-On Step 2B: List Files and Find Deleted Items with fls")
    doc.add_paragraph(
        "What to do: Run fls to view all files. The flags mean: -r searches recursively into all subfolders, "
        "and -p shows the full path of each file. In Windows PowerShell, use Select-Object -First 50 instead of the Linux head command."
    )
    add_code_box(doc, "fls -r -p <image-file> | Select-Object -First 50")
    doc.add_paragraph("What you should see: A list of directory entries. Deleted files are marked with an asterisk (*) and an inode catalog number.")

    add_heading_2(doc, "Hands-On Step 2c - Recover a Specific File with icat")
    doc.add_paragraph(
        "What to do: Extract the contents of a specific deleted inode number. "
        "Use cmd /c with quotation marks so Windows handles file redirection properly without altering file bytes."
    )
    add_code_box(doc, 'cmd /c "icat <image-file> <inode-number> > <output-file>"')
    doc.add_paragraph("What you should see: Open your output file in Notepad. You will see the recovered secret message text!")

    add_heading_2(doc, "Hands-On Step 2d - Recover All Deleted Files with tsk_recover")
    doc.add_paragraph(
        "What to do: Automatically extract every deleted file into a target folder using tsk_recover with the -e flag."
    )
    add_code_box(doc, "tsk_recover -e <image-file> <output-folder>")
    doc.add_paragraph("What you should see: The tool outputs a summary message reporting the number of files recovered (for example: Files Recovered: 12).")

    add_callout(
        doc,
        "Recovery vs. Carving: tsk_recover uses file system metadata (catalog entries) to find where deleted files were stored. "
        "This is called metadata recovery. Signature carving, by contrast, scans raw unallocated sectors for file headers (like PNG or PDF signatures) "
        "when catalog records are completely lost.",
        title="FORENSIC CONCEPT",
        callout_type="info"
    )

    # Section 6: Step 3 Look at It in Autopsy
    add_heading_1(doc, "6. Step 3: Look at It in Autopsy")
    doc.add_paragraph(
        "Autopsy is a graphical user interface tool that sits on top of The Sleuth Kit. "
        "It lets you explore evidence visually with buttons and trees instead of typing terminal commands."
    )

    steps_autopsy = [
        ("Step 3.1: Open Autopsy", "Launch Autopsy from your applications menu or desktop shortcut."),
        ("Step 3.2: Create a New Case", "Click the 'Create New Case' button. Name the case CASE-TEST-014. Choose a base folder and click Next, then Finish."),
        ("Step 3.3: Add the Data Source", "In the Add Data Source wizard, select 'Disk Image or VM File' and click Next. Select your practice evidence image file."),
        ("Step 3.4: Configure Ingest Modules", "Keep the default ingest modules selected (File Type Identification and Keyword Search). Click Next, then Finish."),
        ("Step 3.5: Explore Deleted Files", "In the left-hand navigation tree, expand 'File Views' and click 'Deleted Files'. You will see all deleted files listed in a table with a red mark."),
        ("Step 3.6: Inspect Hex and Text Views", "Click on any deleted file in the table. In the bottom viewer window, switch between 'Hex' and 'Strings' tabs. Notice the raw bytes on the left and readable text characters on the right.")
    ]
    for stitle, sdesc in steps_autopsy:
        add_heading_3(doc, stitle)
        p_st = doc.add_paragraph(sdesc)
        p_st.paragraph_format.space_after = Pt(2)

    add_callout(
        doc,
        "Notice how long Autopsy took to start up! Autopsy is a large Java application that initializes many modules. "
        "In our automated web tool, if Autopsy takes longer than 25 seconds, the tool automatically switches to The Sleuth Kit CLI. "
        "This ensures the automated pipeline never hangs.",
        title="AUTOMATION NOTE",
        callout_type="warning"
    )

    # Section 7: Step 4 Run the Digital Forensics Analyzer Tool
    add_heading_1(doc, "7. Step 4: Run the Digital Forensics Analyzer Tool")
    doc.add_paragraph(
        "Now that you understand the manual commands, you are ready to see how the automated tool does everything in seconds! "
        "The Digital Forensics Analyzer runs all nine forensic phases automatically."
    )

    steps_tool = [
        ("Step 4.1: Verify the Web Server is Running",
         "Make sure the instructor or developer has started the server. If not, open PowerShell in your project folder and run:",
         "python app.py"),
        ("Step 4.2: Open the Web Dashboard",
         "Open your web browser (Chrome, Edge, or Firefox) and navigate to the tool's local page (your instructor will tell you how).",
         "# Open the web page in your browser as instructed"),
        ("Step 4.3: Enter Case Details and Select Evidence",
         "On the upload page, enter Case Number: CASE-TEST-014, Examiner: your name, and click 'Choose File' to select practice_evidence.dd.",
         "# Complete the web intake form"),
        ("Step 4.4: Click Start Analysis",
         "Click the green 'Start Analysis' button. The tool begins executing the 9-phase forensic pipeline in the background.",
         "# Click 'Start Analysis' to begin")
    ]
    for stitle, sdesc, scmd in steps_tool:
        add_heading_3(doc, stitle)
        p = doc.add_paragraph(sdesc)
        p.paragraph_format.space_after = Pt(2)
        add_code_box(doc, scmd)

    p7_bg = doc.add_paragraph("What the Tool Does Behind the Scenes When You Click Start:")
    p7_bg.runs[0].font.bold = True
    bg_phases = [
        "Phase 1: Locks the evidence as read-only and makes a working copy in your case folder.",
        "Phase 2: Computes baseline file fingerprints to establish initial integrity.",
        "Phase 3: Scans the partition table to find where files begin.",
        "Phase 4: Enumerates active and deleted files into a bodyfile index.",
        "Phase 5: Automatically extracts all deleted files into the recovered files folder.",
        "Phase 6: Extracts readable text strings and notes their exact byte offsets.",
        "Phase 7: Builds a chronological activity timeline spreadsheet.",
        "Phase 8: Scans for disguised files (magic byte mismatches) and checks keywords.",
        "Phase 9: Compiles the structured forensic report (HTML & PDF) and builds the ZIP package."
    ]
    for bp in bg_phases:
        p_bp = doc.add_paragraph()
        p_bp.paragraph_format.left_indent = Inches(0.2)
        p_bp.paragraph_format.space_after = Pt(1.5)
        p_bp.add_run("• " + bp)

    add_heading_2(doc, "How to Read the Structured Forensic Report")
    doc.add_paragraph(
        "Once the tool completes the analysis, click 'View Structured Report'. "
        "The report is organized into five easy-to-read sections:"
    )
    headers_rep = ["Report Section", "What It Shows", "What You Should Look For"]
    rows_rep = [
        ["Executive Summary", "Case number, examiner name, and job timestamp.", "Confirm your name and case CASE-TEST-014 appear correctly."],
        ["Evidence Integrity", "Pre-analysis and post-analysis cryptographic fingerprints.", "Verify that the integrity status reports PASS."],
        ["Recovered Files Table", "List of all 12 deleted files restored by The Sleuth Kit.", "Check file names, sizes, and file extension statuses."],
        ["Disguised Files Alert", "Files whose internal magic bytes do not match their file extension.", "Look for _ISGUISE.TXT flagged with an image signature."],
        ["Timeline Analysis", "Chronological table of file activity timestamps.", "Identify the exact date and time the deleted files were created."]
    ]
    add_clean_table(doc, headers_rep, rows_rep, [1.8, 2.5, 2.4])

    # Section 8: What to Hand In
    add_heading_1(doc, "8. What to Hand In")
    doc.add_paragraph(
        "At the end of the lab, assemble your work into a single submission folder and hand it in to your instructor. "
        "Use this checklist to ensure you have included everything:"
    )

    headers_sub = ["Submission Item", "File Name or Description", "Required Check"]
    rows_sub = [
        ["Student Worksheet", "3_Project_Student_Worksheet.docx (completed with your answers)", "[  ] READY"],
        ["Structured Forensic Report", "report.pdf (downloaded from the web dashboard)", "[  ] READY"],
        ["Case Deliverables Archive", "case_package.zip (downloaded from the web dashboard)", "[  ] READY"],
        ["PowerShell Fingerprint Screenshot", "Screenshot showing Get-FileHash command and output", "[  ] READY"],
        ["Autopsy Deleted Files Screenshot", "Screenshot of Autopsy GUI showing the Deleted Files tree", "[  ] READY"]
    ]
    add_clean_table(doc, headers_sub, rows_sub, [2.0, 3.8, 1.0])

    # Section 9: If Something Goes Wrong (5 Common Problems and Fixes)
    add_heading_1(doc, "9. If Something Goes Wrong (Troubleshooting Guide)")
    doc.add_paragraph(
        "Don't panic if you hit an error! Forensics work involves many tools and system security settings. "
        "Here are the five most common issues and how to fix them:"
    )

    troubles = [
        ("Problem 1: PowerShell says 'running scripts is disabled on this system'",
         "Cause: Windows has a security policy that prevents unsigned scripts from running by default.",
         "Fix: Run this command in PowerShell to bypass the restriction for your current session:",
         "Set-ExecutionPolicy -Scope Process Bypass"),
        ("Problem 2: PowerShell does not recognize the 'head' command",
         "Cause: 'head' is a Linux command. Windows PowerShell does not have a head command.",
         "Fix: Pipe your output into Select-Object -First 50 instead:",
         "fls -r -p <image-file> | Select-Object -First 50"),
        ("Problem 3: The file created by icat is empty or has strange corrupted characters",
         "Cause: PowerShell text redirection modifies binary encoding and adds extra characters.",
         "Fix: Wrap the command in cmd /c so the standard Windows command prompt handles the redirection:",
         'cmd /c "icat <image-file> <inode> > <output-file>"'),
        ("Problem 4: Your antivirus suddenly pops up and deletes your recovered files",
         "Cause: Antivirus scanners detect test strings or simulated malware inside recovered forensic files.",
         "Fix: Open PowerShell as Administrator and add an exclusion for your case folder:",
         'Add-MpPreference -ExclusionPath "<your-case-folder>"'),
        ("Problem 5: Autopsy takes forever to start or the web tool says 'Autopsy timed out'",
         "Cause: Autopsy is a large Java application that takes over 25 seconds to start up on Windows.",
         "Fix: This is completely normal! The automated tool is designed to stop waiting after 25 seconds and automatically use The Sleuth Kit instead. Your results are 100% complete and accurate.",
         "# No action needed! The tool switches to The Sleuth Kit automatically.")
    ]

    for title, cause, fix_desc, cmd in troubles:
        add_heading_3(doc, title)
        p_c = doc.add_paragraph(cause)
        p_c.paragraph_format.space_after = Pt(1)
        p_f = doc.add_paragraph(fix_desc)
        p_f.paragraph_format.space_after = Pt(2)
        add_code_box(doc, cmd)

    return doc


# ==============================================================================
# DOCUMENT 3: STUDENT WORKSHEET (3 to 4 pages)
# ==============================================================================
def build_document_3():
    doc = docx.Document()
    setup_doc_layout(doc, margin_in=0.7)
    setup_header_and_footer(doc, "BCSSL Lab 14 | Student Worksheet", "3_Project_Student_Worksheet")

    add_title_block(
        doc,
        title="Document 3: Student Assessment Worksheet",
        subtitle="Individual lab evaluation covering forensic concepts, hands-on findings, and scenarios",
        audience="Student Worksheet",
        case_id="CASE-TEST-014"
    )

    headers_id = ["Student Name", "Student ID Number", "Lab Section / Date", "Final Score"]
    rows_id = [
        ["________________________", "____________________", "Section: _______  Date: ________", "[          / 40 Marks ]"]
    ]
    add_clean_table(doc, headers_id, rows_id, [2.2, 1.8, 2.0, 1.3])
    doc.add_paragraph()

    # Part A: Concepts
    add_heading_1(doc, "Part A: Forensic Concepts (20 Marks Total - 2 Marks Each)")
    doc.add_paragraph(
        "Answer each question in the space provided. All questions can be answered from Document 2 (Student Guide)."
    )

    # Q1
    add_heading_3(doc, "Question 1 (2 Marks)")
    doc.add_paragraph("What is a file fingerprint (hash), and what everyday item is it compared to in digital forensics?")
    add_answer_box(doc, height_lines=2)

    # Q2
    add_heading_3(doc, "Question 2 (2 Marks)")
    doc.add_paragraph("Multiple Choice: When you delete a file on a computer, what actually happens to the data on the disk?")
    mc_q2 = [
        "[   ] A. The file data is erased and shredded immediately.",
        "[   ] B. The file's catalog entry is removed, but the data stays on disk until overwritten.",
        "[   ] C. The computer renames the file to secret.exe automatically.",
        "[   ] D. The file is uploaded to the cloud."
    ]
    for opt in mc_q2:
        p = doc.add_paragraph(opt)
        p.paragraph_format.left_indent = Inches(0.2)
        p.paragraph_format.space_after = Pt(1)

    # Q3
    add_heading_3(doc, "Question 3 (2 Marks)")
    doc.add_paragraph("Why do forensic examiners apply 'read-only protection' to evidence images before starting their analysis?")
    add_answer_box(doc, height_lines=2)

    # Q4
    add_heading_3(doc, "Question 4 (2 Marks)")
    doc.add_paragraph("Multiple Choice: What does a forensic 'disk image' contain?")
    mc_q4 = [
        "[   ] A. Pictures, wallpapers, and photos stored on the desktop.",
        "[   ] B. An exact bit-for-bit photocopy of the whole drive, including deleted space.",
        "[   ] C. Only the files currently sitting inside the Recycle Bin.",
        "[   ] D. The Windows operating system installation files only."
    ]
    for opt in mc_q4:
        p = doc.add_paragraph(opt)
        p.paragraph_format.left_indent = Inches(0.2)
        p.paragraph_format.space_after = Pt(1)

    # Q5
    add_heading_3(doc, "Question 5 (2 Marks)")
    doc.add_paragraph("In The Sleuth Kit, which command lists all directory entries and marks deleted files with an asterisk (*)?")
    add_answer_box(doc, height_lines=2)

    # Q6
    add_heading_3(doc, "Question 6 (2 Marks)")
    doc.add_paragraph("Multiple Choice: If you need to recover file contents directly from a specific inode number, which tool do you use?")
    mc_q6 = [
        "[   ] A. mmls",
        "[   ] B. fsstat",
        "[   ] C. icat",
        "[   ] D. srch_strings"
    ]
    for opt in mc_q6:
        p = doc.add_paragraph(opt)
        p.paragraph_format.left_indent = Inches(0.2)
        p.paragraph_format.space_after = Pt(1)

    # Q7
    add_heading_3(doc, "Question 7 (2 Marks)")
    doc.add_paragraph("What four file timestamps does a forensic 'MACB' timeline track? Write out the meaning of M, A, C, and B.")
    add_answer_box(doc, height_lines=2)

    # Q8
    add_heading_3(doc, "Question 8 (2 Marks)")
    doc.add_paragraph("Why does the Digital Forensics Analyzer try Autopsy first, and what does it do if Autopsy takes longer than 25 seconds?")
    add_answer_box(doc, height_lines=2)

    # Q9
    add_heading_3(doc, "Question 9 (2 Marks)")
    doc.add_paragraph("Multiple Choice: In Windows PowerShell, what command should you use instead of the Linux 'head -n 50' command?")
    mc_q9 = [
        "[   ] A. Get-Head -Count 50",
        "[   ] B. Select-Object -First 50",
        "[   ] C. Limit-Output 50",
        "[   ] D. Take-First 50"
    ]
    for opt in mc_q9:
        p = doc.add_paragraph(opt)
        p.paragraph_format.left_indent = Inches(0.2)
        p.paragraph_format.space_after = Pt(1)

    # Q10
    add_heading_3(doc, "Question 10 (2 Marks)")
    doc.add_paragraph("Why must you use 'cmd /c \"icat ... > file\"' when extracting files on Windows instead of a standard PowerShell redirect?")
    add_answer_box(doc, height_lines=2)

    # Part B: Hands-On Evidence Questions
    add_heading_1(doc, "Part B: Hands-On Evidence Findings (10 Marks Total - 2 Marks Each)")
    doc.add_paragraph(
        "Fill in the findings from your hands-on examination of the practice evidence and the web tool output:"
    )

    # Q11
    add_heading_3(doc, "Question 11 (2 Marks)")
    doc.add_paragraph("Did your file fingerprint calculated before analysis match the fingerprint calculated after analysis? (Attach your screenshot).")
    add_answer_box(doc, height_lines=2)

    # Q12
    add_heading_3(doc, "Question 12 (2 Marks)")
    doc.add_paragraph("Did the file fingerprint of the original evidence match the working copy before analysis? What does this prove?")
    add_answer_box(doc, height_lines=2)

    # Q13
    add_heading_3(doc, "Question 13 (2 Marks)")
    doc.add_paragraph("How many total files were extracted into the recovered files folder during Phase 5 file recovery?")
    add_answer_box(doc, height_lines=2)

    # Q14
    add_heading_3(doc, "Question 14 (2 Marks)")
    doc.add_paragraph("Name one file flagged for an 'extension mismatch' (disguised file), and state what kind of file it really was.")
    add_answer_box(doc, height_lines=2)

    # Q15
    add_heading_3(doc, "Question 15 (2 Marks)")
    doc.add_paragraph("Did the final post-analysis integrity check report PASS or FAIL? Explain what this result means for your evidence.")
    add_answer_box(doc, height_lines=2)

    # Part C: Scenarios
    add_heading_1(doc, "Part C - Forensic Scenarios (10 Marks Total - 5 Marks Each)")
    doc.add_paragraph(
        "Read each realistic scenario carefully and answer the questions using the forensic principles learned in this lab."
    )

    # Scenario 1
    add_heading_2(doc, "Scenario 1: The Careless Investigator (5 Marks)")
    doc.add_paragraph(
        "Detective Alex arrives at an office to investigate data theft. Alex finds a suspect USB drive, plugs it directly "
        "into an office laptop, opens three Microsoft Word documents to read them, and then takes a file fingerprint. "
        "In court, the defense attorney argues that the USB evidence was contaminated and cannot be trusted."
    )
    doc.add_paragraph("a) Did Alex contaminate the evidence? Explain what changes Windows made when the files were opened. (2 Marks)")
    add_answer_box(doc, height_lines=2)
    doc.add_paragraph("b) What two things should Alex have done instead before looking at any files on the USB drive? (3 Marks)")
    add_answer_box(doc, height_lines=2)

    # Scenario 2
    add_heading_2(doc, "Scenario 2: The Deleted Spreadsheet (5 Marks)")
    doc.add_paragraph(
        "An employee suspecting an internal audit deletes a sensitive spreadsheet named 'confidential_salaries.xlsx' "
        "and empties the Recycle Bin at 4:30 PM. At 4:45 PM, the forensics team seizes the computer and takes a bitstream disk image."
    )
    doc.add_paragraph("a) Why is the forensic team able to recover the spreadsheet even though the Recycle Bin was emptied? (2 Marks)")
    add_answer_box(doc, height_lines=2)
    doc.add_paragraph("b) What could have caused the spreadsheet data to become permanently unrecoverable if the PC was left running? (1 Mark)")
    add_answer_box(doc, height_lines=2)
    doc.add_paragraph("c) Which two Sleuth Kit tools from this lab could the analyst use to find the file's inode and extract its data? (2 Marks)")
    add_answer_box(doc, height_lines=2)

    return doc


# ==============================================================================
# DOCUMENT 4: STUDENT WORKSHEET SOLUTIONS (3 to 4 pages)
# ==============================================================================
def build_document_4():
    doc = docx.Document()
    setup_doc_layout(doc, margin_in=0.7)
    setup_header_and_footer(doc, "BCSSL Lab 14 | Instructor Solutions Key", "4_Project_Student_Worksheet_Solutions")

    add_title_block(
        doc,
        title="Document 4: Student Worksheet Solutions",
        subtitle="Complete instructor grading key, marking criteria, and empirical reference values",
        audience="Instructor Only - Grading Key",
        case_id="CASE-TEST-014"
    )

    add_heading_2(doc, "Assessment Score Summary Table")
    headers_sum = ["Worksheet Section", "Question Numbers", "Evaluation Focus", "Available Marks"]
    rows_sum = [
        ["Part A: Forensic Concepts", "Questions 1 to 10", "Core digital forensics concepts and tools", "20 Marks (10 x 2m)"],
        ["Part B: Hands-On Evidence", "Questions 11 to 15", "Empirical findings from practice evidence", "10 Marks (5 x 2m)"],
        ["Part C - Forensic Scenarios", "Scenarios 1 and 2", "Applied reasoning and investigative procedure", "10 Marks (2 x 5m)"],
        ["Total Evaluation", "All Questions", "BCSSL Lab 14 Final Grade", "40 Marks Total"]
    ]
    add_clean_table(doc, headers_sum, rows_sum, [2.2, 1.6, 2.3, 1.4])
    doc.add_paragraph()

    # Part A Solutions
    add_heading_1(doc, "Part A: Forensic Concepts Solutions (20 Marks Total)")

    solutions_a = [
        ("Question 1 (2 Marks)",
         "Model Answer: A file fingerprint (hash) is a unique mathematical string generated from a file's contents. In digital forensics, it is compared to a human fingerprint because even a single altered byte completely changes the fingerprint.",
         "Marking Criteria: [1 mark] for defining hash as a unique file fingerprint; [1 mark] for mentioning the human fingerprint comparison or stating that changing one byte changes the fingerprint."),

        ("Question 2 (2 Marks)",
         "Model Answer: B. The file's catalog entry is removed, but the data stays on disk until overwritten.",
         "Marking Criteria: [2 marks] for option B. [0 marks] for any other option."),

        ("Question 3 (2 Marks)",
         "Model Answer: Examiners apply read-only protection to prevent accidental changes, overwrites, or file deletion, ensuring the original evidence remains pure and unmodified.",
         "Marking Criteria: [1 mark] for preventing accidental modification or tampering; [1 mark] for stating that evidence must remain unaltered for investigation validity."),

        ("Question 4 (2 Marks)",
         "Model Answer: B. An exact bit-for-bit photocopy of the whole drive, including deleted space.",
         "Marking Criteria: [2 marks] for option B. [0 marks] for any other option."),

        ("Question 5 (2 Marks)",
         "Model Answer: The fls tool lists directory entries and marks deleted files with an asterisk (*).",
         "Marking Criteria: [2 marks] for identifying fls. Award 1 mark if student mentions The Sleuth Kit generally."),

        ("Question 6 (2 Marks)",
         "Model Answer: C. icat",
         "Marking Criteria: [2 marks] for option C (icat). [0 marks] for any other option."),

        ("Question 7 (2 Marks)",
         "Model Answer: M = Modified time (content changed); A = Accessed time (file opened or read); C = Changed time (metadata or permissions changed); B = Birth time (file created).",
         "Marking Criteria: [0.5 marks] for each correctly identified letter (Modified, Accessed, Changed, Birth/Created)."),

        ("Question 8 (2 Marks)",
         "Model Answer: The tool tries Autopsy first because of its rich analysis features. If Autopsy takes longer than 25 seconds, the tool automatically falls back to The Sleuth Kit CLI so the automated run never hangs.",
         "Marking Criteria: [1 mark] for noting Autopsy's rich features or graphical engine; [1 mark] for stating that the 25-second timeout triggers an automatic fallback to The Sleuth Kit."),

        ("Question 9 (2 Marks)",
         "Model Answer: B. Select-Object -First 50",
         "Marking Criteria: [2 marks] for option B. [0 marks] for any other option."),

        ("Question 10 (2 Marks)",
         "Model Answer: Standard PowerShell output redirection treats data as text, altering binary byte encoding. Using cmd /c ensures exact, raw binary data redirection without corruption.",
         "Marking Criteria: [1 mark] for identifying PowerShell's text encoding or corruption behavior; [1 mark] for stating that cmd /c preserves raw binary data.")
    ]

    for q_title, q_ans, q_rub in solutions_a:
        add_heading_3(doc, q_title)
        p_ans = doc.add_paragraph()
        r1 = p_ans.add_run(q_ans)
        r1.font.size = Pt(10)
        p_rub = doc.add_paragraph()
        r2 = p_rub.add_run(q_rub)
        r2.font.size = Pt(9.5)
        r2.font.italic = True
        r2.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)
        p_rub.paragraph_format.space_after = Pt(3)

    # Part B Solutions
    add_heading_1(doc, "Part B: Hands-On Evidence Findings Solutions (10 Marks Total)")

    solutions_b = [
        ("Question 11 (2 Marks)",
         "Model Answer: Accept the value from the student's own screenshot, as long as the pre-analysis and post-analysis values match.",
         "Marking Criteria: [2 marks] for confirming pre-analysis and post-analysis fingerprints match and providing a valid screenshot."),

        ("Question 12 (2 Marks)",
         "Model Answer: Yes, the fingerprints matched 100%. This proves that the working copy is an exact, bit-for-bit identical duplicate of the original evidence image.",
         "Marking Criteria: [1 mark] for stating 'Yes, they matched'; [1 mark] for explaining that matching fingerprints prove the copy is an exact duplicate."),

        ("Question 13 (2 Marks)",
         "Model Answer: Exactly 12 files were recovered into the recovered files folder.",
         "Marking Criteria: [2 marks] for stating 12 files. (Award 1 mark if student wrote between 10 and 14 with documented recovery list)."),

        ("Question 14 (2 Marks)",
         "Model Answer: _ISGUISE.TXT (or DISGUISE.TXT). Although it has a text extension, its internal magic bytes correspond to a PNG image file.",
         "Marking Criteria: [1 mark] for naming _ISGUISE.TXT or DISGUISE.TXT; [1 mark] for identifying that it is actually a PNG image file."),

        ("Question 15 (2 Marks)",
         "Model Answer: PASS. This result proves that the forensic analysis engine did not modify, alter, or contaminate the working evidence disk image during all nine phases.",
         "Marking Criteria: [1 mark] for stating PASS; [1 mark] for explaining that it proves the evidence was not modified during the investigation.")
    ]

    for q_title, q_ans, q_rub in solutions_b:
        add_heading_3(doc, q_title)
        p_ans = doc.add_paragraph()
        r1 = p_ans.add_run(q_ans)
        r1.font.size = Pt(10)
        p_rub = doc.add_paragraph()
        r2 = p_rub.add_run(q_rub)
        r2.font.size = Pt(9.5)
        r2.font.italic = True
        r2.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)
        p_rub.paragraph_format.space_after = Pt(3)

    # Part C Solutions
    add_heading_1(doc, "Part C - Forensic Scenarios Solutions (10 Marks Total)")

    add_heading_2(doc, "Scenario 1: The Careless Investigator Solutions (5 Marks)")
    sc1_parts = [
        ("Part (a) Evidence Contamination (2 Marks)",
         "Model Answer: Yes, Alex contaminated the evidence. When Alex plugged in the USB and opened the Word documents, Windows automatically updated the 'Last Accessed' (A) timestamps, created temporary hidden lock files, and updated Windows recent document records.",
         "Marking Criteria: [1 mark] for concluding 'Yes, Alex contaminated the evidence'; [1 mark] for identifying specific changes made by Windows (e.g. modified access times or created temp files)."),
        ("Part (b) Proper Forensic Procedure (3 Marks)",
         "Model Answer: Before examining any files, Alex should have: (1) Connected the USB drive through a write-blocker or mounted it with software read-only protection, (2) Calculated an initial cryptographic file fingerprint to establish a baseline, and (3) Created a bitstream disk image and conducted all analysis exclusively on the copy.",
         "Marking Criteria: [1 mark] for using write-blocking or read-only protection; [1 mark] for taking a baseline file fingerprint; [1 mark] for creating a disk image copy to examine instead of original.")
    ]
    for stitle, sans, srub in sc1_parts:
        add_heading_3(doc, stitle)
        p1 = doc.add_paragraph(sans)
        p1.runs[0].font.size = Pt(10)
        p2 = doc.add_paragraph(srub)
        p2.runs[0].font.size = Pt(9.5)
        p2.runs[0].font.italic = True
        p2.runs[0].font.color.rgb = RGBColor(0x25, 0x63, 0xEB)
        p2.paragraph_format.space_after = Pt(2)

    add_heading_2(doc, "Scenario 2: The Deleted Spreadsheet Solutions (5 Marks)")
    sc2_parts = [
        ("Part (a) Why Recovery Was Successful (2 Marks)",
         "Model Answer: Emptying the Recycle Bin only removes the spreadsheet's catalog entry from the file system directory tables and marks its clusters as unallocated. The actual spreadsheet data bytes remained intact on disk sectors because no new files had overwritten them.",
         "Marking Criteria: [1 mark] for stating that deleting only removes catalog pointers; [1 mark] for explaining that actual data clusters remained untouched because they were not overwritten yet."),
        ("Part (b) Permanent Unrecoverability Cause (1 Mark)",
         "Model Answer: If the computer continued running, normal operating system operations (system logs, updates, web browsing, or new saved files) would allocate and overwrite those unallocated sectors with new data.",
         "Marking Criteria: [1 mark] for identifying that new data would overwrite the sectors."),
        ("Part (c) Sleuth Kit Tools Used (2 Marks)",
         "Model Answer: The analyst would use fls to search the file system and identify the spreadsheet's deleted inode number (marked with a *), and then use icat to extract the contents from that inode number to a file.",
         "Marking Criteria: [1 mark] for naming fls (to find the inode); [1 mark] for naming icat (to extract the file data).")
    ]
    for stitle, sans, srub in sc2_parts:
        add_heading_3(doc, stitle)
        p1 = doc.add_paragraph(sans)
        p1.runs[0].font.size = Pt(10)
        p2 = doc.add_paragraph(srub)
        p2.runs[0].font.size = Pt(9.5)
        p2.runs[0].font.italic = True
        p2.runs[0].font.color.rgb = RGBColor(0x25, 0x63, 0xEB)
        p2.paragraph_format.space_after = Pt(2)

    return doc


# ==============================================================================
# MAIN BUILD & AUDIT PIPELINE
# ==============================================================================
def main():
    target_dir = Path(r"D:\PROJECTS\ForensicsAnalyzer\docs")
    target_dir.mkdir(parents=True, exist_ok=True)

    doc_builders = [
        ("1_Project_Building_Guide.docx", build_document_1, (8, 10)),
        ("2_Project_Student_Guide.docx", build_document_2, (6, 8)),
        ("3_Project_Student_Worksheet.docx", build_document_3, (3, 4)),
        ("4_Project_Student_Worksheet_Solutions.docx", build_document_4, (3, 4))
    ]

    print("=== BUILDING & AUDITING ALL 4 DOCUMENTS ===\n")
    
    total_violations = 0
    generated_files = []

    for fname, builder_fn, page_range in doc_builders:
        out_path = target_dir / fname
        doc = builder_fn()
        
        # Run text audit for forbidden terms
        violations = audit_document_text(doc, fname)
        if violations:
            print(f"[!] VIOLATIONS IN {fname}:")
            for v in violations:
                print(f"    - {v}")
            total_violations += len(violations)
        else:
            print(f"[+] {fname}: 0 forbidden terms found! (PASS)")

        doc.save(str(out_path))
        generated_files.append((fname, out_path, page_range))

    if total_violations > 0:
        print(f"\n[ERROR] Found {total_violations} forbidden term violations across documents!")
        sys.exit(1)
    else:
        print("\n[+] All 4 documents passed the forbidden terms check with ZERO violations!\n")
        print("[+] Successfully saved all 4 documents to target directory!")

if __name__ == "__main__":
    main()
