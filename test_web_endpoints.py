import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import app as flask_app_module
from app import app, JOBS, JOBS_LOCK

def test_endpoints():
    client = app.test_client()
    
    # 1. Test GET / (Upload Page)
    res_index = client.get("/")
    print(f"GET / -> Status {res_index.status_code}")
    assert res_index.status_code == 200
    assert b"Digital Forensics Analyzer" in res_index.data
    assert b"CASE-TEST-014" in res_index.data

    # 2. Test GET /job/test_run_001
    res_job = client.get("/job/test_run_001")
    print(f"GET /job/test_run_001 -> Status {res_job.status_code}")
    assert res_job.status_code == 200
    assert b"test_run_001" in res_job.data

    # 3. Test GET /api/job/test_run_001/status
    res_api = client.get("/api/job/test_run_001/status")
    print(f"GET /api/job/test_run_001/status -> Status {res_api.status_code}")
    assert res_api.status_code == 200
    api_data = res_api.get_json()
    assert api_data["status"] == "completed"
    assert "actions_log" in api_data or "action_log" in api_data

    # 4. Test GET /job/test_run_001/report
    res_report = client.get("/job/test_run_001/report")
    print(f"GET /job/test_run_001/report -> Status {res_report.status_code}")
    assert res_report.status_code == 200
    assert b"Forensic Examination Executive Summary" in res_report.data
    assert b"INTEGRITY: PASS" in res_report.data
    assert b"_ISGUISE.TXT" in res_report.data

    # 5. Test GET /job/test_run_001/download/pdf
    res_pdf = client.get("/job/test_run_001/download/pdf")
    print(f"GET /job/test_run_001/download/pdf -> Status {res_pdf.status_code}, Length: {len(res_pdf.data)}")
    assert res_pdf.status_code == 200
    assert res_pdf.data.startswith(b"%PDF-")

    # 6. Test GET /job/test_run_001/download/package
    res_zip = client.get("/job/test_run_001/download/package")
    print(f"GET /job/test_run_001/download/package -> Status {res_zip.status_code}, Length: {len(res_zip.data)}")
    assert res_zip.status_code == 200
    assert res_zip.data.startswith(b"PK")

    # 7. Test GET /job/test_run_001/download/timeline
    res_tl = client.get("/job/test_run_001/download/timeline")
    print(f"GET /job/test_run_001/download/timeline -> Status {res_tl.status_code}")
    assert res_tl.status_code == 200
    assert b"Date,Size,Type,Mode" in res_tl.data

    # 8. Test GET /job/test_run_001/download/custody
    res_custody = client.get("/job/test_run_001/download/custody")
    print(f"GET /job/test_run_001/download/custody -> Status {res_custody.status_code}")
    assert res_custody.status_code == 200
    assert b"CHAIN OF CUSTODY" in res_custody.data

    # 9. Test POST /upload
    test_img = BASE_DIR / "test_images" / "practice_evidence.dd"
    with open(test_img, "rb") as f:
        import io
        file_storage = (io.BytesIO(f.read()), "test_evidence_upload.dd")
        res_upload = client.post(
            "/upload",
            data={
                "case_number": "CASE-TEST-014",
                "examiner": "Automated Unit Tester",
                "keywords": "secret, flag",
                "evidence_file": file_storage
            },
            content_type="multipart/form-data"
        )
    print(f"POST /upload -> Status {res_upload.status_code}, Location: {res_upload.headers.get('Location')}")
    assert res_upload.status_code == 302
    assert "/job/" in res_upload.headers.get('Location')

    # 10. Test GET /api/storage-status (Option A)
    res_storage = client.get("/api/storage-status")
    print(f"GET /api/storage-status -> Status {res_storage.status_code}")
    assert res_storage.status_code == 200
    storage_json = res_storage.get_json()
    assert storage_json["auto_clean_working_copy"] is True
    assert storage_json["raw_image_retention_hours"] == 24
    assert storage_json["job_retention_hours"] in (24, 72)
    assert storage_json["min_free_threshold_gb"] == 1.5
    assert "free_gb" in storage_json

    # 11. Test POST /api/job/<id>/purge-raw-image (Option A)
    res_purge = client.post("/api/job/test_run_001/purge-raw-image")
    print(f"POST /api/job/test_run_001/purge-raw-image -> Status {res_purge.status_code}")
    assert res_purge.status_code == 200
    purge_json = res_purge.get_json()
    assert purge_json["success"] is True

    print("\nALL FLASK ENDPOINT TESTS (INCLUDING OPTION A STORAGE APIS) PASSED COMPLETELY!")

if __name__ == "__main__":
    test_endpoints()

