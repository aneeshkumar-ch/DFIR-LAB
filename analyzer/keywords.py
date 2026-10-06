import os
import re
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Set

import config
from analyzer.intake import log_action, record_custody_action

DEFAULT_FORENSIC_KEYWORDS = [
    "CASE-TEST-014",
    "password",
    "secret",
    "confidential",
    "admin",
    "flag",
    "evidence"
]

def parse_keywords(input_str: str) -> List[str]:
    """Parse comma/newline/semicolon delimited keyword string into list of unique search terms."""
    if not input_str or not input_str.strip():
        return DEFAULT_FORENSIC_KEYWORDS.copy()
    
    raw_terms = re.split(r'[,;\n\r]+', input_str)
    cleaned = [t.strip() for t in raw_terms if t.strip()]
    if not cleaned:
        return DEFAULT_FORENSIC_KEYWORDS.copy()
    
    # Remove duplicates while preserving order
    seen = set()
    result = []
    for item in cleaned:
        low = item.lower()
        if low not in seen:
            seen.add(low)
            result.append(item)
    return result

def sanitize_context_snippet(raw_bytes: bytes) -> str:
    """Convert raw surrounding bytes into printable ASCII preview text."""
    chars = []
    for b in raw_bytes:
        if 32 <= b <= 126:
            chars.append(chr(b))
        elif b in (9, 10, 13):
            chars.append(" ")
        else:
            chars.append(".")
    return "".join(chars).strip()

def search_recovered_files(keywords: List[str], recovered_dir: Path, max_file_size: int = 50 * 1024 * 1024) -> List[Dict[str, Any]]:
    """
    Search all recovered files for keywords (case-insensitive).
    Returns list of hit records with relative file path, byte offset, and preview snippet.
    """
    hits = []
    if not recovered_dir.exists():
        return hits

    for file_path in recovered_dir.rglob("*"):
        if not file_path.is_file():
            continue
        
        try:
            size = file_path.stat().st_size
            if size == 0 or size > max_file_size:
                continue

            rel_path = str(file_path.relative_to(recovered_dir)).replace("\\", "/")
            
            with open(file_path, "rb") as f:
                data = f.read()

            for kw in keywords:
                # Search ASCII (case-insensitive)
                kw_lower_bytes = kw.lower().encode("utf-8", errors="ignore")
                data_lower = data.lower()
                
                start = 0
                while True:
                    idx = data_lower.find(kw_lower_bytes, start)
                    if idx == -1:
                        break
                    
                    # Extract surrounding context
                    ctx_start = max(0, idx - 30)
                    ctx_end = min(len(data), idx + len(kw_lower_bytes) + 30)
                    snippet = sanitize_context_snippet(data[ctx_start:ctx_end])

                    hits.append({
                        "source": "Recovered File",
                        "target": rel_path,
                        "keyword": kw,
                        "offset_dec": idx,
                        "offset_hex": hex(idx),
                        "sector": idx // 512,
                        "context": snippet
                    })
                    
                    start = idx + len(kw_lower_bytes)
                    if len(hits) >= 1000:
                        break
        except Exception:
            continue

    return hits

def search_raw_image(keywords: List[str], image_path: Path, max_hits_per_kw: int = 150) -> List[Dict[str, Any]]:
    """
    Search raw disk image for keywords using streaming chunks.
    Searches both ASCII and UTF-16LE representations.
    """
    hits = []
    if not image_path.exists():
        return hits

    kw_patterns = []
    for kw in keywords:
        ascii_b = kw.lower().encode("ascii", errors="ignore")
        utf16_b = kw.lower().encode("utf-16le", errors="ignore")
        kw_patterns.append((kw, ascii_b, utf16_b))

    chunk_size = 2 * 1024 * 1024  # 2 MB chunks
    overlap = 512  # Overlap to prevent boundary misses
    
    file_size = image_path.stat().st_size
    current_offset = 0

    counts_per_kw = {kw: 0 for kw in keywords}

    with open(image_path, "rb") as f:
        while current_offset < file_size:
            f.seek(current_offset)
            chunk = f.read(chunk_size + overlap)
            if not chunk:
                break

            chunk_lower = chunk.lower()

            for kw, ascii_b, utf16_b in kw_patterns:
                if counts_per_kw[kw] >= max_hits_per_kw:
                    continue

                # Search ASCII
                pos = 0
                while pos < len(chunk_lower):
                    idx = chunk_lower.find(ascii_b, pos)
                    if idx == -1:
                        break
                    
                    abs_offset = current_offset + idx
                    ctx_start = max(0, idx - 30)
                    ctx_end = min(len(chunk), idx + len(ascii_b) + 30)
                    snippet = sanitize_context_snippet(chunk[ctx_start:ctx_end])

                    hits.append({
                        "source": "Raw Disk Image",
                        "target": image_path.name,
                        "keyword": kw,
                        "offset_dec": abs_offset,
                        "offset_hex": hex(abs_offset),
                        "sector": abs_offset // 512,
                        "encoding": "ASCII",
                        "context": snippet
                    })
                    counts_per_kw[kw] += 1
                    pos = idx + len(ascii_b)
                    if counts_per_kw[kw] >= max_hits_per_kw:
                        break

                # Search UTF-16LE
                if counts_per_kw[kw] < max_hits_per_kw:
                    pos = 0
                    while pos < len(chunk_lower):
                        idx = chunk_lower.find(utf16_b, pos)
                        if idx == -1:
                            break
                        
                        abs_offset = current_offset + idx
                        ctx_start = max(0, idx - 30)
                        ctx_end = min(len(chunk), idx + len(utf16_b) + 30)
                        snippet = sanitize_context_snippet(chunk[ctx_start:ctx_end])

                        hits.append({
                            "source": "Raw Disk Image",
                            "target": image_path.name,
                            "keyword": kw,
                            "offset_dec": abs_offset,
                            "offset_hex": hex(abs_offset),
                            "sector": abs_offset // 512,
                            "encoding": "UTF-16LE",
                            "context": snippet
                        })
                        counts_per_kw[kw] += 1
                        pos = idx + len(utf16_b)
                        if counts_per_kw[kw] >= max_hits_per_kw:
                            break

            current_offset += chunk_size

    return hits

def execute_keyword_search(keywords_input: str, image_path: Path, job_dir: Path) -> Dict[str, Any]:
    """
    Execute Pipeline Step 7:
    - Parse search terms
    - Search recovered files
    - Search raw disk image (ASCII & UTF-16LE)
    - Save results to keyword_hits.json
    """
    keywords = parse_keywords(keywords_input)
    log_action(job_dir, f"Starting forensic keyword search for terms: {', '.join(keywords)}")

    # Search recovered directory
    recovered_dir = job_dir / "recovered"
    recovered_hits = search_recovered_files(keywords, recovered_dir)
    log_action(job_dir, f"Recovered files keyword search found {len(recovered_hits)} hit(s)")

    # Search raw image
    raw_hits = search_raw_image(keywords, image_path)
    log_action(job_dir, f"Raw image keyword search found {len(raw_hits)} hit(s)")

    all_hits = recovered_hits + raw_hits

    record_custody_action(job_dir, f"Keyword search completed for [{', '.join(keywords)}]: {len(all_hits)} total hits discovered.")

    summary = {
        "keywords_searched": keywords,
        "total_hits": len(all_hits),
        "recovered_files_hits_count": len(recovered_hits),
        "raw_image_hits_count": len(raw_hits),
        "hits": all_hits
    }

    with open(job_dir / "keyword_hits.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary
