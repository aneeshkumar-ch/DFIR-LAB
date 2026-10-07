import os
import re
import shutil
import stat
import subprocess
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import config

def sanitize_filename(filename: str) -> str:
    """Sanitize the uploaded evidence filename to prevent path traversal and shell injection."""
    filename = Path(filename).name
    # Keep only alphanumeric, dashes, underscores, and dots
    clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
    if not clean_name:
        clean_name = "evidence_image.raw"
    return clean_name

def calculate_sha256(filepath: Path | str, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hex digest using streaming chunk reading."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest().lower()

def format_bytes(size: int) -> str:
    """Format byte size into human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def get_utc_now_str() -> str:
    """Return formatted UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def log_action(job_dir: Path, message: str) -> None:
    """Log an operational forensic step to actions_log.txt with UTC timestamp."""
    log_path = job_dir / "actions_log.txt"
    timestamp = get_utc_now_str()
    entry = f"[{timestamp}] {message}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)

def record_custody_action(job_dir: Path, action_desc: str) -> None:
    """Append a chain of custody action entry with UTC timestamp."""
    custody_path = job_dir / "chain_of_custody.txt"
    timestamp = get_utc_now_str()
    entry = f"  - [{timestamp}] {action_desc}\n"
    with open(custody_path, "a", encoding="utf-8") as f:
        f.write(entry)

def set_read_only(filepath: Path) -> None:
    """Make the original evidence file strictly read-only."""
    try:
        os.chmod(filepath, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        # Apply Windows attrib +R safely if on Windows
        if os.name == "nt":
            subprocess.run(["attrib", "+R", str(filepath)], check=False, capture_output=True)
    except Exception as e:
        print(f"Warning setting read-only flag on {filepath}: {e}")


def verify_e01(image_path: Path, job_dir: Path) -> dict:
    """Verify E01 file integrity using ewfverify if available or img_stat."""
    result = {"verified": False, "tool_used": None, "details": ""}
    
    # 1. Try ewfverify if configured or in PATH
    ewfverify_bin = config.EWFVERIFY_PATH or shutil.which("ewfverify") or shutil.which("ewfverify.exe")
    if ewfverify_bin and os.path.isfile(ewfverify_bin):
        try:
            log_action(job_dir, f"Running ewfverify integrity verification using {ewfverify_bin}")
            proc = subprocess.run([ewfverify_bin, "-l", str(job_dir / "ewfverify.log"), str(image_path)],
                                  capture_output=True, text=True, check=False)
            if proc.returncode == 0:
                result["verified"] = True
                result["tool_used"] = "ewfverify"
                result["details"] = "EWF acquisition hash verified successfully."
                log_action(job_dir, "ewfverify completed: Acquisition hash match confirmed.")
                return result
            else:
                result["details"] = proc.stderr or proc.stdout
        except Exception as e:
            result["details"] = f"ewfverify execution error: {e}"

    # 2. Verify with TSK img_stat (libewf support)
    img_stat_bin = config.IMG_STAT_PATH
    if os.path.isfile(img_stat_bin):
        try:
            log_action(job_dir, f"Running TSK img_stat E01 structure validation")
            proc = subprocess.run([img_stat_bin, str(image_path)],
                                  capture_output=True, text=True, check=False)
            if proc.returncode == 0 and "Image Type:\tewf" in proc.stdout:
                result["verified"] = True
                result["tool_used"] = "The Sleuth Kit img_stat (libewf)"
                # Extract image metadata
                lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
                result["details"] = " | ".join(lines[:4])
                log_action(job_dir, f"E01 verified via TSK img_stat: {result['details']}")
                return result
            else:
                result["details"] = proc.stderr or "Invalid or unreadable E01 image format"
        except Exception as e:
            result["details"] = f"img_stat execution error: {e}"

    result["details"] = result["details"] or "No specific E01 verification utility found; proceeding with standard cryptographic verification."
    return result

def intake_evidence(source_file_stream_or_path, original_filename: str, examiner_name: str,
                    case_number: str, job_dir: Path) -> dict:
    """
    Execute Pipeline Step 1 & Step 2:
    - Save upload to original/ (read-only)
    - Compute original SHA-256
    - Copy to working/ and verify SHA-256 match
    - Generate initial chain_of_custody.txt and actions_log.txt
    """
    # Create required directory structure
    original_dir = job_dir / "original"
    working_dir = job_dir / "working"
    recovered_dir = job_dir / "recovered"
    autopsy_dir = job_dir / "autopsy"
    reports_dir = job_dir / "reports"

    for d in [original_dir, working_dir, recovered_dir, autopsy_dir, reports_dir]:
        d.mkdir(parents=True, exist_ok=True)

    sanitized_name = sanitize_filename(original_filename)
    original_path = original_dir / sanitized_name
    working_path = working_dir / sanitized_name

    # Clear read-only if file already exists in job directory
    if original_path.exists():
        try:
            os.chmod(original_path, stat.S_IWRITE | stat.S_IREAD)
            if os.name == "nt":
                subprocess.run(["attrib", "-R", str(original_path)], check=False, capture_output=True)
        except Exception:
            pass

    # Save to original/
    if isinstance(source_file_stream_or_path, (str, Path)):
        shutil.copy2(source_file_stream_or_path, original_path)
    else:
        # FileStorage or stream object
        source_file_stream_or_path.save(str(original_path))

    # Mark original file as read-only
    set_read_only(original_path)

    # Initial log setup
    log_action(job_dir, f"Evidence intake initialized for case '{case_number}' by examiner '{examiner_name}'")
    log_action(job_dir, f"Original evidence file saved to '{original_path}' with read-only protection (software attribute; a hardware or driver-level write blocker would be used on real evidence)")

    # Compute SHA-256 of original evidence
    original_sha256 = calculate_sha256(original_path)
    filesize = original_path.stat().st_size
    filesize_str = format_bytes(filesize)
    log_action(job_dir, f"Calculated original SHA-256: {original_sha256} ({filesize_str})")

    # Copy to working directory
    shutil.copy2(original_path, working_path)
    log_action(job_dir, f"Created working copy at '{working_path}'")

    # Compute and verify working copy SHA-256
    working_sha256 = calculate_sha256(working_path)
    if original_sha256 != working_sha256:
        err = f"CRITICAL INTEGRITY FAILURE: Working copy hash ({working_sha256}) does not match original ({original_sha256})"
        log_action(job_dir, err)
        raise ValueError(err)

    log_action(job_dir, f"Working copy integrity verified: SHA-256 match confirmed ({working_sha256})")

    # E01 validation if applicable
    ext = original_path.suffix.lower()
    e01_info = None
    if ext == ".e01":
        e01_info = verify_e01(working_path, job_dir)

    # Generate initial chain_of_custody.txt
    intake_time_utc = get_utc_now_str()
    custody_content = f"""================================================================================
CASE EVIDENCE CHAIN OF CUSTODY LOG (Modeled on ISO/IEC 27037 principles)
================================================================================
Case Number:         {case_number}
Examiner:            {examiner_name}
Intake Date/Time:    {intake_time_utc}
Original Filename:   {sanitized_name}
Evidence File Size:  {filesize} bytes ({filesize_str})
Acquisition SHA-256: {original_sha256}

Storage Locations:
  Original Evidence: {original_path.resolve()} (READ-ONLY PROTECTION - SOFTWARE ATTRIBUTE; A HARDWARE OR DRIVER-LEVEL WRITE BLOCKER WOULD BE USED ON REAL EVIDENCE)
  Working Replica:   {working_path.resolve()} (FOR ANALYSIS ONLY)

Integrity Verification at Intake:
  Original SHA-256:  {original_sha256}
  Working SHA-256:   {working_sha256}
  Intake Status:     MATCH VERIFIED - BIT-FOR-BIT COPY CONFIRMED

Action History:
  - [{intake_time_utc}] Evidence received, read-only protection (software attribute; a hardware or driver-level write blocker would be used on real evidence) applied, SHA-256 calculated.
  - [{intake_time_utc}] Verified working copy created; bitstream integrity confirmed.
"""
    if e01_info and e01_info.get("verified"):
        custody_content += f"  - [{intake_time_utc}] Expert Witness (E01) format verified via {e01_info['tool_used']}: {e01_info['details']}\n"

    with open(job_dir / "chain_of_custody.txt", "w", encoding="utf-8") as f:
        f.write(custody_content)

    # Save initial hashes to hashes.txt
    with open(job_dir / "hashes.txt", "w", encoding="utf-8") as f:
        f.write(f"CASE_NUMBER={case_number}\n")
        f.write(f"TIMESTAMP={intake_time_utc}\n")
        f.write(f"ORIGINAL_FILENAME={sanitized_name}\n")
        f.write(f"ORIGINAL_SHA256={original_sha256}\n")
        f.write(f"INITIAL_WORKING_SHA256={working_sha256}\n")

    return {
        "case_number": case_number,
        "examiner": examiner_name,
        "filename": sanitized_name,
        "original_path": original_path,
        "working_path": working_path,
        "filesize": filesize,
        "filesize_str": filesize_str,
        "sha256": original_sha256,
        "intake_time_utc": intake_time_utc,
        "e01_info": e01_info
    }
