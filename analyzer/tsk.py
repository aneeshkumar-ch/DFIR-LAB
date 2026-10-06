import os
import re
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

import config
from analyzer.intake import log_action, record_custody_action

def run_subprocess_safe(cmd_list: List[str], cwd: Optional[Path] = None, timeout: int = 120) -> Dict[str, Any]:
    """
    Run command securely via subprocess argument list (never shell=True) to prevent command injection.
    """
    try:
        proc = subprocess.run(
            cmd_list,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "success": proc.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds",
            "success": False
        }
    except Exception as e:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "success": False
        }

def inspect_partitions(image_path: Path, job_dir: Path) -> List[Dict[str, Any]]:
    """
    Run mmls to inspect disk partitions and parse partition table and offsets.
    If no partition table is found, returns a single default partition (offset=None).
    """
    log_action(job_dir, f"Analyzing partition table using mmls on '{image_path.name}'")
    cmd = [config.MMLS_PATH, str(image_path)]
    res = run_subprocess_safe(cmd, cwd=job_dir)
    
    partitions = []
    has_partition_table = False

    if res["success"] and res["stdout"]:
        lines = res["stdout"].splitlines()
        # Parse partition lines
        # Typical header: Slot Start End Length Description
        # e.g.: 006:  001       0000065664   0001736831   0001671168   Basic data partition
        # e.g.: 002:  000:000   0000000063   0000020479   0000020417   NTFS / exFAT (0x07)
        for line in lines:
            line_str = line.strip()
            # Skip headers / blank
            if not line_str or line_str.startswith("Units") or line_str.startswith("Offset") or "Slot" in line_str:
                continue
            
            # Match mmls table rows
            # Pattern: index: slot start end length description
            match = re.match(r'^\d+:\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)$', line_str)
            if match:
                slot, start, end, length, desc = match.groups()
                is_unallocated = "-------" in slot or "unallocated" in desc.lower()
                is_meta = "meta" in slot.lower() or "table" in desc.lower() or "header" in desc.lower()

                part_info = {
                    "slot": slot,
                    "start_sector": int(start),
                    "end_sector": int(end),
                    "length_sectors": int(length),
                    "size_bytes": int(length) * 512,
                    "description": desc.strip(),
                    "is_filesystem": not is_unallocated and not is_meta,
                    "raw_line": line_str
                }
                
                if part_info["is_filesystem"]:
                    has_partition_table = True
                    partitions.append(part_info)

    if not has_partition_table or len(partitions) == 0:
        log_action(job_dir, "No partition table detected by mmls. Analyzing image directly as a single filesystem (offset=None).")
        record_custody_action(job_dir, "Partition scan: Direct filesystem access (no volume system detected).")
        partitions = [{
            "slot": "Direct",
            "start_sector": 0,
            "end_sector": 0,
            "length_sectors": 0,
            "size_bytes": image_path.stat().st_size,
            "description": "Direct Unpartitioned Filesystem / Volume",
            "is_filesystem": True,
            "raw_line": "Direct volume access without partition table"
        }]
    else:
        log_action(job_dir, f"mmls detected {len(partitions)} allocated partition(s): " +
                   ", ".join([f"Offset {p['start_sector']} ({p['description']})" for p in partitions]))
        record_custody_action(job_dir, f"Partition table parsed: {len(partitions)} valid partition(s) identified.")

    return partitions

def inspect_filesystem(image_path: Path, partition: Dict[str, Any], job_dir: Path) -> Dict[str, Any]:
    """
    Run fsstat for a specific partition to extract filesystem metadata.
    """
    offset = partition.get("start_sector")
    cmd = [config.FSSTAT_PATH]
    if offset and offset > 0:
        cmd.extend(["-o", str(offset)])
    cmd.append(str(image_path))

    log_action(job_dir, f"Running fsstat for partition at offset {offset or '0 (direct)'}")
    res = run_subprocess_safe(cmd, cwd=job_dir)

    fs_info = {
        "offset": offset,
        "fs_type": "Unknown",
        "volume_name": "N/A",
        "volume_serial": "N/A",
        "block_size": "N/A",
        "total_range": "N/A",
        "root_directory": "N/A",
        "raw_summary": ""
    }

    if res["success"] and res["stdout"]:
        stdout = res["stdout"]
        fs_info["raw_summary"] = "\n".join(stdout.splitlines()[:30])
        
        # Regex parsers for common fsstat outputs (NTFS, FAT, EXT, etc.)
        fs_type_match = re.search(r'File System Type:\s*(.+)', stdout)
        if fs_type_match:
            fs_info["fs_type"] = fs_type_match.group(1).strip()
            
        vol_name_match = re.search(r'Volume Name:\s*(.+)', stdout)
        if vol_name_match:
            fs_info["volume_name"] = vol_name_match.group(1).strip()
            
        vol_serial_match = re.search(r'Volume Serial Number:\s*(.+)', stdout)
        if vol_serial_match:
            fs_info["volume_serial"] = vol_serial_match.group(1).strip()
            
        cluster_match = re.search(r'(Cluster Size|Block Size):\s*(\d+)', stdout)
        if cluster_match:
            fs_info["block_size"] = f"{cluster_match.group(2)} bytes"
            
        range_match = re.search(r'Total (?:Cluster|Block|Sector) Range:\s*(.+)', stdout)
        if range_match:
            fs_info["total_range"] = range_match.group(1).strip()
            
        root_match = re.search(r'Root Directory:\s*(.+)', stdout)
        if root_match:
            fs_info["root_directory"] = root_match.group(1).strip()

        log_action(job_dir, f"Filesystem identified: {fs_info['fs_type']} (Volume: {fs_info['volume_name']})")
    else:
        log_action(job_dir, f"fsstat warning for offset {offset}: {res['stderr'].strip() or 'No filesystem metadata detected'}")

    return fs_info

def parse_fls_output(fls_stdout: str, offset: Optional[int]) -> List[Dict[str, Any]]:
    """
    Parse fls -r output lines into structured entries.
    Flags deleted entries (containing '*').
    """
    entries = []
    lines = fls_stdout.splitlines()
    for line in lines:
        raw_line = line.strip()
        if not raw_line:
            continue

        # Check if line indicates deleted file
        # fls format examples:
        # +* r/r * 1234: filename.ext
        # +++ d/d 55: dir_name
        # r/- * 0: filename.jpg
        # v/v 1234: $UpCase
        is_deleted = "*" in raw_line
        
        # Regex to capture depth, file type flags, inode, and file name
        # Examples: "+++ r/r * 1234-128-3: secret.txt", "r/r 10: normal.txt"
        match = re.search(r'([+\*\s]*)\s*([a-z\-_]+/[a-z\-_]+)\s*(\*?)\s*(\d+(?:-\d+)*):?\s*(.+)$', raw_line, re.IGNORECASE)
        if match:
            prefix, ftype, star, inode_str, name = match.groups()
            depth = prefix.count("+")
            is_deleted = is_deleted or (star == "*")
            
            # Clean up filename
            clean_name = name.strip()
            
            entries.append({
                "partition_offset": offset,
                "type": ftype.strip(),
                "is_directory": "d" in ftype,
                "is_deleted": is_deleted,
                "inode": inode_str.strip(),
                "name": clean_name,
                "depth": depth,
                "raw": raw_line
            })
        else:
            # Fallback for unexpected line formats
            if ":" in raw_line:
                parts = raw_line.split(":", 1)
                entries.append({
                    "partition_offset": offset,
                    "type": "unknown",
                    "is_directory": False,
                    "is_deleted": is_deleted,
                    "inode": parts[0].strip().split()[-1] if parts[0].strip() else "0",
                    "name": parts[1].strip(),
                    "depth": 0,
                    "raw": raw_line
                })
    return entries

def list_files(image_path: Path, partitions: List[Dict[str, Any]], job_dir: Path) -> Dict[str, Any]:
    """
    Execute fls -r for all partitions, parse into JSON, flagging deleted files.
    """
    all_files = []
    deleted_files = []
    active_files = []

    for part in partitions:
        offset = part.get("start_sector")
        cmd = [config.FLS_PATH, "-r"]
        if offset and offset > 0:
            cmd.extend(["-o", str(offset)])
        cmd.append(str(image_path))

        log_action(job_dir, f"Listing files via fls -r for partition offset {offset or '0'}")
        res = run_subprocess_safe(cmd, cwd=job_dir, timeout=180)
        
        if res["stdout"]:
            part_files = parse_fls_output(res["stdout"], offset)
            for f in part_files:
                f["partition_desc"] = part.get("description", "Unknown")
                all_files.append(f)
                if f["is_deleted"]:
                    deleted_files.append(f)
                else:
                    active_files.append(f)
        else:
            log_action(job_dir, f"fls returned no entries or error for offset {offset}: {res['stderr']}")

    log_action(job_dir, f"File listing complete: Total={len(all_files)}, Active={len(active_files)}, Deleted={len(deleted_files)}")
    record_custody_action(job_dir, f"File listing extracted via TSK fls: {len(all_files)} total entries, {len(deleted_files)} deleted entries flagged.")

    listing_summary = {
        "total_files": len(all_files),
        "active_files_count": len(active_files),
        "deleted_files_count": len(deleted_files),
        "deleted_files": deleted_files,
        "all_files": all_files
    }

    # Save to file_listing.json
    with open(job_dir / "file_listing.json", "w", encoding="utf-8") as f:
        json.dump(listing_summary, f, indent=2)

    return listing_summary
