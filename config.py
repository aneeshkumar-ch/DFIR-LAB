import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(r"D:\PROJECTS\ForensicsAnalyzer").resolve()
JOBS_DIR = BASE_DIR / "jobs"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Flask Server Configuration
HOST = "127.0.0.1"
PORT = 5000
DEBUG = False
SECRET_KEY = "case-test-014-digital-forensics-analyzer-secret-key"
# Maximum upload size: 10 GB
MAX_CONTENT_LENGTH = 10 * 1024 * 1024 * 1024

# Case Defaults
DEFAULT_CASE_NUMBER = "CASE-TEST-014"
DEFAULT_EXAMINER = "Forensics Examiner"

# Supported Evidence Image Formats
ALLOWED_EXTENSIONS = {".dd", ".img", ".raw", ".001", ".e01"}

# The Sleuth Kit (TSK) Configuration
TSK_BIN_DIR = Path(r"D:\sleuthkit-4.15.0-win32\bin")

MMLS_PATH = str(TSK_BIN_DIR / "mmls.exe")
FLS_PATH = str(TSK_BIN_DIR / "fls.exe")
FSSTAT_PATH = str(TSK_BIN_DIR / "fsstat.exe")
ICAT_PATH = str(TSK_BIN_DIR / "icat.exe")
TSK_RECOVER_PATH = str(TSK_BIN_DIR / "tsk_recover.exe")
TSK_GETTIMES_PATH = str(TSK_BIN_DIR / "tsk_gettimes.exe")
IMG_STAT_PATH = str(TSK_BIN_DIR / "img_stat.exe")
MACTIME_SCRIPT = str(TSK_BIN_DIR / "mactime.pl")

# Perl Configuration (used for mactime.pl)
PERL_PATH = "perl"

# Autopsy Configuration
AUTOPSY_DIR = Path(r"D:\Autopsy-4.23.1")
AUTOPSY_BIN = str(AUTOPSY_DIR / "bin" / "autopsy64.exe")
AUTOPSY_ENABLED = True
AUTOPSY_TIMEOUT_SECONDS = 25  # Timeout for command line ingest attempt

# Optional / External Forensic Utilities
EWFVERIFY_PATH = None  # Populated dynamically if found in PATH or custom dir
SRCH_STRINGS_PATH = None  # Populated dynamically if found

# Ensure critical job directory exists
JOBS_DIR.mkdir(parents=True, exist_ok=True)
