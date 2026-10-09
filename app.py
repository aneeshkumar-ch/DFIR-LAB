import os
import stat
import time
import shutil
import uuid
import json
import threading
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, abort, session
from werkzeug.utils import secure_filename

import config
from analyzer.intake import intake_evidence, log_action, format_bytes
from analyzer.tsk import inspect_partitions, inspect_filesystem, list_files
from analyzer.autopsy_cli import attempt_autopsy_ingest
from analyzer.recovery import recover_files
from analyzer.timeline import build_timeline
from analyzer.keywords import execute_keyword_search
from analyzer.integrity import verify_evidence_integrity
from analyzer.report import generate_html_report, generate_pdf_report, create_case_package_zip

def safe_remove_file(filepath: Path) -> int:
    """Safely delete a file even if marked read-only, returning bytes freed."""
    if not filepath.exists() or not filepath.is_file():
        return 0
    try:
        size = filepath.stat().st_size
        os.chmod(filepath, stat.S_IWRITE | stat.S_IREAD)
        if os.name == "nt":
            import subprocess
            subprocess.run(["attrib", "-R", str(filepath)], check=False, capture_output=True)
        filepath.unlink()
        return size
    except Exception as e:
        print(f"Warning: Could not remove {filepath}: {e}")
        return 0

def safe_remove_tree(dirpath: Path) -> int:
    """Safely delete a directory tree, returning bytes freed."""
    if not dirpath.exists() or not dirpath.is_dir():
        return 0
    total_freed = 0
    try:
        for root, dirs, files in os.walk(dirpath, topdown=False):
            for f in files:
                total_freed += safe_remove_file(Path(root) / f)
            for d in dirs:
                try:
                    (Path(root) / d).rmdir()
                except Exception:
                    pass
        dirpath.rmdir()
    except Exception as e:
        print(f"Warning: Could not remove directory {dirpath}: {e}")
    return total_freed

def purge_working_copy(job_dir: Path) -> int:
    """
    Mechanism 1: Immediately purge working replica and autopsy cache.
    Reclaims 50%+ disk space while leaving reports, logs, and recovered files intact.
    """
    bytes_freed = 0
    working_dir = job_dir / "working"
    if working_dir.exists():
        for item in working_dir.iterdir():
            if item.is_file():
                bytes_freed += safe_remove_file(item)
    autopsy_dir = job_dir / "autopsy"
    if autopsy_dir.exists():
        bytes_freed += safe_remove_tree(autopsy_dir)
    
    if bytes_freed > 0:
        log_action(job_dir, f"[STORAGE OPTIMIZATION] Working bitstream replica purged. Reclaimed {format_bytes(bytes_freed)}.")
    return bytes_freed

def purge_original_image(job_dir: Path) -> int:
    """
    Purge raw uploaded evidence image from original/ folder.
    Leaves a placeholder marker so examiners know it was pruned by retention policy.
    """
    original_dir = job_dir / "original"
    bytes_freed = 0
    if original_dir.exists():
        for item in original_dir.iterdir():
            if item.is_file() and not item.name.startswith("."):
                bytes_freed += safe_remove_file(item)
        if bytes_freed > 0:
            marker = original_dir / ".pruned.txt"
            marker.write_text(
                f"Raw disk image pruned by storage retention policy.\n"
                f"Reports, audit logs, and case deliverables remain preserved.\n",
                encoding="utf-8"
            )
            log_action(job_dir, f"[STORAGE RETENTION] Raw disk image pruned. Reclaimed {format_bytes(bytes_freed)}.")
    return bytes_freed

def emergency_purge_oldest_images() -> int:
    """
    Mechanism 3: High-watermark emergency purge.
    Iterates over completed jobs oldest first to free space when disk is low.
    Stage 1: Purges working replicas and raw uploaded images.
    Stage 2: If disk remains critically low, purges heavy recovered directories
             and large case ZIP packages from oldest completed jobs.
    """
    total_freed = 0
    if not config.JOBS_DIR.exists():
        return 0
    
    try:
        job_dirs = sorted(
            [d for d in config.JOBS_DIR.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime
        )
        # Stage 1: Purge working copy and raw evidence images
        for jdir in job_dirs:
            total_freed += purge_working_copy(jdir)
            total_freed += purge_original_image(jdir)
            
            free_bytes = shutil.disk_usage(config.JOBS_DIR).free
            if free_bytes >= config.MIN_FREE_DISK_GB * (1024 ** 3):
                return total_freed

        # Stage 2: If still under threshold, prune heavy recovered files and ZIP packages
        for jdir in job_dirs:
            if (jdir / "reports" / "report.html").exists():
                rec_dir = jdir / "recovered"
                if rec_dir.exists():
                    total_freed += safe_remove_tree(rec_dir)
                pkg_zip = jdir / "reports" / "case_package.zip"
                if pkg_zip.exists():
                    total_freed += safe_remove_file(pkg_zip)

                free_bytes = shutil.disk_usage(config.JOBS_DIR).free
                if free_bytes >= config.MIN_FREE_DISK_GB * (1024 ** 3):
                    break
    except Exception as e:
        print(f"Error during emergency storage purge: {e}")
        
    return total_freed

def purge_expired_jobs() -> dict:
    """
    Mechanism 2: TTL Background cleaner.
    - Jobs older than RAW_IMAGE_RETENTION_HOURS: purges original raw images.
    - Jobs older than JOB_RETENTION_HOURS: purges heavy recovered files and ZIP, keeping reports and logs.
    """
    now = time.time()
    raw_cutoff = now - (config.RAW_IMAGE_RETENTION_HOURS * 3600)
    job_cutoff = now - (config.JOB_RETENTION_HOURS * 3600)
    
    stats = {"raw_images_pruned": 0, "jobs_archived": 0, "bytes_freed": 0}
    if not config.JOBS_DIR.exists():
        return stats
        
    for jdir in config.JOBS_DIR.iterdir():
        if not jdir.is_dir():
            continue
        try:
            mtime = jdir.stat().st_mtime
            # Always ensure working copy is pruned if job is complete
            if (jdir / "reports" / "report.html").exists():
                stats["bytes_freed"] += purge_working_copy(jdir)
                
            # Stage 1: Purge raw original image after RAW_IMAGE_RETENTION_HOURS
            if mtime < raw_cutoff:
                freed = purge_original_image(jdir)
                if freed > 0:
                    stats["raw_images_pruned"] += 1
                    stats["bytes_freed"] += freed
                    
            # Stage 2: Prune heavy recovered files and case package after JOB_RETENTION_HOURS
            if mtime < job_cutoff:
                rec_dir = jdir / "recovered"
                if rec_dir.exists():
                    freed = safe_remove_tree(rec_dir)
                    stats["bytes_freed"] += freed
                pkg_zip = jdir / "reports" / "case_package.zip"
                if pkg_zip.exists():
                    freed = safe_remove_file(pkg_zip)
                    stats["bytes_freed"] += freed
                stats["jobs_archived"] += 1
        except Exception as e:
            print(f"Error checking job {jdir.name} for cleanup: {e}")
            
    return stats

_CLEANER_STARTED = False
def init_storage_cleaner():
    global _CLEANER_STARTED
    if not _CLEANER_STARTED:
        _CLEANER_STARTED = True
        def _loop():
            while True:
                try:
                    purge_expired_jobs()
                except Exception as e:
                    print(f"[StorageCleaner Error] {e}")
                time.sleep(config.CLEANUP_INTERVAL_SECONDS)
        t = threading.Thread(target=_loop, daemon=True, name="StorageCleaner")
        t.start()

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

        # Mechanism 1: Immediate Post-Analysis Working Replica Cleanup
        if config.AUTO_CLEAN_WORKING_IMAGE:
            purge_working_copy(job_dir)


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

    # Mechanism 3: High-Watermark Disk Space Safeguard
    try:
        free_bytes = shutil.disk_usage(config.JOBS_DIR).free
        free_gb = free_bytes / (1024 ** 3)
        if free_gb < config.MIN_FREE_DISK_GB:
            emergency_purge_oldest_images()
            free_bytes = shutil.disk_usage(config.JOBS_DIR).free
            free_gb = free_bytes / (1024 ** 3)
            if free_gb < 0.5:
                return (
                    f"Server storage critically low ({free_gb:.2f} GB free). "
                    "Automatic cleanup could not free sufficient space for new uploads. "
                    "Please contact system administrator.",
                    507
                )
    except Exception as e:
        print(f"Warning during disk space check: {e}")

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
        return render_template(
            "package_pruned.html",
            job_id=job_id,
            artifact_name="Case Package Archive (ZIP)"
        ), 200
    return send_file(pkg_file, as_attachment=True, download_name=f"Case_Package_{job_id}.zip")


@app.route("/job/<job_id>/recovered/<path:filename>", methods=["GET"])
def download_recovered_file(job_id: str, filename: str):
    """Download or view an individual recovered evidence file."""
    rec_file = config.JOBS_DIR / job_id / "recovered" / filename
    if not rec_file.exists():
        return render_template(
            "package_pruned.html",
            job_id=job_id,
            artifact_name=f"Recovered Artifact ({filename})"
        ), 200
    return send_file(rec_file, as_attachment=True, download_name=Path(filename).name)


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


@app.route("/api/storage-status", methods=["GET"])
def storage_status():
    """Report server storage metrics and retention configuration."""
    try:
        usage = shutil.disk_usage(config.JOBS_DIR)
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        job_count = len([d for d in config.JOBS_DIR.iterdir() if d.is_dir()]) if config.JOBS_DIR.exists() else 0
        return jsonify({
            "status": "healthy" if free_gb >= config.MIN_FREE_DISK_GB else "low_disk",
            "free_gb": round(free_gb, 2),
            "used_gb": round(used_gb, 2),
            "total_gb": round(total_gb, 2),
            "min_free_threshold_gb": config.MIN_FREE_DISK_GB,
            "jobs_count": job_count,
            "auto_clean_working_copy": config.AUTO_CLEAN_WORKING_IMAGE,
            "raw_image_retention_hours": config.RAW_IMAGE_RETENTION_HOURS,
            "job_retention_hours": config.JOB_RETENTION_HOURS
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/job/<job_id>/purge-raw-image", methods=["POST"])
def manual_purge_raw_image(job_id: str):
    """Allow examiner to manually purge raw evidence images from server storage."""
    job_dir = config.JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Job not found"}), 404
        
    freed_working = purge_working_copy(job_dir)
    freed_original = purge_original_image(job_dir)
    total_freed = freed_working + freed_original

    # If raw evidence was already pruned, also reclaim heavy recovered files and ZIP package
    if total_freed == 0:
        rec_dir = job_dir / "recovered"
        if rec_dir.exists():
            total_freed += safe_remove_tree(rec_dir)
        pkg_zip = job_dir / "reports" / "case_package.zip"
        if pkg_zip.exists():
            total_freed += safe_remove_file(pkg_zip)
    
    return jsonify({
        "success": True,
        "job_id": job_id,
        "bytes_freed": total_freed,
        "freed_str": format_bytes(total_freed),
        "message": "Evidence artifacts successfully purged from server storage. Reports and audit logs preserved."
    })


def get_case_inventory() -> list:
    """Scan jobs directory and compile inventory of cases and storage footprints."""
    cases = []
    if not config.JOBS_DIR.exists():
        return cases
    try:
        jdirs = sorted([d for d in config.JOBS_DIR.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
        for jdir in jdirs:
            try:
                mtime = jdir.stat().st_mtime
                created_str = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(mtime))
                
                tot_size = 0
                for root, _, files in os.walk(jdir):
                    for f in files:
                        try:
                            tot_size += (Path(root) / f).stat().st_size
                        except Exception:
                            pass
                            
                orig_dir = jdir / "original"
                has_orig = False
                orig_size = 0
                if orig_dir.exists():
                    for f in orig_dir.iterdir():
                        if f.is_file() and not f.name.startswith("."):
                            has_orig = True
                            orig_size += f.stat().st_size
                            
                pkg_file = jdir / "reports" / "case_package.zip"
                has_pkg = pkg_file.exists() and pkg_file.stat().st_size > 0
                
                job_data = get_job_data(jdir.name)
                case_num = job_data.get("case_number", config.DEFAULT_CASE_NUMBER)
                examiner = job_data.get("examiner", config.DEFAULT_EXAMINER)
                
                cases.append({
                    "job_id": jdir.name,
                    "case_number": case_num,
                    "examiner": examiner,
                    "created_str": created_str,
                    "size_bytes": tot_size,
                    "size_str": format_bytes(tot_size),
                    "has_original": has_orig,
                    "orig_size_str": format_bytes(orig_size),
                    "has_package": has_pkg
                })
            except Exception as e:
                print(f"Error inspecting case {jdir.name}: {e}")
    except Exception as e:
        print(f"Error compiling case inventory: {e}")
    return cases


@app.route("/admin", methods=["GET"])
def admin_dashboard():
    """Admin Storage & Retention Management Console."""
    if not session.get("is_admin"):
        return render_template("admin_login.html")
    cases = get_case_inventory()
    return render_template("admin.html", cases=cases)


@app.route("/admin/login", methods=["POST"])
def admin_login():
    """Authenticate administrator."""
    pwd = request.form.get("password", "")
    if pwd == config.ADMIN_PASSWORD:
        session["is_admin"] = True
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html", error="Invalid administrator password."), 401


@app.route("/admin/logout", methods=["GET"])
def admin_logout():
    """Log out administrator."""
    session.pop("is_admin", None)
    return redirect(url_for("index"))


@app.route("/api/admin/emergency-purge", methods=["POST"])
def api_admin_emergency_purge():
    """Trigger emergency storage purge across oldest jobs."""
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 401
    freed = emergency_purge_oldest_images()
    return jsonify({
        "success": True,
        "bytes_freed": freed,
        "freed_str": format_bytes(freed),
        "message": f"Emergency purge completed. Reclaimed {format_bytes(freed)}."
    })


# Start the background TTL storage cleaner daemon thread
init_storage_cleaner()


if __name__ == "__main__":
    print(f"================================================================")
    print(f" Digital Forensics Analyzer -- BCSSL Lab 14 (CASE-TEST-014)")
    print(f" Binding to: http://{config.HOST}:{config.PORT}")
    print(f" Evidence Directory: {config.JOBS_DIR}")
    print(f" TSK Binaries:       {config.TSK_BIN_DIR}")
    print(f" Autopsy Bin:        {config.AUTOPSY_BIN}")
    print(f" Storage Policies:   Auto-Clean Working Copy={config.AUTO_CLEAN_WORKING_IMAGE}, Raw TTL={config.RAW_IMAGE_RETENTION_HOURS}h, Min Free={config.MIN_FREE_DISK_GB}GB")
    print(f"================================================================")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)

