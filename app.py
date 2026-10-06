import os
import uuid
import json
import threading
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, abort
from werkzeug.utils import secure_filename

import config
from analyzer.intake import intake_evidence, log_action
from analyzer.tsk import inspect_partitions, inspect_filesystem, list_files
from analyzer.autopsy_cli import attempt_autopsy_ingest
from analyzer.recovery import recover_files
from analyzer.timeline import build_timeline
from analyzer.keywords import execute_keyword_search
from analyzer.integrity import verify_evidence_integrity
from analyzer.report import generate_html_report, generate_pdf_report, create_case_package_zip

app = Flask(
    __name__,
    template_folder=str(config.TEMPLATES_DIR),
    static_folder=str(config.STATIC_DIR)
)
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

# Thread-safe job store
JOBS = {}
JOBS_LOCK = threading.Lock()

def get_job_data(job_id: str) -> dict:
    with JOBS_LOCK:
        if job_id in JOBS:
            return JOBS[job_id].copy()

    # Attempt to restore persisted job from disk
    job_dir = config.JOBS_DIR / job_id
    if not job_dir.is_dir():
        return {}

    case_num = config.DEFAULT_CASE_NUMBER
    examiner = config.DEFAULT_EXAMINER
    fname = "evidence.raw"
    initial_sha = ""
    hashes_file = job_dir / "hashes.txt"
    if hashes_file.exists():
        try:
            for line in hashes_file.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("CASE_NUMBER="):
                    case_num = line.split("=", 1)[1].strip()
                elif line.startswith("ORIGINAL_FILENAME="):
                    fname = line.split("=", 1)[1].strip()
                elif line.startswith("ORIGINAL_SHA256="):
                    initial_sha = line.split("=", 1)[1].strip()
        except Exception:
            pass

    custody_file = job_dir / "chain_of_custody.txt"
    if custody_file.exists():
        try:
            for line in custody_file.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("Examiner:"):
                    examiner = line.split(":", 1)[1].strip()
        except Exception:
            pass

    is_complete = (job_dir / "reports" / "report.html").exists()

    job_state = {
        "job_id": job_id,
        "case_number": case_num,
        "examiner": examiner,
        "filename": fname,
        "keywords_input": "",
        "status": "completed" if is_complete else "processing",
        "error": None,
        "engine_mode": "The Sleuth Kit (TSK) Native Pipeline",
        "steps": {s: ("done" if is_complete else "pending") for s in [
            "intake", "custody", "partition", "listing", "recovery", "timeline", "keywords", "integrity", "report"
        ]},
        "intake": {
            "case_number": case_num,
            "examiner": examiner,
            "filename": fname,
            "original_path": str(job_dir / "original" / fname),
            "working_path": str(job_dir / "working" / fname),
            "sha256": initial_sha,
            "filesize_str": "N/A"
        }
    }

    # Load JSON artifacts if present
    for json_name, key in [
        ("file_listing.json", "file_listing"),
        ("recovered_files.json", "recovered_files"),
        ("timeline.json", "timeline"),
        ("keyword_hits.json", "keywords"),
        ("integrity.json", "integrity"),
    ]:
        p = job_dir / json_name
        if p.exists():
            try:
                job_state[key] = json.loads(p.read_text(encoding="utf-8"))
                if key == "file_listing":
                    job_state["deleted_files"] = job_state[key].get("deleted_files", [])
            except Exception:
                pass

    with JOBS_LOCK:
        JOBS[job_id] = job_state

    return job_state.copy()

def update_job_step(job_id: str, step_name: str, step_status: str, extra: dict = None) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["steps"][step_name] = step_status
            if extra:
                JOBS[job_id].update(extra)

def run_analysis_pipeline(job_id: str, temp_upload_path: Path, original_filename: str,
                          examiner_name: str, case_number: str, keywords_input: str) -> None:
    """
    Background worker executing the complete 9-phase automated forensic pipeline.
    """
    job_dir = config.JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Phase 1: Intake & Read-Only Protection
        update_job_step(job_id, "intake", "running")
        intake_info = intake_evidence(
            source_file_stream_or_path=temp_upload_path,
            original_filename=original_filename,
            examiner_name=examiner_name,
            case_number=case_number,
            job_dir=job_dir
        )
        update_job_step(job_id, "intake", "done", {"intake": intake_info})

        # Phase 2: Chain of Custody & Action Logging initialized
        update_job_step(job_id, "custody", "done")

        working_image_path = Path(intake_info["working_path"])

        # Autopsy Automation Evaluation
        log_action(job_dir, "Evaluating Autopsy command-line ingest engine capabilities")
        autopsy_res = attempt_autopsy_ingest(working_image_path, job_dir, case_number)
        engine_mode = autopsy_res.get("engine_mode", "The Sleuth Kit (TSK) Native Pipeline")
        with JOBS_LOCK:
            JOBS[job_id]["engine_mode"] = engine_mode
            JOBS[job_id]["autopsy_result"] = autopsy_res

        # Phase 3: Partition & Filesystem Architecture
        update_job_step(job_id, "partition", "running")
        partitions = inspect_partitions(working_image_path, job_dir)
        filesystems = []
        for part in partitions:
            fs_info = inspect_filesystem(working_image_path, part, job_dir)
            filesystems.append(fs_info)
        update_job_step(job_id, "partition", "done", {"partitions": partitions, "filesystems": filesystems})

        # Phase 4: File Listing & Deleted Inode Identification
        update_job_step(job_id, "listing", "running")
        listing_info = list_files(working_image_path, partitions, job_dir)
        update_job_step(job_id, "listing", "done", {
            "file_listing": listing_info,
            "deleted_files": listing_info.get("deleted_files", [])
        })

        # Phase 5: File Recovery & Magic Byte Type Mismatch Analysis
        update_job_step(job_id, "recovery", "running")
        recovered_meta = recover_files(
            image_path=working_image_path,
            partitions=partitions,
            deleted_files_listing=listing_info.get("deleted_files", []),
            job_dir=job_dir
        )
        update_job_step(job_id, "recovery", "done", {"recovered_files": recovered_meta})

        # Phase 6: MACB Timeline Compilation (fls -m + mactime)
        update_job_step(job_id, "timeline", "running")
        timeline_info = build_timeline(working_image_path, partitions, job_dir)
        update_job_step(job_id, "timeline", "done", {"timeline": timeline_info})

        # Phase 7: Forensic Keyword Content Search
        update_job_step(job_id, "keywords", "running")
        keyword_hits = execute_keyword_search(keywords_input, working_image_path, job_dir)
        update_job_step(job_id, "keywords", "done", {"keywords": keyword_hits})

        # Phase 8: Post-Analysis Cryptographic Integrity Verification (PASS / FAIL)
        update_job_step(job_id, "integrity", "running")
        integrity_audit = verify_evidence_integrity(intake_info, job_dir)
        update_job_step(job_id, "integrity", "done", {"integrity": integrity_audit})

        # Phase 9: Report Generation & Case Packaging
        update_job_step(job_id, "report", "running")
        
        # Prepare full job payload for reports
        with JOBS_LOCK:
            current_job_state = JOBS[job_id].copy()

        generate_html_report(current_job_state, job_dir)
        generate_pdf_report(current_job_state, job_dir)
        create_case_package_zip(job_dir)
        
        update_job_step(job_id, "report", "done")

        with JOBS_LOCK:
            JOBS[job_id]["status"] = "completed"
            
        log_action(job_dir, "Forensic pipeline successfully finished. Deliverables ready.")

    except Exception as e:
        log_action(job_dir, f"[FATAL ERROR] Analysis pipeline encountered an exception: {e}")
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "failed"
                JOBS[job_id]["error"] = str(e)
    finally:
        # Clean up temporary staging upload file
        if temp_upload_path and temp_upload_path.exists():
            try:
                temp_upload_path.unlink()
            except Exception:
                pass


@app.route("/", methods=["GET"])
def index():
    """Render the evidence upload intake page."""
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload():
    """Handle forensic evidence upload and launch background worker."""
    if "evidence_file" not in request.files:
        return redirect(url_for("index"))

    file_obj = request.files["evidence_file"]
    if not file_obj or not file_obj.filename:
        return redirect(url_for("index"))

    filename = secure_filename(file_obj.filename)
    ext = Path(filename).suffix.lower()

    if ext not in config.ALLOWED_EXTENSIONS:
        return f"Unsupported file type '{ext}'. Allowed formats: {', '.join(config.ALLOWED_EXTENSIONS)}", 400

    examiner = request.form.get("examiner", config.DEFAULT_EXAMINER).strip() or config.DEFAULT_EXAMINER
    case_number = request.form.get("case_number", config.DEFAULT_CASE_NUMBER).strip() or config.DEFAULT_CASE_NUMBER
    keywords = request.form.get("keywords", "").strip()

    job_id = uuid.uuid4().hex[:12]
    job_dir = config.JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save to temporary staging path
    temp_upload_path = job_dir / f"staging_{filename}"
    file_obj.save(str(temp_upload_path))

    # Initialize job state
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "case_number": case_number,
            "examiner": examiner,
            "filename": filename,
            "keywords_input": keywords,
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

    # Start background analysis thread
    t = threading.Thread(
        target=run_analysis_pipeline,
        args=(job_id, temp_upload_path, filename, examiner, case_number, keywords),
        daemon=True
    )
    t.start()

    return redirect(url_for("job_view", job_id=job_id))


@app.route("/job/<job_id>", methods=["GET"])
def job_view(job_id: str):
    """Render live job status page."""
    job = get_job_data(job_id)
    if not job:
        abort(404)
    return render_template("job.html", job_id=job_id, job=job)


@app.route("/api/job/<job_id>/status", methods=["GET"])
def api_job_status(job_id: str):
    """Return live JSON progress and action log."""
    job = get_job_data(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Read latest action log content
    action_log = ""
    log_file = config.JOBS_DIR / job_id / "actions_log.txt"
    if log_file.exists():
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                action_log = f.read()
        except Exception:
            pass

    return jsonify({
        "job_id": job_id,
        "status": job.get("status"),
        "error": job.get("error"),
        "steps": job.get("steps"),
        "engine_mode": job.get("engine_mode"),
        "action_log": action_log
    })


@app.route("/job/<job_id>/report", methods=["GET"])
def view_report(job_id: str):
    """Display generated HTML report."""
    report_file = config.JOBS_DIR / job_id / "reports" / "report.html"
    if not report_file.exists():
        return "Report is still compiling or job failed.", 404
    return send_file(report_file, mimetype="text/html")


@app.route("/job/<job_id>/download/pdf", methods=["GET"])
def download_pdf(job_id: str):
    """Download official PDF forensic report."""
    pdf_file = config.JOBS_DIR / job_id / "reports" / "report.pdf"
    if not pdf_file.exists():
        return "PDF report is not available.", 404
    return send_file(pdf_file, as_attachment=True, download_name=f"Forensic_Report_{job_id}.pdf")


@app.route("/job/<job_id>/download/package", methods=["GET"])
def download_package(job_id: str):
    """Download bundled case archive ZIP."""
    pkg_file = config.JOBS_DIR / job_id / "reports" / "case_package.zip"
    if not pkg_file.exists():
        return "Case package archive is not available.", 404
    return send_file(pkg_file, as_attachment=True, download_name=f"Case_Package_{job_id}.zip")


@app.route("/job/<job_id>/download/timeline", methods=["GET"])
def download_timeline(job_id: str):
    """Download MACB timeline CSV."""
    timeline_file = config.JOBS_DIR / job_id / "timeline.csv"
    if not timeline_file.exists():
        return "Timeline CSV is not available.", 404
    return send_file(timeline_file, as_attachment=True, download_name=f"Timeline_{job_id}.csv")


@app.route("/job/<job_id>/download/custody", methods=["GET"])
def download_custody(job_id: str):
    """Download Chain of Custody text document."""
    custody_file = config.JOBS_DIR / job_id / "chain_of_custody.txt"
    if not custody_file.exists():
        return "Chain of Custody is not available.", 404
    return send_file(custody_file, as_attachment=True, download_name=f"Chain_Of_Custody_{job_id}.txt")


if __name__ == "__main__":
    print(f"================================================================")
    print(f" Digital Forensics Analyzer -- BCSSL Lab 14 (CASE-TEST-014)")
    print(f" Binding to: http://{config.HOST}:{config.PORT}")
    print(f" Evidence Directory: {config.JOBS_DIR}")
    print(f" TSK Binaries:       {config.TSK_BIN_DIR}")
    print(f" Autopsy Bin:        {config.AUTOPSY_BIN}")
    print(f"================================================================")
    # Binds strictly to 127.0.0.1 for forensic security
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)
