import os
import sys
import tempfile
import pytest
from unittest.mock import patch

# Point to isolated temporary database before importing app
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"

# Ensure backend directory is in sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_backend_path = os.path.join(_repo_root, "user-website", "backend")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from starlette.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.main import (
    app, Base, engine, db, current_user, User, Provider, Wallet, StreamSession,
    validate_destination_target, encrypt_secret, decrypt_secret
)

Base.metadata.create_all(engine)
TestSessionLocal = sessionmaker(bind=engine)

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    s = TestSessionLocal()
    for model in [StreamSession, Provider, Wallet, User]:
        s.query(model).delete()
    s.commit()
    s.close()
    yield

def create_user_with_wallet(session, email="streamer@test.com", tokens=100):
    user = User(email=email, password_hash="dummy")
    session.add(user)
    session.flush()
    wallet = Wallet(id=f"wal_{user.id}", user_id=user.id, token_balance=tokens)
    session.add(wallet)
    session.commit()
    return user

def create_online_provider(session, pid="prov-test", ffmpeg=True, cores=8, ram=16.0):
    p = Provider(
        id=pid,
        name=f"Provider-{pid}",
        cpu_cores=cores,
        ram_gb=ram,
        cost_per_hour=0.25,
        status="ONLINE",
        reliability=100.0,
        system_info={"ffmpeg_available": ffmpeg, "ffmpeg_version": "7.1"}
    )
    session.add(p)
    session.commit()
    return p


# ─── 1. SSRF & Destination Validation Tests ─────────────────────────────────

def test_ssrf_destination_validation():
    # Loopback IP
    with pytest.raises(HTTPException) as exc:
        validate_destination_target("rtmp://127.0.0.1/live", "secret_key")
    assert exc.value.status_code == 422
    assert "local or internal host" in exc.value.detail or "forbidden" in exc.value.detail

    # Localhost string
    with pytest.raises(HTTPException) as exc:
        validate_destination_target("rtmp://localhost/live", "secret_key")
    assert exc.value.status_code == 422

    # HTTP scheme not allowed
    with pytest.raises(HTTPException) as exc:
        validate_destination_target("http://youtube.com/live", "secret_key")
    assert exc.value.status_code == 422
    assert "rtmp://" in exc.value.detail

    # Cloud metadata endpoint
    with pytest.raises(HTTPException) as exc:
        validate_destination_target("rtmp://169.254.169.254/live", "secret_key")
    assert exc.value.status_code == 422

    # Mocked valid external host
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 1935))]):
        url, key, masked = validate_destination_target("rtmp://a.rtmp.youtube.com/live2", "live_secret_key_12345")
        assert url == "rtmp://a.rtmp.youtube.com/live2"
        assert key == "live_secret_key_12345"
        assert masked == "liv****345"


# ─── 2. Secret Encryption / Decryption Tests ────────────────────────────────

def test_encryption_roundtrip():
    secret = "live_stream_key_abc_xyz_987"
    enc = encrypt_secret(secret)
    assert enc != secret
    dec = decrypt_secret(enc)
    assert dec == secret


# ─── 3. Session Creation & Provider Assignment Tests ────────────────────────

def test_create_session_requires_minimum_wallet_balance(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=5)  # Less than 10
    create_online_provider(s)

    app.dependency_overrides[current_user] = lambda: user
    try:
        resp = client.post("/stream/sessions", json={
            "destination_platform": "youtube",
            "destination_url": "rtmp://a.rtmp.youtube.com/live2",
            "destination_key": "my_yt_key_123",
            "profile": "720p60"
        })
        assert resp.status_code == 402
        assert "Insufficient token balance" in resp.json()["detail"]["message"]
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_create_session_requires_online_provider_with_ffmpeg(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    create_online_provider(s, pid="no-ffmpeg-prov", ffmpeg=False)

    app.dependency_overrides[current_user] = lambda: user
    try:
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 1935))]):
            resp = client.post("/stream/sessions", json={
                "destination_platform": "youtube",
                "destination_url": "rtmp://a.rtmp.youtube.com/live2",
                "destination_key": "my_yt_key_123",
                "profile": "720p60"
            })
            assert resp.status_code == 409
            assert "No compatible online provider with FFmpeg" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_successful_session_creation(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    prov = create_online_provider(s, pid="ffmpeg-prov-1", ffmpeg=True)

    app.dependency_overrides[current_user] = lambda: user
    try:
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 1935))]):
            resp = client.post("/stream/sessions", json={
                "destination_platform": "youtube",
                "destination_url": "rtmp://a.rtmp.youtube.com/live2",
                "destination_key": "my_yt_key_123",
                "profile": "720p60"
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"].startswith("stream_")
            assert data["status"] == "ALLOCATED"
            assert data["provider_id"] == prov.id
            assert "stream_key" in data
            assert data["publish_key"].startswith("nxt_live_")
            assert data["destination_key_masked"] == "my_****123"

            # Provider should now be BUSY
            s.refresh(prov)
            assert prov.status == "BUSY"
    finally:
        app.dependency_overrides.pop(current_user, None)


# ─── 4. MediaMTX Webhook Authentication Tests ───────────────────────────────

def test_mediamtx_auth_webhook(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    prov = create_online_provider(s)

    app.dependency_overrides[current_user] = lambda: user
    try:
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 1935))]):
            resp = client.post("/stream/sessions", json={
                "destination_platform": "youtube",
                "destination_url": "rtmp://a.rtmp.youtube.com/live2",
                "destination_key": "my_yt_key_123",
                "profile": "720p60"
            })
            sess_data = resp.json()
            sess_id = sess_data["id"]
            pub_key = sess_data["publish_key"]
    finally:
        app.dependency_overrides.pop(current_user, None)

    # 1. Reject invalid stream key
    auth_resp = client.post("/stream/internal/mediamtx/auth", json={
        "path": f"live/{sess_id}",
        "action": "publish",
        "password": "wrong_key"
    })
    assert auth_resp.status_code == 401

    # 2. Accept valid publish key
    auth_resp = client.post("/stream/internal/mediamtx/auth", json={
        "path": f"live/{sess_id}",
        "action": "publish",
        "password": pub_key
    })
    assert auth_resp.status_code == 200
    assert auth_resp.json()["action"] == "publish"

    # Session status should transition to INGESTING
    db_sess = s.get(StreamSession, sess_id)
    s.refresh(db_sess)
    assert db_sess.status == "INGESTING"

    # 3. Provider read authentication
    auth_read = client.post("/stream/internal/mediamtx/auth", json={
        "path": f"live/{sess_id}",
        "action": "read",
        "password": db_sess.read_key
    })
    assert auth_read.status_code == 200
    assert auth_read.json()["action"] == "read"


# ─── 5. Provider Heartbeat & Metered Billing Tests ──────────────────────────

def test_provider_heartbeat_and_metered_billing(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=10)  # Exactly 10 tokens
    prov = create_online_provider(s)

    app.dependency_overrides[current_user] = lambda: user
    try:
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 1935))]):
            sess_data = client.post("/stream/sessions", json={
                "destination_platform": "youtube",
                "destination_url": "rtmp://a.rtmp.youtube.com/live2",
                "destination_key": "my_yt_key_123",
                "profile": "720p60"
            }).json()
            sess_id = sess_data["id"]
    finally:
        app.dependency_overrides.pop(current_user, None)

    headers = {"X-Provider-Token": "local-demo-token"}

    # First heartbeat: transitions to ENCODING, records start time
    hb1 = client.post(f"/providers/streams/{sess_id}/heartbeat", headers=headers, json={
        "status": "ENCODING",
        "metrics": {"fps": 59.9, "bitrate_kbps": 4500, "speed": "1.00x"}
    })
    assert hb1.status_code == 200
    assert hb1.json()["action"] == "continue"

    # Fast-forward time by 65 seconds
    db_sess = s.get(StreamSession, sess_id)
    from datetime import datetime, timedelta, timezone
    db_sess.last_billed_at = datetime.now(timezone.utc) - timedelta(seconds=65)
    s.commit()

    # Second heartbeat: should bill 1 minute (2 tokens for 720p60)
    hb2 = client.post(f"/providers/streams/{sess_id}/heartbeat", headers=headers, json={
        "status": "ENCODING",
        "metrics": {"fps": 60.0, "bitrate_kbps": 4520, "speed": "1.00x"}
    })
    assert hb2.status_code == 200
    assert hb2.json()["action"] == "continue"
    assert hb2.json()["token_balance"] == 8  # 10 - 2

    # Fast forward by 300 seconds (5 minutes = 10 tokens, balance only has 8!)
    db_sess.last_billed_at = datetime.now(timezone.utc) - timedelta(seconds=305)
    s.commit()

    hb3 = client.post(f"/providers/streams/{sess_id}/heartbeat", headers=headers, json={
        "status": "ENCODING",
        "metrics": {"fps": 60.0}
    })
    assert hb3.status_code == 200
    assert hb3.json()["action"] == "stop"
    assert hb3.json()["reason"] == "insufficient_tokens"


# ─── 6. Stop Stream & Clean Teardown ────────────────────────────────────────

def test_stop_stream_and_release_provider(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=50)
    prov = create_online_provider(s)

    app.dependency_overrides[current_user] = lambda: user
    try:
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 1935))]):
            sess_data = client.post("/stream/sessions", json={
                "destination_platform": "youtube",
                "destination_url": "rtmp://a.rtmp.youtube.com/live2",
                "destination_key": "my_yt_key_123",
                "profile": "720p60"
            }).json()
            sess_id = sess_data["id"]

        # User clicks stop
        stop_resp = client.post(f"/stream/sessions/{sess_id}/stop")
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "STOPPING"
    finally:
        app.dependency_overrides.pop(current_user, None)

    # Provider heartbeat receives stop signal
    headers = {"X-Provider-Token": "local-demo-token"}
    hb = client.post(f"/providers/streams/{sess_id}/heartbeat", headers=headers, json={
        "status": "ENCODING",
        "metrics": {"fps": 60}
    })
    assert hb.json()["action"] == "stop"
    assert hb.json()["reason"] == "user_cancelled"

    # Provider confirms stopped
    stopped_resp = client.post(f"/providers/streams/{sess_id}/stopped", headers=headers, json={
        "status": "COMPLETED",
        "metrics": {"fps": 0}
    })
    assert stopped_resp.status_code == 200

    # Provider is back ONLINE
    s.refresh(prov)
    assert prov.status == "ONLINE"

    # Session is COMPLETED
    db_sess = s.get(StreamSession, sess_id)
    s.refresh(db_sess)
    assert db_sess.status == "COMPLETED"
