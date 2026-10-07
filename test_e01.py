import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import config
from app import run_analysis_pipeline, JOBS, JOBS_LOCK

def test_e01_pipeline():
    e01_path = BASE_DIR / "test_images" / "2020DFImage.E01"
    if not e01_path.exists():
        print(f"Skipping E01 test: {e01_path} not found.")
        return

    job_id = "test_e01_001"
    job_dir = config.JOBS_DIR / job_id
    if job_dir.exists():
        import shutil, stat, subprocess
        def on_rm_error(func, path, exc_info):
            try:
                os.chmod(path, stat.S_IWRITE)
                if os.name == "nt":
                    subprocess.run(["attrib", "-R", str(path)], check=False, capture_output=True)
                func(path)
            except Exception:
                pass
        shutil.rmtree(job_dir, onerror=on_rm_error)
    job_dir.mkdir(parents=True, exist_ok=True)

    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "case_number": "CASE-TEST-014",
            "examiner": "Senior Forensics Specialist",
            "filename": e01_path.name,
            "keywords_input": "BillyBob, Fred, Russell, password, secret",
            "status": "processing",
            "error": None,
            "engine_mode": "Evaluating...",
            "steps": {s: "pending" for s in [
                "intake", "custody", "partition", "listing", "recovery", "timeline", "keywords", "integrity", "report"
            ]}
        }

    temp_staging = job_dir / f"staging_{e01_path.name}"
    import shutil
    print(f"[*] Staging 309MB E01 image...")
    shutil.copy2(e01_path, temp_staging)

    print(f"[*] Running automated pipeline on authentic E01 image...")
    t0 = time.time()
    run_analysis_pipeline(
        job_id=job_id,
        temp_upload_path=temp_staging,
        original_filename=e01_path.name,
        examiner_name="Senior Forensics Specialist",
        case_number="CASE-TEST-014",
        keywords_input="BillyBob, Fred, Russell, password, secret"
    )
    t1 = time.time()
    print(f"[*] E01 pipeline completed in {t1 - t0:.2f} seconds.")

    with JOBS_LOCK:
        state = JOBS[job_id]

    print(f"\nStatus: {state.get('status')}")
    print(f"Engine Mode: {state.get('engine_mode')}")
    print(f"Error: {state.get('error')}")
    print(f"Integrity Audit: {state.get('integrity', {}).get('status')}")
    print(f"Partitions: {len(state.get('partitions', []))}")
    print(f"Deleted Inodes: {len(state.get('deleted_files', []))}")
    print(f"Recovered Files: {len(state.get('recovered_files', []))}")
    print(f"Keyword Hits: {state.get('keywords', {}).get('total_hits')}")

if __name__ == "__main__":
    test_e01_pipeline()
