# Digital Forensics Analyzer (DFA-14)
**Automated Forensic Investigation & Reporting Engine**  
**BCSSL Lab 14 (CASE-TEST-014)**  
**Platform: Windows | Python 3.10+ | The Sleuth Kit (Autopsy CLI when available)**

---

## 1. Overview
**Digital Forensics Analyzer** is a fully automated web-based digital forensics investigation tool designed for BCSSL Lab 14 (Case: `CASE-TEST-014`). When a raw bitstream (`.dd`, `.raw`, `.img`, `.001`) or Expert Witness format (`.E01`) disk image is uploaded, the analyzer executes a comprehensive 9-phase forensic examination end-to-end without requiring manual steps, preserves evidence integrity with strict read-only protection (software attribute; a hardware or driver-level write blocker would be used on real evidence), and generates structured forensic reports in both HTML and PDF formats alongside a complete downloadable case package.

---

## 2. Key Forensic Capabilities

| Forensic Phase | Engine / Tool | Capability & Forensic Function |
| :--- | :--- | :--- |
| **1. Evidence Intake & Read-Only Protection** | Standard Library (`hashlib`, `stat`) | Uploads saved to `jobs/<id>/original/` and set to strictly READ-ONLY via read-only protection (software attribute; a hardware or driver-level write blocker would be used on real evidence). Baseline SHA-256 computed. Bitstream copy created in `working/` and verified identical. |
| **2. Chain of Custody & Audit Trail** | Built-in Custody Logger | Generates `chain_of_custody.txt` and `actions_log.txt` with UTC timestamps, examiner details, storage paths, and chronological audit entries modeled on ISO/IEC 27037 principles. |
| **3. Partition & Filesystem Architecture** | TSK `mmls`, `fsstat` | Parses GPT and MBR partition tables. Extracts sector offsets, volume labels, serial numbers, block sizes, and filesystem architectures (FAT12/16/32, NTFS, EXT). |
| **4. File Listing & Inode Enumeration** | TSK `fls -r` | Recursively enumerates active and deleted file records. Identifies unallocated directory entries flagged with `*` and outputs structured `file_listing.json`. |
| **5. File Recovery & Anti-Forensics Analysis** | TSK `tsk_recover -e`, `icat`, Magic Engine | Recovers unallocated file data via volume-level metadata extraction (`tsk_recover`) and targeted inode extraction (`icat`) into non-executable storage `jobs/<id>/recovered/`. Computes SHA-256 for all recovered items and flags disguised file extensions via magic byte inspection. |
| **6. MACB Activity Timeline** | TSK `fls -m`, `mactime.pl` (Perl) | Compiles standard Sleuth Kit body file into an ISO-8601 UTC timeline (`timeline.csv`) using `mactime.pl` executed directly via Perl (with an internal Python parser fallback). Computes daily activity distribution rendered as an interactive Chart.js graphic. |
| **7. Forensic Keyword Discovery** | Dual-Layer Binary Scanner | Scans all recovered files and raw disk image sectors (both ASCII and UTF-16LE) for target keywords, logging exact byte offsets and surrounding context snippets into `keyword_hits.json`. |
| **8. Post-Examination Cryptographic Integrity Audit** | Cryptographic Re-Hashing | Re-hashes original and working copies after examination. Compares against acquisition baseline and reports explicit **PASS** or **FAIL** in `integrity.json`. |
| **9. Report Compilation & Case Deliverables** | Jinja2 & ReportLab | Generates interactive `report.html`, professional `report.pdf`, and bundles `case_package.zip` (containing structured forensic reports, audit logs, hashes, timeline CSV, and recovered files). |

---

## 3. Autopsy Automation & Engine Mode Architecture

Per lab requirements, the system evaluates the local Autopsy installation (`D:\Autopsy-4.23.1\bin\autopsy64.exe`):
1. **Autopsy Command-Line Ingest**: Inspects `CommandLineOptionProcessor` flags (`--createCase`, `--caseName`, `--caseBaseDir`, `--addDataSource`, `--dataSourcePath`, `--runIngest`, `--generateReports`).
2. **Observed Local Test Result & Fallback**: In testing on the local Windows environment, invoking `autopsy64.exe` headlessly timed out after 25 seconds (`AUTOPSY_TIMEOUT_SECONDS = 25` in `config.py`) without producing an HTML report, as Autopsy command-line ingest requires an interactive desktop session and pre-configured GUI ingest/report profiles. Consequently, the pipeline seamlessly fell back to **The Sleuth Kit (TSK) Native Pipeline**, which reliably completed all analysis tasks in seconds. If an Autopsy execution produces an HTML report within the timeout window, the analyzer archives and presents it directly.
3. **Attribution**: The final report explicitly documents which engine mode was utilized (`Autopsy Command-Line Ingest Engine` vs `The Sleuth Kit (TSK) Native Pipeline`).

---

## 4. Safety & Operational Security (OpSec)

- **Untrusted File Quarantine & Non-Executable Storage**: Recovered files may contain live exploits, malicious payloads, or weaponized binaries. All recovered files are strictly treated as passive evidence data: they are never opened or executed by the application and are saved to `jobs/<job_id>/recovered/` with execution permissions removed (`stat.S_IREAD | stat.S_IWRITE`).
- **Windows Defender Advisory & Exclusion**: Windows Defender may quarantine suspicious test strings, unpacked malware samples, or recovered artifacts. To prevent operational disruption during forensic analysis, add a folder exclusion in Windows Defender via elevated PowerShell:
  ```powershell
  Add-MpPreference -ExclusionPath "D:\PROJECTS\ForensicsAnalyzer\jobs"
  ```
- **XSS & Injection Protection**: HTML templates utilize strict Jinja2 autoescaping (`select_autoescape(['html', 'xml'])`). Dynamic data strings interpolated into ReportLab PDF flowables are sanitized with XML escaping (`xml.sax.saxutils.escape`) to prevent injection attacks.
- **Localhost Binding**: The Flask application server binds strictly to the loopback interface `127.0.0.1:5000` (`host="127.0.0.1"`), preventing unauthorized external network access.
- **Upload Size Limit**: HTTP evidence uploads are constrained to a configurable maximum size limit of 10 GB (`MAX_CONTENT_LENGTH = 10 * 1024 * 1024 * 1024` in `config.py`) to safeguard system memory and storage against denial-of-service (DoS) exhaustion.
- **Subprocess Safety**: All invocations of external forensic utilities (`mmls`, `fls`, `fsstat`, `icat`, `tsk_recover`, `mactime.pl`, `attrib`) use strict argument lists (vectors) and never pass commands through the shell (`shell=False`), preventing command injection.

---

## 5. Directory Structure

```
D:\PROJECTS\ForensicsAnalyzer\
├── app.py                      # Flask web application and background worker orchestration
├── config.py                   # Central paths, binary locations, timeouts, and upload limits
├── requirements.txt            # Python dependencies
├── README.md                   # Complete system documentation
├── test_pipeline.py            # Automated verification test script
├── test_web_endpoints.py       # Comprehensive Flask HTTP endpoint tests
├── test_e01.py                 # E01 309MB forensic image test runner
├── analyzer/
│   ├── __init__.py
│   ├── intake.py               # Intake, SHA-256 hashing, read-only protection, chain of custody
│   ├── tsk.py                  # mmls partition parsing, fsstat, fls file listing
│   ├── autopsy_cli.py          # Autopsy CLI automation and fallback handler
│   ├── recovery.py             # icat, tsk_recover, magic byte detection, extension mismatch
│   ├── timeline.py             # fls -m bodyfile generator, mactime.pl, timeline CSV & chart
│   ├── keywords.py             # Keyword search across recovered files and raw disk image
│   ├── integrity.py            # Re-hashing evidence verification (PASS/FAIL)
│   └── report.py               # Jinja2 HTML report, ReportLab PDF, and ZIP case packaging
├── templates/
│   ├── upload.html             # Upload dropzone and case metadata form
│   ├── job.html                # Real-time 9-phase progress tracker and live action logger
│   └── report.html             # Interactive forensic laboratory case report
├── static/
│   └── style.css               # Responsive forensic styling and badges
├── test_images/
│   ├── make_practice_image.py  # Synthetic FAT12 practice disk image generator
│   └── practice_evidence.dd    # 1.44MB test image with deleted files & extension disguise
└── jobs/                       # Runtime storage for examination artifacts (per job_id)
```

---

## 6. Installation & Setup

### Prerequisites
- **Windows 10/11** or **Windows Server**
- **Python 3.10+** (verified on Python 3.13)
- **The Sleuth Kit (TSK)** Windows binaries located at `D:\sleuthkit-4.15.0-win32\bin`
- **Autopsy** located at `D:\Autopsy-4.23.1`
- **Perl** (in system PATH) for `mactime.pl` (Perl 5.42.2 is installed and used directly; Python is an automated fallback)

### Step 1: Install Python Dependencies
Open PowerShell and navigate to the project directory:
```powershell
cd D:\PROJECTS\ForensicsAnalyzer
python -m pip install -r requirements.txt
```

### Step 2: Generate or Place Test Disk Image
A self-contained practice disk image generator is included:
```powershell
python test_images\make_practice_image.py
```
This generates `practice_evidence.dd` (1.44 MB) containing active files, deliberate deleted files (`FLAG.TXT`, `SECRET.TXT`, `PASSWD.TXT`), and an extension disguise (`DISGUISE.TXT` with real PNG magic bytes).

---

## 7. Running the Tool

### Step 1: Start the Web Application
```powershell
cd D:\PROJECTS\ForensicsAnalyzer
python app.py
```

Console output will display:
```
================================================================
 Digital Forensics Analyzer -- BCSSL Lab 14 (CASE-TEST-014)
 Binding to: http://127.0.0.1:5000
 Evidence Directory: D:\PROJECTS\ForensicsAnalyzer\jobs
 TSK Binaries:       D:\sleuthkit-4.15.0-win32\bin
 Autopsy Bin:        D:\Autopsy-4.23.1\bin\autopsy64.exe
================================================================
```

### Step 2: Access the User Interface
Open your web browser and navigate to:
**`http://127.0.0.1:5000`**

1. Enter **Case Number** (default: `CASE-TEST-014`) and **Lead Examiner Name**.
2. Select or drag-and-drop your evidence image (`practice_evidence.dd` or `2020DFImage.E01`).
3. Enter target keywords (e.g. `secret, password, confidential, flag`).
4. Click **Start Automated Forensic Analysis**.

### Step 3: Monitor Live Execution
The page redirects to `/job/<job_id>`. The interface displays real-time execution across the 9 forensic steps and streams lines from `actions_log.txt`.

### Step 4: Review and Download Deliverables
Upon completion, direct download options become active:
- **View Interactive Report**: Opens complete HTML structured forensic report with Chart.js timeline and searchable tables.
- **Download PDF Report**: Downloads official ReportLab PDF case document.
- **Download Case Package (ZIP)**: Archives structured forensic report, PDF, logs, hashes, timeline CSV, and recovered files.
- **Download Timeline CSV**: Delivers standard MACB timeline.

---

## 8. Testing

The analyzer includes automated test suites covering end-to-end pipeline execution, web endpoints, and large raw/E01 images.

### 1. Automated Pipeline Test (`test_pipeline.py`)
Executes the full 9-phase automated forensic pipeline against `practice_evidence.dd` and verifies all deliverable artifacts and cryptographic integrity:
```powershell
python test_pipeline.py
```
**Verification Results Summary**:
- **Pipeline Status**: `completed` (all 9 steps `done`)
- **Deliverables Verified**: `chain_of_custody.txt`, `actions_log.txt`, `hashes.txt`, `file_listing.json`, `timeline.csv`, `timeline.json`, `keyword_hits.json`, `integrity.json`, `report.html`, `report.pdf`, `case_package.zip` (all 100% present and non-empty).
- **Evidence Integrity**: `PASS` (Acquisition SHA-256 matches final original and working hashes).
- **File Recovery**: Successfully recovered deleted files (`FLAG.TXT`, `SECRET.TXT`, `PASSWD.TXT`) with SHA-256 hashes.
- **Anti-Forensics Deception**: Correctly flagged `DISGUISE.TXT` as PNG image masquerading under a `.txt` extension.
- **Keyword Search**: Successfully located keyword hits across recovered files and raw sectors.

### 2. Web Endpoints Test (`test_web_endpoints.py`)
Validates Flask HTTP routes, page rendering, live polling, and file downloads:
```powershell
python test_web_endpoints.py
```
All endpoints return HTTP `200 OK` (index `/`, job status `/job/<id>`, polling `/api/job/<id>`, HTML report `/job/<id>/report`, PDF download `/job/<id>/download/pdf`, Case ZIP download `/job/<id>/download/package`, Timeline CSV `/job/<id>/download/timeline`, and Evidence Image `/job/<id>/download/evidence`).

### 3. Forensic E01 Image Test (`test_e01.py`)
Validates handling of Expert Witness format images (`2020DFImage.E01`, 309 MB NTFS):
```powershell
python test_e01.py
```
- E01 partition table parsed (NTFS partition at sector 2048).
- 4,721 files recovered from image metadata.
- Cryptographic integrity audit reported `PASS`.

---

## 9. Mapping Tool Outputs to BCSSL Lab 14 Deliverables

| Lab Deliverable (Lab 14 Rubric) | Tool Output Artifact | Location in Case Package |
| :--- | :--- | :--- |
| **1. Forensic Image & Verification Hash Log (20%)** | `hashes.txt` & `chain_of_custody.txt` | `jobs/<id>/hashes.txt`<br>`jobs/<id>/chain_of_custody.txt` |
| **2. Python Hash Verification Output (PASS/FAIL)** | `integrity.json` & PDF Report Badge | `jobs/<id>/integrity.json`<br>`jobs/<id>/reports/report.pdf` |
| **3. Deleted File Recovery via TSK (30%)** | Recovered Files & `recovered_files.json` | `jobs/<id>/recovered/` (recovered files)<br>`jobs/<id>/recovered_files.json` |
| **4. Anti-Forensics / Deception Detection** | Extension Mismatch Analysis | Highlighted in HTML/PDF reports (`FLAG: Renamed file detected`) |
| **5. MACB Activity Timeline (20%)** | `timeline.csv` & Chart.js Activity Graph | `jobs/<id>/timeline.csv`<br>Interactive chart in `report.html` |
| **6. Written Chain-of-Custody Log (15%)** | `chain_of_custody.txt` & `actions_log.txt` | `jobs/<id>/chain_of_custody.txt`<br>`jobs/<id>/actions_log.txt` |
| **7. Final Combined Case Report (15%)** | `report.html`, `report.pdf`, `case_package.zip` | `jobs/<id>/reports/report.html`<br>`jobs/<id>/reports/report.pdf` |

### Manual Steps Required for Submission
- **Autopsy GUI Screenshots**: Because Autopsy operates via GUI for student lab submissions (Phase 3 of the lab manual), open `Autopsy` GUI manually, open or create `CASE-TEST-014`, load the image, and capture screenshots of:
  - Data Sources > File System > Deleted Files view.
  - Tools > Timeline view.
- All other hashing, custody logging, TSK command-line recoveries, timeline CSV compilation, and structured case reporting are **100% automated** by this tool.
#   D F I R - L A B  
 