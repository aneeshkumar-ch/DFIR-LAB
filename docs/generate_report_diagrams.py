import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

DOCS_DIR = Path(r"D:\PROJECTS\ForensicsAnalyzer\docs")
IMG_DIR = DOCS_DIR / "images"
IMG_DIR.mkdir(parents=True, exist_ok=True)

def create_rounded_rect(ax, x, y, width, height, corner_radius, facecolor, edgecolor, linewidth=1.5, zorder=2, alpha=1.0):
    box = patches.FancyBboxPatch(
        (x, y), width, height,
        boxstyle=f"round,pad=0,rounding_size={corner_radius}",
        facecolor=facecolor, edgecolor=edgecolor,
        linewidth=linewidth, zorder=zorder, alpha=alpha
    )
    ax.add_patch(box)
    return box

# ==============================================================================
# DIAGRAM 1: Multi-Tier System Architecture Topology
# ==============================================================================
def generate_architecture_diagram():
    fig, ax = plt.subplots(figsize=(13, 11), dpi=300)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 11)
    ax.axis('off')

    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FFFFFF')

    # Title header banner
    create_rounded_rect(ax, 0.6, 10.15, 11.8, 0.65, 0.08, '#1E3A8A', '#1E3A8A', zorder=2)
    ax.text(6.5, 10.47, "DIGITAL FORENSICS ANALYZER (DFA-14) - SYSTEM ARCHITECTURE TOPOLOGY",
            ha='center', va='center', color='#FFFFFF', fontsize=12.5, fontweight='bold', family='sans-serif', zorder=3)

    tiers = [
        {
            "y": 8.55, "h": 1.25, "num": "TIER 1", "title": "CLIENT PRESENTATION & INTERFACE LAYER",
            "bg": "#F0F9FF", "border": "#0284C7", "tag_bg": "#0284C7",
            "items": [
                ("Interactive Web Dashboard", "Modern HTML5 forensic user interface\nfor evidence upload & live status tracking", 5.65),
                ("REST API & Automation Interface", "Programmatic investigation endpoints\nand automated regression testing suite", 5.65)
            ],
            "connector_text": "HTTPS / Web Requests & Status Polling"
        },
        {
            "y": 6.65, "h": 1.45, "num": "TIER 2", "title": "APPLICATION CONTROLLER & ASYNCHRONOUS WORKER",
            "bg": "#EEF2FF", "border": "#4F46E5", "tag_bg": "#4F46E5",
            "items": [
                ("Web Application Router", "REST endpoints for uploads, streaming\ndeliverables & status responses", 3.65),
                ("Staging Controller", "Verifies image container headers\nand sanitizes evidence filenames", 3.65),
                ("Asynchronous Worker Pool", "Spawns dedicated background threads\nto prevent request thread blocking", 3.65)
            ],
            "connector_text": "Dispatches Job Parameters & Evidence Configuration"
        },
        {
            "y": 4.65, "h": 1.55, "num": "TIER 3", "title": "PIPELINE ORCHESTRATION & STATE MANAGEMENT",
            "bg": "#F8FAFC", "border": "#1E3A8A", "tag_bg": "#1E3A8A",
            "items": [
                ("Sequential Workflow Engine", "Coordinates Phases 1 through 9\nmodeled on ISO/IEC 27037 principles", 3.65),
                ("Real-Time State Store", "Atomic JSON state updates tracking\nstep progression & telemetry", 3.65),
                ("Resilient Failover Controller", "Watchdog execution monitoring with\nautomatic binary fallback logic", 3.65)
            ],
            "connector_text": "Executes Toolchain Vectors via Argument Lists (shell=False)"
        },
        {
            "y": 2.50, "h": 1.65, "num": "TIER 4", "title": "CORE FORENSIC ENGINES & LOW-LEVEL TOOLING",
            "bg": "#ECFDF5", "border": "#059669", "tag_bg": "#059669",
            "items": [
                ("The Sleuth Kit (TSK)", "mmls (partition geometry)\nfls (inode enumeration)\nicat & tsk_recover", 2.70),
                ("Autopsy CLI Engine", "Headless ingest execution\nwith strict 25-second\nwatchdog timeout", 2.70),
                ("Timeline Engine", "Chronological MACB\nsynthesis with native\nPython fallback parser", 2.70),
                ("Cryptographic Engine", "Streaming 64 KB block\nSHA-256 & MD5 hashing\nfor pre/post analysis", 2.70)
            ],
            "connector_text": "Persists Evidentiary Artifacts to Isolated Vault"
        },
        {
            "y": 0.45, "h": 1.55, "num": "TIER 5", "title": "ISOLATED EVIDENCE VAULT & STRUCTURED DELIVERABLES",
            "bg": "#F1F5F9", "border": "#334155", "tag_bg": "#334155",
            "items": [
                ("Evidence Storage Vault", "Original Disk Image (Read-Only Lock)\nand isolated analysis working copy", 3.65),
                ("Recovered Evidence Vault", "Recovered Inode Artifacts stored with\nnon-executable file permissions", 3.65),
                ("Structured Deliverables", "Audit Log, Timeline CSV, HTML Report,\nVector PDF & Case Archive ZIP", 3.65)
            ],
            "connector_text": None
        }
    ]

    for tier in tiers:
        y, h = tier["y"], tier["h"]
        # Outer tier box
        create_rounded_rect(ax, 0.6, y, 11.8, h, 0.08, tier["bg"], tier["border"], linewidth=1.5, zorder=2)

        # Tier badge
        create_rounded_rect(ax, 0.75, y + h - 0.36, 1.25, 0.28, 0.05, tier["tag_bg"], tier["tag_bg"], zorder=3)
        ax.text(1.375, y + h - 0.22, tier["num"], ha='center', va='center', color='#FFFFFF',
                fontsize=8.5, fontweight='bold', family='sans-serif', zorder=4)

        # Tier title
        ax.text(2.15, y + h - 0.22, tier["title"], ha='left', va='center', color=tier["border"],
                fontsize=9.5, fontweight='bold', family='sans-serif', zorder=4)

        # Inner item cards
        x_offset = 0.8
        for name, desc, cw in tier["items"]:
            ch = h - 0.52
            cy = y + 0.10
            create_rounded_rect(ax, x_offset, cy, cw, ch, 0.06, '#FFFFFF', '#CBD5E1', linewidth=1.0, zorder=3)
            # Item title
            ax.text(x_offset + 0.15, cy + ch - 0.22, name, ha='left', va='center', color='#0F172A',
                    fontsize=8.5, fontweight='bold', family='sans-serif', zorder=4)
            # Divider line inside card
            ax.plot([x_offset + 0.15, x_offset + cw - 0.15], [cy + ch - 0.38, cy + ch - 0.38],
                    color='#E2E8F0', lw=0.8, zorder=3)
            # Item description (explicit lines, guaranteed fit)
            ax.text(x_offset + 0.15, cy + (ch - 0.38) / 2.0, desc, ha='left', va='center', color='#475569',
                    fontsize=7.2, family='sans-serif', linespacing=1.25, zorder=4)
            x_offset += cw + 0.20

        # Connector arrow to next tier
        if tier["connector_text"]:
            ax.annotate('', xy=(6.5, y), xytext=(6.5, y - 0.45),
                        arrowprops=dict(arrowstyle='<-', color=tier["border"], lw=1.6), zorder=5)
            # Badge for connector text
            ax.text(6.5, y - 0.225, f"  {tier['connector_text']}  ", ha='center', va='center',
                    fontsize=7.2, fontweight='bold', color='#1E293B', family='sans-serif',
                    bbox=dict(boxstyle='round,pad=0.25', facecolor='#FFFFFF', edgecolor='#94A3B8', lw=0.8), zorder=6)

    out_file = IMG_DIR / "arch_topology.png"
    plt.tight_layout()
    plt.savefig(str(out_file), dpi=300, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"[+] Saved Architecture Diagram: {out_file}")


# ==============================================================================
# DIAGRAM 2: Nine-Phase Forensic Pipeline Sequential Workflow
# ==============================================================================
def generate_pipeline_diagram():
    fig, ax = plt.subplots(figsize=(13, 11), dpi=300)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 11)
    ax.axis('off')

    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FFFFFF')

    # Header banner
    create_rounded_rect(ax, 0.6, 10.15, 11.8, 0.65, 0.08, '#1E3A8A', '#1E3A8A', zorder=2)
    ax.text(6.5, 10.47, "THE NINE-PHASE FORENSIC EXAMINATION PIPELINE",
            ha='center', va='center', color='#FFFFFF', fontsize=12.5, fontweight='bold', family='sans-serif', zorder=3)

    phases = [
        # Row 1: Left to Right
        {"pnum": "PHASE 01", "name": "Evidence Intake & Protection", "engine": "Standard Library",
         "desc": "Applies software read-only lock\nCreates isolated analysis working copy\nValidates image container headers",
         "artifact": "Locked Evidence Copy", "col": 0, "row": 0, "theme": "#1E40AF", "bg": "#EFF6FF"},
        {"pnum": "PHASE 02", "name": "Baseline Cryptographic Hashes", "engine": "Python hashlib",
         "desc": "Streaming 64 KB block hashing\nComputes SHA-256 and MD5 baselines\nAsserts bit-for-bit initial parity",
         "artifact": "Pre-Analysis Hashes", "col": 1, "row": 0, "theme": "#1E40AF", "bg": "#EFF6FF"},
        {"pnum": "PHASE 03", "name": "Partition Table Inspection", "engine": "The Sleuth Kit (mmls)",
         "desc": "Parses volume partition geometry\nIdentifies MBR and GPT structures\nDynamically calculates sector offsets",
         "artifact": "Partition Layout Map", "col": 2, "row": 0, "theme": "#0F766E", "bg": "#F0FDFA"},

        # Row 2: Right to Left (snaking flow)
        {"pnum": "PHASE 04", "name": "File System Inode Listing", "engine": "The Sleuth Kit (fls)",
         "desc": "Traverses partition directory trees\nEnumerates allocated inode records\nFlags deleted entries (* indicator)",
         "artifact": "System Bodyfile", "col": 2, "row": 1, "theme": "#0F766E", "bg": "#F0FDFA"},
        {"pnum": "PHASE 05", "name": "Metadata-Driven File Recovery", "engine": "tsk_recover & icat",
         "desc": "Recovers files via inode pointers\nExtracts allocated & unallocated clusters\nStores files with non-exec attributes",
         "artifact": "Recovered File Store", "col": 1, "row": 1, "theme": "#0F766E", "bg": "#F0FDFA"},
        {"pnum": "PHASE 06", "name": "String Extraction & Indexing", "engine": "TSK srch_strings",
         "desc": "Extracts 7-bit ASCII text strings\nExtracts 16-bit UTF-16LE strings\nRecords decimal byte offsets for audit",
         "artifact": "String Index Files", "col": 0, "row": 1, "theme": "#4338CA", "bg": "#EEF2FF"},

        # Row 3: Left to Right
        {"pnum": "PHASE 07", "name": "Chronological Timeline", "engine": "mactime & Custom Parser",
         "desc": "Synthesizes MACB activity timestamps\nConstructs temporal event spreadsheet\nIncludes built-in Python regex fallback",
         "artifact": "Timeline CSV & JSON", "col": 0, "row": 2, "theme": "#4338CA", "bg": "#EEF2FF"},
        {"pnum": "PHASE 08", "name": "Heuristics & Engine Ingest", "engine": "Heuristics + Autopsy CLI",
         "desc": "Detects MIME magic byte mismatches\nIdentifies disguised file extensions\nRuns Autopsy with 25s watchdog timer",
         "artifact": "Anomaly & Alert Logs", "col": 1, "row": 2, "theme": "#C2410C", "bg": "#FFF7ED"},
        {"pnum": "PHASE 09", "name": "Deliverables & Verification", "engine": "ReportLab & Zipfile",
         "desc": "Re-computes post-analysis hashes\nAsserts 100% hash parity (PASS)\nCompiles HTML, PDF & ZIP archive",
         "artifact": "Case Package (HTML/PDF/ZIP)", "col": 2, "row": 2, "theme": "#047857", "bg": "#ECFDF5"},
    ]

    card_w = 3.5
    card_h = 2.5
    x_coords = [0.8, 4.8, 8.8]
    y_coords = [7.2, 4.0, 0.8]

    for p in phases:
        x = x_coords[p["col"]]
        y = y_coords[p["row"]]

        # Outer card
        create_rounded_rect(ax, x, y, card_w, card_h, 0.08, p["bg"], p["theme"], linewidth=1.6, zorder=2)

        # Header tag
        create_rounded_rect(ax, x + 0.15, y + card_h - 0.42, 1.25, 0.30, 0.06, p["theme"], p["theme"], zorder=3)
        ax.text(x + 0.775, y + card_h - 0.27, p["pnum"], ha='center', va='center', color='#FFFFFF',
                fontsize=8.5, fontweight='bold', family='sans-serif', zorder=4)

        # Engine pill
        create_rounded_rect(ax, x + 1.5, y + card_h - 0.42, card_w - 1.65, 0.30, 0.06, '#FFFFFF', '#CBD5E1', linewidth=1.0, zorder=3)
        ax.text(x + 1.5 + (card_w - 1.65)/2.0, y + card_h - 0.27, p["engine"], ha='center', va='center', color='#334155',
                fontsize=7.2, fontweight='bold', family='sans-serif', zorder=4)

        # Phase title
        ax.text(x + 0.18, y + card_h - 0.72, p["name"], ha='left', va='center', color='#0F172A',
                fontsize=9.0, fontweight='bold', family='sans-serif', zorder=4)

        # Horizontal separator
        ax.plot([x + 0.18, x + card_w - 0.18], [y + card_h - 0.90, y + card_h - 0.90], color='#E2E8F0', lw=1.0, zorder=3)

        # Explicit description lines (guaranteed zero spillage)
        ax.text(x + 0.18, y + 1.05, p["desc"], ha='left', va='center', color='#475569',
                fontsize=7.5, family='sans-serif', linespacing=1.28, zorder=4)

        # Output artifact pill at bottom
        create_rounded_rect(ax, x + 0.18, y + 0.18, card_w - 0.36, 0.38, 0.05, '#FFFFFF', '#CBD5E1', linewidth=0.8, zorder=3)
        ax.text(x + 0.28, y + 0.37, "Deliverable:", ha='left', va='center', color=p["theme"],
                fontsize=7.0, fontweight='bold', family='sans-serif', zorder=4)
        ax.text(x + 1.25, y + 0.37, p["artifact"], ha='left', va='center', color='#1E293B',
                fontsize=7.2, fontweight='bold', family='sans-serif', zorder=4)

    # Connecting arrows (strictly in empty corridors between cards)
    # Row 1: P1 -> P2 -> P3
    ax.annotate('', xy=(4.8, 8.45), xytext=(4.3, 8.45),
                arrowprops=dict(arrowstyle='->', color='#1E40AF', lw=2.2), zorder=5)
    ax.annotate('', xy=(8.8, 8.45), xytext=(8.3, 8.45),
                arrowprops=dict(arrowstyle='->', color='#0F766E', lw=2.2), zorder=5)

    # Turn from Row 1 to Row 2: P3 down to P4
    ax.annotate('', xy=(10.55, 6.5), xytext=(10.55, 7.2),
                arrowprops=dict(arrowstyle='->', color='#0F766E', lw=2.2), zorder=5)

    # Row 2: P4 -> P5 -> P6 (Right to Left)
    ax.annotate('', xy=(8.3, 5.25), xytext=(8.8, 5.25),
                arrowprops=dict(arrowstyle='->', color='#0F766E', lw=2.2), zorder=5)
    ax.annotate('', xy=(4.3, 5.25), xytext=(4.8, 5.25),
                arrowprops=dict(arrowstyle='->', color='#4338CA', lw=2.2), zorder=5)

    # Turn from Row 2 to Row 3: P6 down to P7
    ax.annotate('', xy=(2.55, 3.3), xytext=(2.55, 4.0),
                arrowprops=dict(arrowstyle='->', color='#4338CA', lw=2.2), zorder=5)

    # Row 3: P7 -> P8 -> P9 (Left to Right)
    ax.annotate('', xy=(4.8, 2.05), xytext=(4.3, 2.05),
                arrowprops=dict(arrowstyle='->', color='#C2410C', lw=2.2), zorder=5)
    ax.annotate('', xy=(8.8, 2.05), xytext=(8.3, 2.05),
                arrowprops=dict(arrowstyle='->', color='#047857', lw=2.2), zorder=5)

    out_file = IMG_DIR / "pipeline_flowchart.png"
    plt.tight_layout()
    plt.savefig(str(out_file), dpi=300, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"[+] Saved Pipeline Diagram: {out_file}")


# ==============================================================================
# DIAGRAM 3: End-to-End System Workflow (Swimlane with wide corridor)
# ==============================================================================
def generate_workflow_diagram():
    fig, ax = plt.subplots(figsize=(14, 10), dpi=300)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis('off')

    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FFFFFF')

    # Main Title Header
    create_rounded_rect(ax, 0.6, 9.15, 12.8, 0.65, 0.08, '#1E3A8A', '#1E3A8A', zorder=2)
    ax.text(7.0, 9.47, "END-TO-END INVESTIGATION WORKFLOW & INTERACTION LIFECYCLE",
            ha='center', va='center', color='#FFFFFF', fontsize=12.5, fontweight='bold', family='sans-serif', zorder=3)

    # Left Swimlane: Examiner Operations (x = 0.6 to 5.6)
    create_rounded_rect(ax, 0.6, 0.5, 5.0, 8.4, 0.08, '#F8FAFC', '#94A3B8', linewidth=1.5, zorder=1)
    create_rounded_rect(ax, 0.8, 8.2, 4.6, 0.5, 0.06, '#0284C7', '#0284C7', zorder=2)
    ax.text(3.1, 8.45, "EXAMINER / CLIENT WORKFLOW", ha='center', va='center', color='#FFFFFF',
            fontsize=9.5, fontweight='bold', family='sans-serif', zorder=3)

    # Right Swimlane: Backend Engine Operations (x = 8.4 to 13.4)
    create_rounded_rect(ax, 8.4, 0.5, 5.0, 8.4, 0.08, '#F8FAFC', '#94A3B8', linewidth=1.5, zorder=1)
    create_rounded_rect(ax, 8.6, 8.2, 4.6, 0.5, 0.06, '#1E3A8A', '#1E3A8A', zorder=2)
    ax.text(10.9, 8.45, "AUTOMATED BACKEND FORENSIC ENGINE", ha='center', va='center', color='#FFFFFF',
            fontsize=9.5, fontweight='bold', family='sans-serif', zorder=3)

    # Wide central corridor is x = 5.6 to 8.4 (2.8 units wide) -> plenty of space for badges!

    steps = [
        # Step 1
        {"y": 6.35, "user_t": "1. Access Dashboard & Select Image",
         "user_d": "• Examiner accesses web interface\n• Selects raw (.dd) or Expert Witness (.E01)\n• System prepares secure upload channel",
         "sys_t": "1. Ready State & Upload Controller",
         "sys_d": "• Web server validates payload headers\n• Verifies forensic format integrity\n• Provisions isolated case workspace",
         "interaction": "HTTP POST Evidence Upload", "dir": "right"},

        # Step 2
        {"y": 4.45, "user_t": "2. Initiate Automated Case Ingestion",
         "user_d": "• Enters case reference & investigator metadata\n• Clicks Begin Investigation button\n• Enters monitoring telemetry mode",
         "sys_t": "2. Ingestion & Thread Dispatch",
         "sys_d": "• Enforces software read-only attribute\n• Calculates baseline SHA-256 / MD5 hashes\n• Dispatches background execution worker",
         "interaction": "Dispatches Background Worker", "dir": "right"},

        # Step 3
        {"y": 2.55, "user_t": "3. Monitor Live Pipeline Telemetry",
         "user_d": "• Web dashboard displays dynamic progress bar\n• Real-time stage progression & status logs\n• Zero manual examiner intervention needed",
         "sys_t": "3. Sequential Pipeline Execution",
         "sys_d": "• Executes Phases 3-8 sequentially\n• Inodes, recovery, strings, timeline, heuristics\n• Updates status.json telemetry atomically",
         "interaction": "AJAX Polling Status Updates", "dir": "left"},

        # Step 4
        {"y": 0.65, "user_t": "4. Review Findings & Export Deliverables",
         "user_d": "• Inspects structured HTML report in browser\n• Downloads vector PDF report\n• Archives complete case package ZIP",
         "sys_t": "4. Verification & Package Assembly",
         "sys_d": "• Validates post-analysis hashes (100% PASS)\n• Compiles HTML, PDF & chain of custody\n• Builds compressed case package ZIP",
         "interaction": "Download Deliverable Streams", "dir": "left"}
    ]

    for s in steps:
        y = s["y"]
        # Left card (Examiner)
        create_rounded_rect(ax, 0.8, y, 4.6, 1.6, 0.06, '#FFFFFF', '#0284C7', linewidth=1.2, zorder=2)
        ax.text(0.95, y + 1.35, s["user_t"], ha='left', va='center', color='#0284C7',
                fontsize=8.8, fontweight='bold', family='sans-serif', zorder=3)
        ax.plot([0.95, 5.25], [y + 1.15, y + 1.15], color='#E2E8F0', lw=0.8, zorder=3)
        ax.text(0.95, y + 0.60, s["user_d"], ha='left', va='center', color='#475569',
                fontsize=7.5, family='sans-serif', linespacing=1.28, zorder=3)

        # Right card (System)
        create_rounded_rect(ax, 8.6, y, 4.6, 1.6, 0.06, '#FFFFFF', '#1E3A8A', linewidth=1.2, zorder=2)
        ax.text(8.75, y + 1.35, s["sys_t"], ha='left', va='center', color='#1E3A8A',
                fontsize=8.8, fontweight='bold', family='sans-serif', zorder=3)
        ax.plot([8.75, 13.05], [y + 1.15, y + 1.15], color='#E2E8F0', lw=0.8, zorder=3)
        ax.text(8.75, y + 0.60, s["sys_d"], ha='left', va='center', color='#475569',
                fontsize=7.5, family='sans-serif', linespacing=1.28, zorder=3)

        # Central interaction arrow and badge (located strictly in the 5.6 to 8.4 corridor)
        mid_y = y + 0.80
        if s["dir"] == "right":
            # Arrow from 5.6 to 8.4
            ax.annotate('', xy=(8.5, mid_y), xytext=(5.5, mid_y),
                        arrowprops=dict(arrowstyle='->', color='#2563EB', lw=2.0), zorder=4)
        else:
            # Arrow from 8.4 to 5.6
            ax.annotate('', xy=(5.5, mid_y), xytext=(8.5, mid_y),
                        arrowprops=dict(arrowstyle='->', color='#059669', lw=2.0), zorder=4)

        # Badge in the exact center of corridor (x = 7.0, width fits easily inside 2.8 units)
        ax.text(7.0, mid_y, f"  {s['interaction']}  ",
                ha='center', va='center', fontsize=6.8, fontweight='bold', color='#0F172A', family='sans-serif',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#FFFFFF', edgecolor='#64748B', lw=1.0), zorder=6)

    out_file = IMG_DIR / "workflow_swimlane.png"
    plt.tight_layout()
    plt.savefig(str(out_file), dpi=300, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.close()
    print(f"[+] Saved Workflow Diagram: {out_file}")

if __name__ == "__main__":
    generate_architecture_diagram()
    generate_pipeline_diagram()
    generate_workflow_diagram()
