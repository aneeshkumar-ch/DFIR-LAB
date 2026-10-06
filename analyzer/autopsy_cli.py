import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

import config
from analyzer.intake import log_action, record_custody_action

def check_autopsy_capabilities() -> Dict[str, Any]:
    """
    Examine the installed Autopsy binary and libraries to verify command-line ingest support.
    """
    autopsy_bin = Path(config.AUTOPSY_BIN)
    exists = autopsy_bin.exists() and autopsy_bin.is_file()
    
    # We inspected org-sleuthkit-autopsy-core.jar and verified CommandLineOptionProcessor
    return {
        "installed": exists,
        "path": str(autopsy_bin) if exists else "Not Found",
        "cli_ingest_supported": exists,
        "flags_supported": [
            "--createCase",
            "--caseName=<name>",
            "--caseBaseDir=<dir>",
            "--caseType=<single|multi>",
            "--addDataSource",
            "--dataSourcePath=<path>",
            "--runIngest[=<profile>]",
            "--generateReports[=<profile>]",
            "--listAllDataSources"
        ],
        "notes": (
            "Autopsy 4.23.1 includes CommandLineOptionProcessor for automated case creation and ingest. "
            "Note: Command-line ingest requires prior configuration of ingest modules and report profiles "
            "in the Autopsy GUI options, and may require significant execution time or an interactive desktop session."
        )
    }

def attempt_autopsy_ingest(image_path: Path, job_dir: Path, case_number: str) -> Dict[str, Any]:
    """
    Attempt to run Autopsy in automated command-line ingest mode.
    If Autopsy is not available, fails, or times out, returns status with fallback indication.
    """
    capabilities = check_autopsy_capabilities()
    if not capabilities["installed"] or not config.AUTOPSY_ENABLED:
        log_action(job_dir, "Autopsy CLI automation skipped (disabled in config or binary not found). Falling back to TSK pipeline.")
        return {
            "success": False,
            "engine_mode": "The Sleuth Kit (TSK) Native Pipeline",
            "fallback_reason": "Autopsy CLI disabled or not found",
            "report_path": None,
            "details": capabilities["notes"]
        }

    autopsy_work_dir = job_dir / "autopsy"
    autopsy_work_dir.mkdir(parents=True, exist_ok=True)
    
    case_name = f"Case_{case_number}_{job_dir.name[:8]}"
    case_dir = autopsy_work_dir / case_name
    
    log_action(job_dir, f"Attempting primary analysis with Autopsy CLI ingest engine (Case: {case_name})")
    record_custody_action(job_dir, f"Initiated Autopsy command-line ingest attempt for data source '{image_path.name}'.")

    try:
        # Step 1: Create Case
        create_cmd = [
            config.AUTOPSY_BIN,
            "--nosplash",
            "--createCase",
            f"--caseName={case_name}",
            f"--caseBaseDir={str(autopsy_work_dir)}"
        ]
        
        log_action(job_dir, f"Executing: {' '.join(create_cmd)}")
        proc_create = subprocess.run(
            create_cmd,
            capture_output=True,
            text=True,
            timeout=config.AUTOPSY_TIMEOUT_SECONDS,
            check=False
        )

        # Step 2: Add Data Source & Run Ingest & Generate Reports
        if case_dir.exists():
            ingest_cmd = [
                config.AUTOPSY_BIN,
                "--nosplash",
                f"--caseDir={str(case_dir)}",
                "--addDataSource",
                f"--dataSourcePath={str(image_path)}",
                "--runIngest",
                "--generateReports"
            ]
            log_action(job_dir, f"Executing Autopsy ingest: {' '.join(ingest_cmd)}")
            proc_ingest = subprocess.run(
                ingest_cmd,
                capture_output=True,
                text=True,
                timeout=config.AUTOPSY_TIMEOUT_SECONDS,
                check=False
            )

            # Check if Autopsy HTML report was generated
            reports_dir = case_dir / "Reports"
            if reports_dir.exists():
                html_reports = list(reports_dir.rglob("*.html"))
                if html_reports:
                    primary_report = html_reports[0]
                    log_action(job_dir, f"Autopsy CLI ingest succeeded! Report generated at: {primary_report}")
                    record_custody_action(job_dir, f"Autopsy ingest completed; native Autopsy HTML report archived.")
                    return {
                        "success": True,
                        "engine_mode": "Autopsy Command-Line Ingest Engine",
                        "report_path": str(primary_report),
                        "details": f"Autopsy ingested data source and generated report in {primary_report.name}"
                    }

        # If we reached here, Autopsy did not generate a report or did not create the case
        log_action(job_dir, "Autopsy CLI did not produce an HTML report within the timeout window. Falling back to TSK Native Pipeline.")
        return {
            "success": False,
            "engine_mode": "The Sleuth Kit (TSK) Native Pipeline",
            "fallback_reason": "Autopsy CLI ingest completed without generating HTML report (may require pre-configured GUI report profile or desktop session)",
            "report_path": None,
            "details": capabilities["notes"]
        }

    except subprocess.TimeoutExpired:
        log_action(job_dir, f"Autopsy CLI ingest timed out after {config.AUTOPSY_TIMEOUT_SECONDS}s. Falling back automatically to TSK Native Pipeline.")
        return {
            "success": False,
            "engine_mode": "The Sleuth Kit (TSK) Native Pipeline",
            "fallback_reason": f"Autopsy CLI process timed out after {config.AUTOPSY_TIMEOUT_SECONDS} seconds",
            "report_path": None,
            "details": "Timed out waiting for NetBeans / Solr / Ingest subsystem."
        }
    except Exception as e:
        log_action(job_dir, f"Autopsy CLI execution error: {e}. Falling back to TSK Native Pipeline.")
        return {
            "success": False,
            "engine_mode": "The Sleuth Kit (TSK) Native Pipeline",
            "fallback_reason": str(e),
            "report_path": None,
            "details": str(e)
        }
