import os
import re
import shutil
import stat
import subprocess
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
import filetype

import config
from analyzer.intake import log_action, record_custody_action, calculate_sha256, format_bytes
from analyzer.tsk import run_subprocess_safe

# Magic byte signatures for deep forensic analysis
SIGNATURES = [
    (b"\xFF\xD8\xFF", "image/jpeg", [".jpg", ".jpeg"], "JPEG Image"),
    (b"\x89PNG\r\n\x1a\n", "image/png", [".png"], "PNG Image"),
    (b"GIF87a", "image/gif", [".gif"], "GIF Image (87a)"),
    (b"GIF89a", "image/gif", [".gif"], "GIF Image (89a)"),
    (b"BM", "image/bmp", [".bmp"], "Bitmap Image"),
    (b"%PDF-", "application/pdf", [".pdf"], "PDF Document"),
    (b"PK\x03\x04", "application/zip", [".zip", ".docx", ".xlsx", ".pptx", ".jar", ".apk"], "ZIP / Office OpenXML"),
    (b"7z\xBC\xAF\x27\x1C", "application/x-7z-compressed", [".7z"], "7-Zip Archive"),
    (b"Rar!\x1A\x07", "application/x-rar", [".rar"], "RAR Archive"),
    (b"\x1F\x8B", "application/gzip", [".gz", ".tgz"], "GZIP Archive"),
    (b"SQLite format 3\x00", "application/vnd.sqlite3", [".db", ".sqlite", ".sqlite3"], "SQLite 3 Database"),
    (b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1", "application/x-ole-storage", [".doc", ".xls", ".ppt", ".msg"], "Microsoft Compound OLE2 Document"),
    (b"\x7FELF", "application/x-executable", ["", ".bin", ".so", ".elf"], "ELF Executable / Library"),
    (b"MZ", "application/x-dosexec", [".exe", ".dll", ".sys", ".scr", ".com"], "DOS / Windows PE Executable"),
]

def detect_file_type_and_mismatch(filepath: Path) -> Dict[str, Any]:
    """
    Detect real file type by magic byte signature and filetype library.
    Flags extension mismatches (e.g., sensitive file renamed to conceal true identity).
    """
    file_ext = filepath.suffix.lower()
    file_size = filepath.stat().st_size

    if file_size == 0:
        return {
            "real_type": "empty/zero-byte",
            "mime": "inode/x-empty",
            "description": "Empty unallocated file record (0 bytes)",
            "extension_mismatch": False,
            "mismatch_details": "N/A",
            "is_corrupted_or_partial": True,
            "status_note": "Forensic limitation: Metadata entry exists but cluster allocation is zero"
        }

    # Read first 4096 bytes for header analysis
    with open(filepath, "rb") as f:
        header = f.read(4096)

    # Check for all zeroes
    if all(b == 0 for b in header[:min(file_size, 512)]):
        return {
            "real_type": "zero-filled",
            "mime": "application/x-zeros",
            "description": "Zeroed / unallocated block remnants",
            "extension_mismatch": False,
            "mismatch_details": "N/A",
            "is_corrupted_or_partial": True,
            "status_note": "Forensic limitation: File clusters were overwritten with zeroes"
        }

    detected_mime = None
    detected_desc = None
    allowed_extensions = []

    # 1. Custom signature matching
    for sig, mime, exts, desc in SIGNATURES:
        if header.startswith(sig):
            detected_mime = mime
            detected_desc = desc
            allowed_extensions = exts
            break

    # Check TAR magic at offset 257
    if not detected_mime and len(header) >= 262 and header[257:262] == b"ustar":
        detected_mime = "application/x-tar"
        detected_desc = "POSIX TAR Archive"
        allowed_extensions = [".tar"]

    # 2. Check filetype library if not matched
    if not detected_mime:
        try:
            kind = filetype.guess(filepath)
            if kind:
                detected_mime = kind.mime
                detected_desc = f"{kind.extension.upper()} ({kind.mime})"
                allowed_extensions = [f".{kind.extension.lower()}"]
        except Exception:
            pass

    # 3. Check for Plain Text (ASCII / UTF-8 text)
    if not detected_mime:
        is_text = True
        try:
            sample = header[:1024]
            # Must not contain null bytes or control chars except \t, \r, \n
            if b"\x00" in sample:
                is_text = False
            else:
                sample.decode("utf-8")
        except UnicodeDecodeError:
            is_text = False

        if is_text:
            detected_mime = "text/plain"
            detected_desc = "Plain Text / Document / Script"
            allowed_extensions = [".txt", ".log", ".csv", ".ini", ".cfg", ".py", ".json", ".md", ".xml", ".html", ".htm", ".sh"]

    if not detected_mime:
        detected_mime = "application/octet-stream"
        detected_desc = "Unknown Binary Stream / Fragment"
        allowed_extensions = []

    # Check for Extension Mismatch
    mismatch = False
    mismatch_details = "None"
    
    if allowed_extensions:
        if file_ext and file_ext not in allowed_extensions:
            mismatch = True
            mismatch_details = f"Renamed file detected! Extension '{file_ext}' does not match real format '{detected_desc}' (expected {', '.join(allowed_extensions)})"
        elif not file_ext and allowed_extensions and detected_mime != "text/plain":
            mismatch = True
            mismatch_details = f"File has no extension but is a valid '{detected_desc}'"

    return {
        "real_type": detected_mime,
        "mime": detected_mime,
        "description": detected_desc,
        "extension_mismatch": mismatch,
        "mismatch_details": mismatch_details,
        "is_corrupted_or_partial": False,
        "status_note": "Intact recovered file" if not mismatch else "Deception artifact: File extension disguised"
    }

def sanitize_recovered_filename(name: str) -> str:
    """Sanitize recovered filename to prevent path traversal or filesystem collisions."""
    base = Path(name).name
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', base)
    if not clean.strip():
        clean = "unnamed_recovered_file"
    return clean

def recover_files(image_path: Path, partitions: List[Dict[str, Any]], deleted_files_listing: List[Dict[str, Any]], job_dir: Path) -> List[Dict[str, Any]]:
    """
    Execute Pipeline Step 5:
    - Run tsk_recover for bulk extraction
    - Run icat for individual deleted inodes
    - Hash every recovered file with SHA-256
    - Inspect magic bytes and flag extension mismatches
    - Enforce safety: no execute permissions, warn on untrusted files
    """
    recovered_dir = job_dir / "recovered"
    recovered_dir.mkdir(parents=True, exist_ok=True)
    
    log_action(job_dir, "Beginning forensic file recovery process (tsk_recover + icat)")
    recovered_files_meta = []
    seen_hashes = set()

    # Part A: Run tsk_recover for each partition
    for part in partitions:
        offset = part.get("start_sector")
        cmd = [config.TSK_RECOVER_PATH, "-e"]  # -e: recover all files (allocated and unallocated)
        if offset and offset > 0:
            cmd.extend(["-o", str(offset)])
        
        # Output directory for this partition
        part_dir_name = f"partition_{offset}" if offset else "volume_direct"
        part_out_dir = recovered_dir / part_dir_name
        part_out_dir.mkdir(parents=True, exist_ok=True)
        
        cmd.extend([str(image_path), str(part_out_dir)])
        log_action(job_dir, f"Executing tsk_recover -e for partition offset {offset or '0'}")
        
        res = run_subprocess_safe(cmd, cwd=job_dir, timeout=300)
        log_action(job_dir, f"tsk_recover completed for offset {offset}: {res['stdout'].strip() or 'Finished'}")

    # Part B: Run icat for deleted inodes from fls listing
    target_deleted = deleted_files_listing[:100] if len(deleted_files_listing) > 100 else deleted_files_listing
    log_action(job_dir, f"Targeted deleted file recovery via icat for {len(target_deleted)} deleted entries (total: {len(deleted_files_listing)})")
    for item in target_deleted:
        inode = item.get("inode")
        if not inode or inode == "0":
            continue
        
        offset = item.get("partition_offset")
        raw_name = item.get("name", "unknown")
        clean_name = sanitize_recovered_filename(raw_name)
        
        out_filename = f"deleted_inode_{inode}_{clean_name}"
        out_filepath = recovered_dir / out_filename
        
        cmd = [config.ICAT_PATH]
        if offset and offset > 0:
            cmd.extend(["-o", str(offset)])
        # Inode string might contain attribute specifier, e.g. 123-128-3
        # icat takes inode and optional attribute
        # For NTFS, icat accepts 123-128-3 or just 123
        cmd.extend([str(image_path), str(inode)])
        
        try:
            with open(out_filepath, "wb") as outfile:
                proc = subprocess.run(cmd, stdout=outfile, stderr=subprocess.PIPE, timeout=30, check=False)
                
            # If empty and icat failed, clean up or note as empty
            if out_filepath.stat().st_size == 0 and proc.returncode != 0:
                out_filepath.unlink(missing_ok=True)
        except Exception as e:
            log_action(job_dir, f"icat error for inode {inode}: {e}")

    # Part C: Post-process all recovered files in recovered_dir
    log_action(job_dir, "Scanning recovered files: Computing SHA-256 and analyzing magic byte headers")
    
    for file_path in recovered_dir.rglob("*"):
        if not file_path.is_file():
            continue

        try:
            # Set non-executable permissions for forensic safety
            try:
                os.chmod(file_path, stat.S_IREAD | stat.S_IWRITE)
            except Exception:
                pass

            rel_path = file_path.relative_to(recovered_dir)
            filesize = file_path.stat().st_size
            file_sha256 = calculate_sha256(file_path) if filesize > 0 else "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            
            # Magic byte signature and mismatch analysis
            type_analysis = detect_file_type_and_mismatch(file_path)

            file_info = {
                "filename": file_path.name,
                "relative_path": str(rel_path).replace("\\", "/"),
                "size_bytes": filesize,
                "size_str": format_bytes(filesize),
                "sha256": file_sha256,
                "magic_desc": type_analysis["description"],
                "mime_type": type_analysis["mime"],
                "extension_mismatch": type_analysis["extension_mismatch"],
                "mismatch_details": type_analysis["mismatch_details"],
                "is_corrupted_or_partial": type_analysis["is_corrupted_or_partial"],
                "status_note": type_analysis["status_note"]
            }

            recovered_files_meta.append(file_info)
            if type_analysis["extension_mismatch"]:
                log_action(job_dir, f"[ALERT] Disguised file detected: {file_info['relative_path']} -> {type_analysis['mismatch_details']}")
                record_custody_action(job_dir, f"Deception detected: {file_info['relative_path']} is a {type_analysis['description']} disguised with extension '{file_path.suffix}'")
        except Exception as e:
            log_action(job_dir, f"Error processing recovered file {file_path}: {e}")

    # Summary logging
    mismatches = [f for f in recovered_files_meta if f["extension_mismatch"]]
    log_action(job_dir, f"Recovery complete: {len(recovered_files_meta)} file(s) recovered. Flagged {len(mismatches)} extension mismatch(es).")
    record_custody_action(job_dir, f"Recovery completed: {len(recovered_files_meta)} files recovered, {len(mismatches)} extension mismatches identified.")

    # Save to recovered_files.json
    with open(job_dir / "recovered_files.json", "w", encoding="utf-8") as f:
        import json
        json.dump(recovered_files_meta, f, indent=2)

    return recovered_files_meta
