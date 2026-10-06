import os
import re
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import config
from analyzer.intake import log_action, record_custody_action
from analyzer.tsk import run_subprocess_safe

def generate_bodyfile(image_path: Path, partitions: List[Dict[str, Any]], job_dir: Path) -> Path:
    """
    Run fls -r -m on each partition to create a standardized Sleuth Kit body file.
    Format: MD5|name|inode|mode_as_string|UID|GID|size|atime|mtime|ctime|crtime
    """
    bodyfile_path = job_dir / "bodyfile.txt"
    log_action(job_dir, "Generating Sleuth Kit body file (fls -r -m)")

    with open(bodyfile_path, "w", encoding="utf-8", errors="replace") as outfile:
        for part in partitions:
            offset = part.get("start_sector")
            desc = part.get("description", "Volume")
            clean_tag = re.sub(r'[^a-zA-Z0-9_]', '_', desc).strip('_')
            mount_point = f"/vol_{offset}" if (offset and offset > 0) else f"/{clean_tag or 'root'}"
            
            cmd = [config.FLS_PATH, "-r", "-m", mount_point]
            if offset and offset > 0:
                cmd.extend(["-o", str(offset)])
            cmd.append(str(image_path))

            res = run_subprocess_safe(cmd, cwd=job_dir, timeout=180)
            if res["stdout"]:
                outfile.write(res["stdout"])
                if not res["stdout"].endswith("\n"):
                    outfile.write("\n")

    return bodyfile_path

def parse_bodyfile_python(bodyfile_path: Path) -> List[Dict[str, Any]]:
    """
    Fallback pure-Python parser for TSK body file in case Perl / mactime is unavailable.
    Outputs normalized timeline events.
    """
    events = []
    if not bodyfile_path.exists():
        return events

    with open(bodyfile_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) < 11:
                continue
            
            md5, name, inode, mode, uid, gid, size, atime, mtime, ctime, crtime = parts[:11]
            try:
                size_int = int(size)
            except ValueError:
                size_int = 0

            # Map time attributes to MACB flags
            times_map = {}
            for t_val, flag in [(mtime, "m"), (atime, "a"), (ctime, "c"), (crtime, "b")]:
                try:
                    t_int = int(t_val)
                    if t_int > 0:
                        times_map.setdefault(t_int, []).append(flag)
                except ValueError:
                    pass

            for t_sec, flags in times_map.items():
                try:
                    dt = datetime.fromtimestamp(t_sec, tz=timezone.utc)
                    dt_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    # Construct MACB representation
                    macb_str = (
                        ("m" if "m" in flags else ".") +
                        ("a" if "a" in flags else ".") +
                        ("c" if "c" in flags else ".") +
                        ("b" if "b" in flags else ".")
                    )
                    events.append({
                        "datetime": dt_str,
                        "epoch": t_sec,
                        "size": size_int,
                        "type": macb_str,
                        "mode": mode,
                        "uid": uid,
                        "gid": gid,
                        "meta": inode,
                        "filename": name
                    })
                except Exception:
                    continue

    events.sort(key=lambda x: x["epoch"])
    return events

def run_mactime(bodyfile_path: Path, job_dir: Path) -> Path:
    """
    Execute mactime.pl using Perl to convert body file into CSV timeline.
    Falls back to internal Python parser if Perl or mactime.pl fails.
    """
    timeline_csv = job_dir / "timeline.csv"
    log_action(job_dir, "Executing mactime to compile MACB timeline CSV")

    success = False
    if os.path.isfile(config.MACTIME_SCRIPT):
        cmd = [config.PERL_PATH, config.MACTIME_SCRIPT, "-b", str(bodyfile_path), "-d", "-y"]
        res = run_subprocess_safe(cmd, cwd=job_dir, timeout=120)
        if res["success"] and res["stdout"]:
            with open(timeline_csv, "w", encoding="utf-8") as f:
                f.write(res["stdout"])
            success = True
            log_action(job_dir, "mactime completed successfully via Perl")

    if not success:
        log_action(job_dir, "Using built-in Python timeline compiler fallback for body file")
        events = parse_bodyfile_python(bodyfile_path)
        with open(timeline_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Size", "Type", "Mode", "UID", "GID", "Meta", "File Name"])
            for ev in events:
                writer.writerow([ev["datetime"], ev["size"], ev["type"], ev["mode"], ev["uid"], ev["gid"], ev["meta"], ev["filename"]])
        log_action(job_dir, f"Python timeline compiler generated {len(events)} events")

    record_custody_action(job_dir, "MACB timeline generated and saved to timeline.csv.")
    return timeline_csv

def build_timeline(image_path: Path, partitions: List[Dict[str, Any]], job_dir: Path) -> Dict[str, Any]:
    """
    Execute Pipeline Step 6:
    - Generate bodyfile.txt
    - Generate timeline.csv via mactime
    - Parse into structured list and activity aggregates for chart rendering
    """
    bodyfile_path = generate_bodyfile(image_path, partitions, job_dir)
    timeline_csv = run_mactime(bodyfile_path, job_dir)

    # Parse CSV into structured event objects and aggregate counts
    events = []
    date_counts = {}

    if timeline_csv.exists():
        with open(timeline_csv, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Standard mactime header: Date,Size,Type,Mode,UID,GID,Meta,File Name
                dt_str = row.get("Date") or row.get("date") or ""
                ev = {
                    "datetime": dt_str,
                    "size": row.get("Size") or row.get("size") or "0",
                    "type": row.get("Type") or row.get("type") or "....",
                    "mode": row.get("Mode") or row.get("mode") or "",
                    "uid": row.get("UID") or row.get("uid") or "0",
                    "gid": row.get("GID") or row.get("gid") or "0",
                    "meta": row.get("Meta") or row.get("meta") or "",
                    "filename": row.get("File Name") or row.get("file name") or ""
                }
                events.append(ev)

                # Aggregate by Day (YYYY-MM-DD) for chart (excluding zero timestamps)
                day = dt_str.split("T")[0] if "T" in dt_str else dt_str.split(" ")[0]
                if day and len(day) == 10 and not day.startswith("0000"):
                    date_counts[day] = date_counts.get(day, 0) + 1

    # Sort chronological day labels
    sorted_days = sorted(date_counts.keys())
    chart_data = {
        "labels": sorted_days,
        "counts": [date_counts[d] for d in sorted_days]
    }

    log_action(job_dir, f"Timeline parsed: {len(events)} total timestamp events across {len(sorted_days)} active dates")

    summary = {
        "total_events": len(events),
        "events": events[:2000],  # Cap at 2000 for browser rendering performance
        "total_untruncated": len(events),
        "chart_data": chart_data
    }

    with open(job_dir / "timeline.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary
