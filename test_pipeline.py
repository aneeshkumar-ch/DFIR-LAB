import os
import sys
import json
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(r"D:\PROJECTS\ForensicsAnalyzer").resolve()))

import config
from app import run_analysis_pipeline, JOBS, JOBS_LOCK

def run_test():
    test_image = Path(r"D:\PROJECTS\ForensicsAnalyzer\test_images\practice_evidence.dd")
    if not test_image.exists():
        print(f"ERROR: Test image {test_image} does not exist!")
        sys.exit(1)

    job_id = "test_run_001"
    job_dir = config.JOBS_DIR / job_id
    
    # Clean previous run if any
    if job_dir.exists():
        import shutil, stat, subprocess
        def on_rm_error(func, path, exc_info):
            try:
                os.chmod(path, stat.S_IWRITE)
                subprocess.run(["attrib", "-R", str(path)], check=False, capture_output=True)
                func(path)
            except Exception:
                pass
        shutil.rmtree(job_dir, onerror=on_rm_error)
    job_dir.mkdir(parents=True, exist_ok=True)

    # Initialize in JOBS map
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "case_number": "CASE-TEST-014",
            "examiner": "Senior Forensics Specialist",
            "filename": test_image.name,
            "keywords_input": "flag, secret, password, confidential, CASE-TEST-014, admin",
            "status": "processing",
            "error": None,
            "engine_mode": "Evaluating...",
            "steps": {
                "intake": "pending",
                "custody": "pending",
                "partition": "pending",
                "listing": "pending",
                "recovery": "pending",
                "timeline": "pending",
                "keywords": "pending",
                "integrity": "pending",
                "report": "pending"
            }
        }

    # Staging copy
    temp_staging = job_dir / f"staging_{test_image.name}"
    import shutil
    shutil.copy2(test_image, temp_staging)

    print(f"[*] Starting full pipeline execution for Job {job_id}...")
    start_time = time.time()
    
    run_analysis_pipeline(
        job_id=job_id,
        temp_upload_path=temp_staging,
        original_filename=test_image.name,
        examiner_name="Senior Forensics Specialist",
        case_number="CASE-TEST-014",
        keywords_input="flag, secret, password, confidential, CASE-TEST-014, admin"
    )

    elapsed = time.time() - start_time
    print(f"[*] Pipeline completed in {elapsed:.2f} seconds.")

    with JOBS_LOCK:
        job_state = JOBS[job_id]

    print(f"\n========================================================")
    print(f" PIPELINE EXECUTION VERIFICATION SUMMARY")
    print(f"========================================================")
    print(f"Overall Status: {job_state.get('status')}")
    print(f"Engine Mode:    {job_state.get('engine_mode')}")
    print(f"Error (if any): {job_state.get('error')}")
    print(f"\nStep Statuses:")
    for step, st in job_state.get("steps", {}).items():
        print(f"  - {step.upper():<12}: {st}")

    # Check generated files
    expected_files = [
        job_dir / "original" / test_image.name,
        job_dir / "working" / test_image.name,
        job_dir / "chain_of_custody.txt",
        job_dir / "actions_log.txt",
        job_dir / "hashes.txt",
        job_dir / "file_listing.json",
        job_dir / "timeline.csv",
        job_dir / "timeline.json",
        job_dir / "keyword_hits.json",
        job_dir / "integrity.json",
        job_dir / "reports" / "report.html",
        job_dir / "reports" / "report.pdf",
        job_dir / "reports" / "case_package.zip"
    ]

    print(f"\nDeliverable Artifact Checks:")
    all_files_ok = True
    for ef in expected_files:
        exists = ef.exists() and ef.stat().st_size > 0
        status_sym = "[OK]" if exists else "[MISSING]"
        size_str = f"({ef.stat().st_size} bytes)" if exists else ""
        print(f"  {status_sym} {ef.name:<25} {size_str}")
        if not exists:
            all_files_ok = False

    # Check Integrity Result
    integ_data = job_state.get("integrity", {})
    print(f"\nIntegrity Audit Status: {integ_data.get('status')}")
    print(f"Acquisition SHA-256:    {integ_data.get('initial_sha256')}")
    print(f"Final Original SHA-256: {integ_data.get('final_original_sha256')}")
    print(f"Final Working SHA-256:  {integ_data.get('final_working_sha256')}")

    # Check Recovered Files & Mismatches
    recovered = job_state.get("recovered_files", [])
    mismatches = [f for f in recovered if f.get("extension_mismatch")]
    print(f"\nRecovered Files: {len(recovered)}")
    print(f"Extension Mismatches Detected: {len(mismatches)}")
    for m in mismatches:
        print(f"  [DECEPTION DETECTED] {m['filename']} -> {m['mismatch_details']}")

    # Check Keyword Hits
    kw_data = job_state.get("keywords", {})
    print(f"\nKeyword Hits Discovered: {kw_data.get('total_hits')}")
    for hit in kw_data.get("hits", [])[:5]:
        print(f"  Hit on '{hit['keyword']}' in {hit['target']} (Offset {hit['offset_hex']}): {hit['context']}")

    if not all_files_ok or job_state.get("status") != "completed":
        print("\nTEST FAILED: Some deliverables are missing or pipeline did not complete cleanly.")
        sys.exit(1)
    else:
        print("\nALL TEST CRITERIA PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_test()
