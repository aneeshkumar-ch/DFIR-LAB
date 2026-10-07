import os
import platform
import shutil
from pathlib import Path

# Operating System Detection
IS_WINDOWS = platform.system() == "Windows"

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
JOBS_DIR = BASE_DIR / "jobs"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Flask Server Configuration
HOST = os.getenv("FLASK_HOST", "127.0.0.1")
PORT = int(os.getenv("FLASK_PORT", 5000))
DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
SECRET_KEY = os.getenv("SECRET_KEY", "case-test-014-digital-forensics-analyzer-secret-key")
# Maximum upload size: 10 GB
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024 * 1024))

# Case Defaults
DEFAULT_CASE_NUMBER = os.getenv("DEFAULT_CASE_NUMBER", "CASE-TEST-014")
DEFAULT_EXAMINER = os.getenv("DEFAULT_EXAMINER", "Forensics Examiner")

# Supported Evidence Image Formats
ALLOWED_EXTENSIONS = {".dd", ".img", ".raw", ".001", ".e01"}

# The Sleuth Kit (TSK) Configuration
_tsk_env = os.getenv("TSK_BIN_DIR")
if _tsk_env:
    TSK_BIN_DIR = Path(_tsk_env)
elif IS_WINDOWS and Path(r"D:\sleuthkit-4.15.0-win32\bin").exists():
    TSK_BIN_DIR = Path(r"D:\sleuthkit-4.15.0-win32\bin")
else:
    TSK_BIN_DIR = None

def _resolve_binary(name: str) -> str:
    ext = ".exe" if IS_WINDOWS else ""
    if TSK_BIN_DIR:
        candidate = TSK_BIN_DIR / f"{name}{ext}"
        if candidate.exists():
            return str(candidate)
    found = shutil.which(f"{name}{ext}") or shutil.which(name)
    if found:
        return found
    return f"{name}{ext}" if IS_WINDOWS else name

MMLS_PATH = _resolve_binary("mmls")
FLS_PATH = _resolve_binary("fls")
FSSTAT_PATH = _resolve_binary("fsstat")
ICAT_PATH = _resolve_binary("icat")
TSK_RECOVER_PATH = _resolve_binary("tsk_recover")
TSK_GETTIMES_PATH = _resolve_binary("tsk_gettimes")
IMG_STAT_PATH = _resolve_binary("img_stat")

# Perl Configuration (used for mactime)
PERL_PATH = shutil.which("perl") or "perl"
_mactime_candidate = _resolve_binary("mactime.pl")
if not (os.path.isfile(_mactime_candidate) or shutil.which(_mactime_candidate)):
    _mactime_candidate = shutil.which("mactime") or "mactime"
MACTIME_SCRIPT = _mactime_candidate

# Autopsy Configuration
_autopsy_env = os.getenv("AUTOPSY_DIR")
if _autopsy_env:
    AUTOPSY_DIR = Path(_autopsy_env)
elif IS_WINDOWS and Path(r"D:\Autopsy-4.23.1").exists():
    AUTOPSY_DIR = Path(r"D:\Autopsy-4.23.1")
else:
    AUTOPSY_DIR = Path("/usr/share/autopsy")

AUTOPSY_BIN = str(AUTOPSY_DIR / "bin" / ("autopsy64.exe" if IS_WINDOWS else "autopsy"))
AUTOPSY_ENABLED = os.getenv("AUTOPSY_ENABLED", "true" if IS_WINDOWS else "false").lower() in ("true", "1", "yes")
AUTOPSY_TIMEOUT_SECONDS = int(os.getenv("AUTOPSY_TIMEOUT_SECONDS", 25))

# Optional / External Forensic Utilities
EWFVERIFY_PATH = shutil.which("ewfverify.exe" if IS_WINDOWS else "ewfverify")
SRCH_STRINGS_PATH = shutil.which("srch_strings.exe" if IS_WINDOWS else "srch_strings")

# Resource Optimization & Storage Retention Policies
AUTO_CLEAN_WORKING_IMAGE = os.getenv("AUTO_CLEAN_WORKING_IMAGE", "true").lower() in ("true", "1", "yes")
RAW_IMAGE_RETENTION_HOURS = int(os.getenv("RAW_IMAGE_RETENTION_HOURS", 24))
JOB_RETENTION_HOURS = int(os.getenv("JOB_RETENTION_HOURS", 72))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", 1800))
MIN_FREE_DISK_GB = float(os.getenv("MIN_FREE_DISK_GB", 1.5))

# Ensure critical job directory exists
JOBS_DIR.mkdir(parents=True, exist_ok=True)

