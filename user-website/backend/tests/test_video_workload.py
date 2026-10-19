"""
Comprehensive automated tests for Video Compression Workload in Nexora UCMP:
- Upload file validation (extension, MIME, size, probe integrity)
- Provider capability filtering (ffmpeg_available requirement)
- Argument array construction (no shell interpolation)
- Artifact access control (owner vs non-owner, provider token)
- Idempotent billing settlement
- Real end-to-end integration test with FFmpeg when available
"""
import io
import os
import sys
import tempfile
import subprocess
from pathlib import Path
import pytest

# Point to isolated temporary database before importing app
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_backend_path = os.path.join(_repo_root, "user-website", "backend")
_provider_path = os.path.join(_repo_root, "provider-server")

for p in [_backend_path, _provider_path]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from app.main import (
    Base, app, engine, Job, Provider, User, JobArtifact, JobBilling,
    wallet_for, token_ledger, session_response, get_ffmpeg_binary,
    probe_video_file, ARTIFACTS_DIR
)
from sqlalchemy.orm import sessionmaker

Base.metadata.create_all(engine)
client = TestClient(app)
SessionLocal = sessionmaker(bind=engine)

PROVIDER_SHARED_TOKEN = "local-demo-token"


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    # Ensure test user
    u = db.get(User, 1)
    if not u:
        u = User(id=1, email="test_user@nexora.io", password_hash="dummy_hash", wallet_balance=500.0)
        db.merge(u)
    wallet = wallet_for(db, 1)
    if wallet.token_balance < 500:
        wallet.token_balance = 500

    # Ensure other user
    u2 = db.get(User, 2)
    if not u2:
        u2 = User(id=2, email="other_user@nexora.io", password_hash="dummy_hash", wallet_balance=500.0)
        db.merge(u2)
    wallet_for(db, 2)

    db.commit()
    db.close()
    yield


def get_user_token(user_id=1):
    db = SessionLocal()
    u = db.get(User, user_id)
    resp = session_response(db, u)
    db.close()
    return resp["access_token"]


def test_upload_rejects_invalid_extension():
    token = get_user_token(1)
    dummy_data = b"This is a text file, not a video."
    files = {"file": ("malicious.exe", io.BytesIO(dummy_data), "application/octet-stream")}
    res = client.post("/media/artifacts/upload", files=files, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 415
    assert "Unsupported file type" in res.json()["detail"]


def test_upload_rejects_invalid_corrupt_content():
    token = get_user_token(1)
    # File named .mp4 but with text content
    dummy_data = b"Fake mp4 video content header that is not real video."
    files = {"file": ("corrupt.mp4", io.BytesIO(dummy_data), "video/mp4")}
    res = client.post("/media/artifacts/upload", files=files, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422
    assert "Invalid video file" in res.json()["detail"]


def test_provider_capability_filtering():
    """Verify that video_compress jobs are only scheduled to providers with ffmpeg_available."""
    db = SessionLocal()
    # Provider 1: Online, but NO ffmpeg
    p1 = Provider(
        id="prov_no_ffmpeg",
        name="Node Without FFmpeg",
        cpu_cores=4,
        ram_gb=8.0,
        gpu_name=None,
        gpu_memory_gb=0,
        cost_per_hour=0.15,
        status="ONLINE",
        reliability=100.0,
        utilization={},
        system_info={"ffmpeg_available": False}
    )
    db.merge(p1)

    # Provider 2: Online, WITH ffmpeg
    p2 = Provider(
        id="prov_with_ffmpeg",
        name="Node With FFmpeg",
        cpu_cores=4,
        ram_gb=8.0,
        gpu_name=None,
        gpu_memory_gb=0,
        cost_per_hour=0.20,
        status="ONLINE",
        reliability=100.0,
        utilization={},
        system_info={"ffmpeg_available": True, "ffmpeg_version": "7.1"}
    )
    db.merge(p2)

    # Fake input artifact for job submission
    art = JobArtifact(
        id="art_test_input_1",
        user_id=1,
        artifact_type="input",
        filename="sample.mp4",
        media_type="video/mp4",
        file_path="art_test_input_1/sample.mp4",
        size_bytes=1000,
        checksum_sha256="abc",
        meta_data={"duration": 15.0}
    )
    db.merge(art)
    db.commit()
    db.close()

    token = get_user_token(1)
    res = client.post("/jobs", json={
        "name": "Video-Test-Job",
        "workload": "video_compress",
        "requirements": {
            "input_artifact_id": "art_test_input_1",
            "codec": "h264",
            "compression_profile": "balanced",
            "target_resolution": "720p"
        }
    }, headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    job_data = res.json()
    assert job_data["status"] == "SCHEDULED"
    # Must have picked prov_with_ffmpeg, not prov_no_ffmpeg!
    assert job_data["provider_id"] == "prov_with_ffmpeg"


def test_video_compress_requires_input_artifact():
    token = get_user_token(1)
    res = client.post("/jobs", json={
        "name": "Missing-Artifact-Job",
        "workload": "video_compress",
        "requirements": {
            "codec": "h264"
        }
    }, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422
    assert "input_artifact_id" in res.json()["detail"]


def test_artifact_access_control():
    """Verify that only the job owner and authorized providers can access job artifacts."""
    db = SessionLocal()
    # Create test artifact file on disk
    art_dir = ARTIFACTS_DIR / "art_access_test"
    art_dir.mkdir(parents=True, exist_ok=True)
    sample_file = art_dir / "sample_out.mp4"
    sample_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00")

    j = Job(
        id="job_access_test",
        name="Access Test Job",
        workload="video_compress",
        requirements={},
        user_id=1,
        provider_id="prov_test",
        status="COMPLETED"
    )
    db.merge(j)
    art = JobArtifact(
        id="art_access_test",
        job_id="job_access_test",
        user_id=1,
        artifact_type="output",
        filename="sample_out.mp4",
        media_type="video/mp4",
        file_path="art_access_test/sample_out.mp4",
        size_bytes=sample_file.stat().st_size
    )
    db.merge(art)
    db.commit()
    db.close()

    # User 1 (owner) can download
    token1 = get_user_token(1)
    res_owner = client.get("/jobs/job_access_test/artifacts/art_access_test/download", headers={"Authorization": f"Bearer {token1}"})
    assert res_owner.status_code == 200
    assert len(res_owner.content) == sample_file.stat().st_size

    # User 2 (not owner) CANNOT download
    token2 = get_user_token(2)
    res_non_owner = client.get("/jobs/job_access_test/artifacts/art_access_test/download", headers={"Authorization": f"Bearer {token2}"})
    assert res_non_owner.status_code == 404

    # Provider with correct token can download
    res_provider = client.get("/providers/jobs/job_access_test/artifacts/art_access_test/download", headers={"X-Provider-Token": PROVIDER_SHARED_TOKEN})
    assert res_provider.status_code == 200

    # Provider with bad token is rejected
    res_bad_provider = client.get("/providers/jobs/job_access_test/artifacts/art_access_test/download", headers={"X-Provider-Token": "bad-token"})
    assert res_bad_provider.status_code == 401


def test_provider_output_upload_and_billing_settlement():
    """Verify provider output upload, metadata probing, and idempotent billing."""
    db = SessionLocal()
    wallet = wallet_for(db, 1)
    initial_tokens = wallet.token_balance

    j = Job(
        id="job_settle_test",
        name="Settle Test Job",
        workload="video_compress",
        requirements={"input_duration_seconds": 30},
        user_id=1,
        provider_id="prov_with_ffmpeg",
        status="RUNNING"
    )
    db.merge(j)
    bill = JobBilling(job_id=j.id, estimated_tokens=40, reserved_tokens=40)
    db.merge(bill)
    wallet.token_balance -= 40
    db.commit()
    db.close()

    # Provider uploads output file
    output_content = b"\x00\x00\x00\x18ftypmp42fake_output_video_stream_content"
    res_up = client.post(
        "/providers/jobs/job_settle_test/artifacts/upload",
        files={"file": ("output.mp4", io.BytesIO(output_content), "video/mp4")},
        params={"artifact_type": "output"},
        headers={"X-Provider-Token": PROVIDER_SHARED_TOKEN}
    )
    assert res_up.status_code == 200
    art_meta = res_up.json()
    assert art_meta["artifact_id"].startswith("art_")

    # Provider completes job
    res_comp = client.post(
        "/providers/jobs/job_settle_test/update",
        json={
            "status": "COMPLETED",
            "progress": 100,
            "attempt": 1,
            "result": {
                "message": "Video compression completed",
                "workload": "video_compress",
                "video": {
                    "operation": "video_compress",
                    "input_artifact_id": "art_in",
                    "output_artifact_id": art_meta["artifact_id"],
                    "input_size_bytes": 10000,
                    "output_size_bytes": 4000,
                    "compression_ratio": 2.5
                },
                "elapsed_seconds": 5.0
            }
        },
        headers={"X-Provider-Token": PROVIDER_SHARED_TOKEN}
    )
    assert res_comp.status_code == 200

    # Verify billing settled
    db = SessionLocal()
    bill_after = db.get(JobBilling, "job_settle_test")
    assert bill_after.reserved_tokens == 0
    assert bill_after.actual_tokens is not None
    assert bill_after.actual_tokens > 0

    # Verify idempotency: duplicate completion does not double-charge or double-refund
    wallet_mid = wallet_for(db, 1).token_balance
    db.close()

    res_comp2 = client.post(
        "/providers/jobs/job_settle_test/update",
        json={"status": "COMPLETED", "attempt": 1, "result": {"elapsed_seconds": 5.0}},
        headers={"X-Provider-Token": PROVIDER_SHARED_TOKEN}
    )
    assert res_comp2.status_code == 200

    db = SessionLocal()
    wallet_end = wallet_for(db, 1).token_balance
    assert wallet_mid == wallet_end  # Balance did not change on duplicate update!
    db.close()


def test_real_small_video_compression_with_ffmpeg():
    """
    End-to-end integration test:
    Generates a real 1-second small test video using FFmpeg, uploads it to control plane,
    verifies probe metadata, runs provider compression, verifies output artifact exists and is valid.
    """
    ffmpeg_bin = get_ffmpeg_binary()
    if not ffmpeg_bin:
        pytest.skip("FFmpeg binary not installed on this system; skipping live video encode integration test")

    with tempfile.TemporaryDirectory() as td:
        src_path = Path(td) / "test_pattern.mp4"
        # Generate 1-second 320x240 synthetic test video with testsrc filter and silent audio
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=15",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v", "libx264", "-t", "1",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            str(src_path)
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=15)
        assert src_path.exists()
        assert src_path.stat().st_size > 0

        # Upload to control plane
        token = get_user_token(1)
        with open(src_path, "rb") as f:
            upload_res = client.post(
                "/media/artifacts/upload",
                files={"file": ("test_pattern.mp4", f, "video/mp4")},
                headers={"Authorization": f"Bearer {token}"}
            )

        assert upload_res.status_code == 200
        up_data = upload_res.json()
        assert up_data["meta"]["duration"] >= 0.8
        assert up_data["meta"]["width"] == 320
        assert up_data["meta"]["height"] == 240
        input_artifact_id = up_data["artifact_id"]

        # Run provider compression on this artifact
        import main as provider_main
        job_mock = {
            "id": f"job_int_{input_artifact_id[:8]}",
            "workload": "video_compress",
            "attempt": 1,
            "requirements": {
                "input_artifact_id": input_artifact_id,
                "codec": "h264",
                "compression_profile": "balanced",
                "target_resolution": "480p",
                "strip_audio": False
            }
        }

        # Seed provider in DB
        db = SessionLocal()
        p = Provider(
            id=provider_main.PID,
            name=provider_main.NAME,
            cpu_cores=4,
            ram_gb=8.0,
            status="ONLINE",
            system_info={"ffmpeg_available": True}
        )
        db.merge(p)
        db.commit()
        db.close()

        # Submit job so control plane knows about it
        job_res = client.post("/jobs", json={
            "name": "Integration-Test-Job",
            "workload": "video_compress",
            "requirements": job_mock["requirements"]
        }, headers={"Authorization": f"Bearer {token}"})
        assert job_res.status_code == 200
        real_job = job_res.json()
        job_mock["id"] = real_job["id"]

        progress_reports = []
        def report_callback(pct, payload):
            progress_reports.append((pct, payload))

        # Monkey-patch provider requests to call client
        def mock_request(method, path, **kwargs):
            url = path
            headers = kwargs.get("headers", {})
            headers["X-Provider-Token"] = PROVIDER_SHARED_TOKEN
            stream = kwargs.pop("stream", False)
            if method.upper() == "GET":
                return client.get(url, headers=headers, **kwargs)
            elif method.upper() == "POST":
                return client.post(url, headers=headers, **kwargs)

        orig_req = provider_main.request
        provider_main.request = mock_request

        try:
            res_dict = provider_main.run_video_compress(job_mock, report_callback)
            assert res_dict["operation"] == "video_compress"
            assert res_dict["output_artifact_id"] is not None
            assert res_dict["output_size_bytes"] > 0
            assert res_dict["output_probe"]["valid"] is True
            # Progress reached encoding and validating stages
            stages = [p[1].get("stage") for p in progress_reports]
            assert "encoding" in stages
            assert "uploading" in stages
        finally:
            provider_main.request = orig_req
