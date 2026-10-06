import os
import json
from pathlib import Path
from typing import Dict, Any

from analyzer.intake import calculate_sha256, log_action, record_custody_action, get_utc_now_str

def verify_evidence_integrity(intake_data: Dict[str, Any], job_dir: Path) -> Dict[str, Any]:
    """
    Execute Pipeline Step 8:
    Re-hash the working copy and the original evidence, confirming neither changed.
    Generates cryptographic audit trail and reports PASS or FAIL.
    """
    original_path = Path(intake_data["original_path"])
    working_path = Path(intake_data["working_path"])
    initial_sha256 = intake_data["sha256"]

    log_action(job_dir, "Beginning post-analysis cryptographic integrity verification")

    final_original_sha256 = calculate_sha256(original_path)
    final_working_sha256 = calculate_sha256(working_path)

    original_intact = (final_original_sha256 == initial_sha256)
    working_intact = (final_working_sha256 == initial_sha256)
    both_match = (final_original_sha256 == final_working_sha256)

    status = "PASS" if (original_intact and working_intact and both_match) else "FAIL"
    now_utc = get_utc_now_str()

    result = {
        "status": status,
        "verified": (status == "PASS"),
        "timestamp_utc": now_utc,
        "initial_sha256": initial_sha256,
        "final_original_sha256": final_original_sha256,
        "final_working_sha256": final_working_sha256,
        "original_unaltered": original_intact,
        "working_unaltered": working_intact,
        "message": (
            "CRYPTOGRAPHIC INTEGRITY VERIFICATION SUCCEEDED: "
            "Neither the original evidence nor the working copy was altered during examination. "
            "Forensic read-only protection (software attribute; a hardware or driver-level write blocker would be used on real evidence) and custody principles adhered to strictly."
            if status == "PASS" else
            "CRITICAL WARNING: Integrity violation detected! Hashes differ from intake acquisition baseline."
        )
    }

    log_action(job_dir, f"Integrity check completed: Result={status}")
    log_action(job_dir, f"Original Hash: {final_original_sha256} (Match: {original_intact})")
    log_action(job_dir, f"Working Hash:  {final_working_sha256} (Match: {working_intact})")

    custody_entry = f"""
================================================================================
FINAL INTEGRITY VERIFICATION AUDIT
================================================================================
Verification Timestamp: {now_utc}
Acquisition SHA-256:    {initial_sha256}
Final Original SHA-256: {final_original_sha256} [Match: {'YES' if original_intact else 'NO'}]
Final Working SHA-256:  {final_working_sha256} [Match: {'YES' if working_intact else 'NO'}]
Overall Integrity Audit: {status}
Audit Note: {result['message']}
================================================================================
"""
    with open(job_dir / "chain_of_custody.txt", "a", encoding="utf-8") as f:
        f.write(custody_entry)

    # Append to hashes.txt
    with open(job_dir / "hashes.txt", "a", encoding="utf-8") as f:
        f.write(f"FINAL_VERIFICATION_TIMESTAMP={now_utc}\n")
        f.write(f"FINAL_ORIGINAL_SHA256={final_original_sha256}\n")
        f.write(f"FINAL_WORKING_SHA256={final_working_sha256}\n")
        f.write(f"INTEGRITY_AUDIT_RESULT={status}\n")

    # Save integrity.json
    with open(job_dir / "integrity.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result
