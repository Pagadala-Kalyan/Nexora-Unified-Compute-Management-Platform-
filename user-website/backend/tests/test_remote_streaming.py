import os
import secrets
import sys
import tempfile
import urllib.parse
from pathlib import Path
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
import app.main as backend

Base.metadata.create_all(engine)
TestSessionLocal = sessionmaker(bind=engine)

@pytest.fixture
def client():
    backend.MEDIAMTX_INGEST_URL = "rtmp://media.example.test:1935"
    backend.MEDIAMTX_PROVIDER_READ_URL = "rtsp://media.example.test:8554"
    backend.MEDIAMTX_WEBRTC_URL = "http://127.0.0.1:8889"
    backend.MEDIA_SERVER_ALLOW_LOOPBACK = False
    return TestClient(app)


def test_mediamtx_configuration_validation(client, monkeypatch):
    monkeypatch.setattr(backend, "MEDIAMTX_INGEST_URL", "")
    with pytest.raises(HTTPException) as missing:
        backend._validate_media_server_config()
    assert missing.value.status_code == 503
    assert "MEDIAMTX_INGEST_URL" in missing.value.detail

    monkeypatch.setattr(backend, "MEDIAMTX_INGEST_URL", "https://media.example.test")
    with pytest.raises(HTTPException) as wrong_protocol:
        backend._validate_media_server_config()
    assert "RTMP(S)" in wrong_protocol.value.detail

    monkeypatch.setattr(backend, "MEDIAMTX_INGEST_URL", "rtmp://media.example.test:99999")
    with pytest.raises(HTTPException) as bad_port:
        backend._validate_media_server_config()
    assert "valid URL" in bad_port.value.detail or "invalid port" in bad_port.value.detail

    monkeypatch.setattr(backend, "MEDIAMTX_INGEST_URL", "rtmp://127.0.0.1:1935")
    monkeypatch.setattr(backend, "MEDIA_SERVER_ALLOW_LOOPBACK", False)
    with pytest.raises(HTTPException) as loopback:
        backend._validate_media_server_config()
    assert "other devices cannot reach" in loopback.value.detail

    monkeypatch.setattr(backend, "MEDIA_SERVER_ALLOW_LOOPBACK", True)
    monkeypatch.setattr(backend, "MEDIAMTX_INGEST_URL", "rtmp://media.example.test:1935")
    monkeypatch.setattr(backend, "MEDIAMTX_PROVIDER_READ_URL", "rtsp://media.example.test:8554")
    backend._validate_media_server_config()


def test_local_env_file_does_not_override_process_environment(monkeypatch):
    env_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".env", delete=False)
    env_file.write('NEXORA_TEST_OVERRIDE=file-value\nNEXORA_TEST_QUOTED="quoted value"\n')
    env_file.close()
    monkeypatch.setenv("NEXORA_TEST_OVERRIDE", "process-value")
    monkeypatch.delenv("NEXORA_TEST_QUOTED", raising=False)
    try:
        backend._load_local_env_file(Path(env_file.name))
        assert os.environ["NEXORA_TEST_OVERRIDE"] == "process-value"
        assert os.environ["NEXORA_TEST_QUOTED"] == "quoted value"
    finally:
        os.unlink(env_file.name)


def test_local_env_paths_find_and_load_repository_and_backend_files_on_host(monkeypatch):
    # Model the checked-in layout without relying on this test file's own path.
    with tempfile.TemporaryDirectory(dir=_repo_root) as temp_root:
        repo = Path(temp_root)
        backend_app = repo / "user-website" / "backend" / "app"
        backend_app.mkdir(parents=True)
        (repo / ".env.example").write_text("", encoding="utf-8")
        (repo / ".env").write_text("NEXORA_ROOT_ENV=loaded-root\n", encoding="utf-8")
        (repo / "user-website" / "backend" / ".env").write_text(
            "NEXORA_BACKEND_ENV=loaded-backend\n", encoding="utf-8"
        )
        expected = [repo / ".env", repo / "user-website" / "backend" / ".env"]

        paths = backend._local_env_file_paths(backend_app / "main.py")
        assert paths == expected
        monkeypatch.delenv("NEXORA_ROOT_ENV", raising=False)
        monkeypatch.delenv("NEXORA_BACKEND_ENV", raising=False)
        for path in paths:
            backend._load_local_env_file(path)
        assert os.environ["NEXORA_ROOT_ENV"] == "loaded-root"
        assert os.environ["NEXORA_BACKEND_ENV"] == "loaded-backend"


def test_local_env_paths_are_disabled_in_docker(monkeypatch):
    # The container receives configuration from Compose, even if its image
    # happens to contain repository-looking directories or dotenv files.
    monkeypatch.setenv("NEXORA_IN_DOCKER", "1")
    assert backend._is_container_runtime()
    assert backend._local_env_file_paths(Path("/app/app/main.py"), in_container=True) == []


def test_session_start_fails_clearly_before_allocating_when_ingest_is_missing(client, monkeypatch):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    create_online_provider(s)
    monkeypatch.setattr(backend, "MEDIAMTX_INGEST_URL", "")
    try:
        with pytest.raises(HTTPException) as response:
            backend.create_stream_session(backend.StreamSessionCreate(**{
                "destination_platform": "youtube",
                "destination_url": "rtmp://a.rtmp.youtube.com/live2",
                "destination_key": "my_yt_key_123",
                "profile": "720p60",
            }), user, s)
        assert response.value.status_code == 503
        assert "MEDIAMTX_INGEST_URL" in response.value.detail
        assert s.query(StreamSession).count() == 0
        assert s.query(Wallet).filter_by(user_id=user.id).one().token_balance == 100
    finally:
        s.close()


def test_session_generates_obs_ingest_path_and_session_credential(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    create_online_provider(s)
    try:
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 1935))]):
            session = backend.create_stream_session(backend.StreamSessionCreate(**{
                "destination_platform": "youtube",
                "destination_url": "rtmp://a.rtmp.youtube.com/live2",
                "destination_key": "destination-secret",
                "profile": "720p60",
            }), user, s)
        assert session["ingest_server"] == "rtmp://media.example.test:1935/live"
        assert session["ingest_path"] == f"live/{session['id']}"
        stream_key = session["stream_key"]
        assert stream_key.startswith(f"{session['id']}?")
        credentials = urllib.parse.parse_qs(stream_key.split("?", 1)[1])
        assert credentials["user"] == ["nexora"]
        assert credentials["pass"][0].startswith("nxt_live_")
        assert "publish_key" not in session
        assert "destination-secret" not in str(session)
        auth_result = backend.mediamtx_auth(backend.MediaMTXAuthPayload(
            path=session["ingest_path"], action="publish",
            user=credentials["user"][0], password=credentials["pass"][0], protocol="rtmp",
        ), s)
        assert auth_result == {"status": "ok", "action": "publish"}
        with pytest.raises(HTTPException) as wrong_path:
            backend.mediamtx_auth(backend.MediaMTXAuthPayload(
                path=f"wrong/{session['id']}", action="publish",
                user=credentials["user"][0], password=credentials["pass"][0],
            ), s)
        assert wrong_path.value.status_code == 401
    finally:
        s.close()

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
        system_info={"ffmpeg_available": ffmpeg, "ffmpeg_version": "7.1", "stream_encoders": ["libx264"] if ffmpeg else []}
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
            assert "No eligible online provider reports FFmpeg" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_create_session_rejects_invalid_destination_without_echoing_key(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    create_online_provider(s)
    secret = "never-echo-this-stream-key"

    app.dependency_overrides[current_user] = lambda: user
    try:
        resp = client.post("/stream/sessions", json={
            "destination_platform": "youtube",
            "destination_url": "https://example.com/live",
            "destination_key": secret,
            "profile": "720p60"
        })
        assert resp.status_code == 422
        assert "rtmp://" in resp.json()["detail"]
        assert secret not in resp.text
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_create_session_rejects_unknown_platform_and_profile(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    create_online_provider(s)

    app.dependency_overrides[current_user] = lambda: user
    try:
        base = {
            "destination_url": "rtmp://a.rtmp.youtube.com/live2",
            "destination_key": "my_yt_key_123",
            "profile": "720p60"
        }
        resp = client.post("/stream/sessions", json={**base, "destination_platform": "unknown"})
        assert resp.status_code == 422
        assert "supported stream destination" in resp.json()["detail"]

        resp = client.post("/stream/sessions", json={**base, "destination_platform": "youtube", "profile": "ultra-8k"})
        assert resp.status_code == 422
        assert "supported stream encoding profile" in resp.json()["detail"]
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
            credentials = urllib.parse.parse_qs(data["stream_key"].split("?", 1)[1])
            assert credentials["pass"][0].startswith("nxt_live_")
            assert data["ingest_server"] == "rtmp://media.example.test:1935/live"
            assert data["ingest_path"] == f"live/{data['id']}"
            assert data["stream_key"].startswith(f"{data['id']}?user=nexora&pass=")
            assert data["destination_key_masked"] != credentials["pass"][0]
            assert data["destination_key_masked"] == "my_****123"
            assert data["encoding_config"]["video_encoder"] == "libx264"

            # Provider should now be BUSY
            s.refresh(prov)
            assert prov.status == "BUSY"
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_provider_claim_is_single_use_and_credentials_are_scoped(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    provider = create_online_provider(s, pid="claim-provider")
    create_online_provider(s, pid="not-assigned")
    app.dependency_overrides[current_user] = lambda: user
    try:
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 1935))]):
            created = client.post("/stream/sessions", json={
                "destination_platform": "youtube",
                "destination_url": "rtmp://a.rtmp.youtube.com/live2",
                "destination_key": "my_yt_key_123",
                "profile": "720p60",
            }).json()
    finally:
        app.dependency_overrides.pop(current_user, None)

    headers = {"X-Provider-Token": backend.PROVIDER_TOKEN}
    wrong_provider = client.post("/providers/not-assigned/streams/claim", headers=headers)
    assert wrong_provider.json()["command"] == "NONE"
    claimed = client.post(f"/providers/{provider.id}/streams/claim", headers=headers)
    assert claimed.status_code == 200
    assert claimed.json()["command"] == "START_STREAM"
    session = claimed.json()["session"]
    assert session["session_id"] == created["id"]
    read_url = urllib.parse.urlsplit(session["source_url"])
    read_query = urllib.parse.parse_qs(read_url.query)
    assert set(read_query) == {"token"}
    assert read_query["token"][0].startswith("nxt_read_")
    assert session["destination_key"] == "my_yt_key_123"
    legacy = client.get(f"/providers/{provider.id}/streams/pending", headers=headers)
    assert legacy.json() == []
    assert "destination_key" not in legacy.text
    second_claim = client.post(f"/providers/{provider.id}/streams/claim", headers=headers)
    assert second_claim.json() == {"command": "NONE"}


def test_provider_cannot_report_or_stop_another_providers_stream(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    provider = create_online_provider(s, pid="assigned-provider")
    create_online_provider(s, pid="other-provider")
    app.dependency_overrides[current_user] = lambda: user
    try:
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 1935))]):
            sess_data = client.post("/stream/sessions", json={
                "destination_platform": "youtube", "destination_url": "rtmp://a.rtmp.youtube.com/live2",
                "destination_key": "my_yt_key_123", "profile": "720p60",
            }).json()
    finally:
        app.dependency_overrides.pop(current_user, None)
    headers = {"X-Provider-Token": backend.PROVIDER_TOKEN}
    response = client.post(f"/providers/streams/{sess_data['id']}/heartbeat", headers=headers, json={
        "provider_id": "other-provider", "status": "STREAMING", "metrics": {"fps": 60},
    })
    assert response.status_code == 403
    response = client.post(f"/providers/streams/{sess_data['id']}/stopped", headers=headers, json={
        "provider_id": "other-provider", "status": "STOPPED",
    })
    assert response.status_code == 403


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
            pub_key = urllib.parse.parse_qs(sess_data["stream_key"].split("?", 1)[1])["pass"][0]
    finally:
        app.dependency_overrides.pop(current_user, None)

    # 1. Reject invalid stream key
    auth_resp = client.post("/stream/internal/mediamtx/auth", json={
        "path": f"live/{sess_id}",
        "action": "publish",
        "protocol": "rtmp",
        "password": "wrong_key"
    })
    assert auth_resp.status_code == 401

    # 2. Accept valid publish key
    auth_resp = client.post("/stream/internal/mediamtx/auth", json={
        "path": f"live/{sess_id}",
        "action": "publish",
        "protocol": "rtmp",
        "user": "nexora",
        "password": pub_key
    })
    assert auth_resp.status_code == 200
    assert auth_resp.json()["action"] == "publish"

    wrong_path = client.post("/stream/internal/mediamtx/auth", json={
        "path": f"another/{sess_id}", "action": "publish", "protocol": "rtmp", "user": "nexora", "password": pub_key
    })
    assert wrong_path.status_code == 401

    # Session status should transition to RECEIVING when ingest is authenticated.
    db_sess = s.get(StreamSession, sess_id)
    s.refresh(db_sess)
    assert db_sess.status == "RECEIVING"

    # 3. Provider read authentication
    auth_read = client.post("/stream/internal/mediamtx/auth", json={
        "ip": "127.0.0.1",
        "user": "",
        "password": "",
        "token": db_sess.read_key,
        "path": f"live/{sess_id}",
        "protocol": "rtsp",
        "action": "read",
        "query": f"token={urllib.parse.quote(db_sess.read_key)}",
    })
    assert auth_read.status_code == 200
    assert auth_read.json()["action"] == "read"

    invalid_read = client.post("/stream/internal/mediamtx/auth", json={
        "path": f"live/{sess_id}", "protocol": "rtsp", "action": "read", "token": "wrong-token",
    })
    assert invalid_read.status_code == 401

    wrong_path_read = client.post("/stream/internal/mediamtx/auth", json={
        "path": f"other/{sess_id}", "protocol": "rtsp", "action": "read", "token": db_sess.read_key,
    })
    assert wrong_path_read.status_code == 401

    # A valid session path paired with another session's token must be rejected.
    other_read_key = "nxt_read_regression_other_session"
    other_session = StreamSession(
        id=f"stream_other_{secrets.token_hex(4)}", user_id=user.id, provider_id=prov.id,
        status="ALLOCATED", ingest_path="", publish_key="nxt_live_unused", read_key=other_read_key,
        destination_platform="youtube", destination_url="rtmp://a.rtmp.youtube.com/live2",
        destination_key_masked="****", destination_key_encrypted="unused",
        profile_name="720p60", encoding_config={}, latest_metrics={},
        tokens_per_minute=2, total_tokens_billed=0,
    )
    s.add(other_session)
    s.commit()
    mismatch_read = client.post("/stream/internal/mediamtx/auth", json={
        "path": f"live/{other_session.id}", "protocol": "rtsp", "action": "read", "token": db_sess.read_key,
    })
    assert mismatch_read.status_code == 401


def test_browser_capture_uses_webrtc_publish_and_scoped_credentials(client):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    provider = create_online_provider(s, pid="browser-provider")
    app.dependency_overrides[current_user] = lambda: user
    try:
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 1935))]):
            response = client.post("/stream/sessions", json={
                "source_mode": "browser_capture",
                "destination_platform": "youtube",
                "destination_url": "rtmp://a.rtmp.youtube.com/live2",
                "destination_key": "private-youtube-key",
                "profile": "720p60",
            })
        assert response.status_code == 200
        session = response.json()
        assert session["source_mode"] == "browser_capture"
        assert session["webrtc_publish_url"] == f"http://127.0.0.1:8889/live/{session['id']}/whip"
        assert "private-youtube-key" not in str(session)
        key = session["browser_publish_credential"]["password"]
        assert session["browser_publish_credential"]["username"] == "nexora"
        assert "stream_key" not in session

        valid = client.post("/stream/internal/mediamtx/auth", json={
            "path": f"live/{session['id']}", "action": "publish", "protocol": "webrtc",
            "user": "nexora", "password": key, "token": "", "ip": "172.18.0.1",
            "id": "153f0260-0000-0000-0000-000000000000", "query": "",
            "userAgent": "MediaMTX/1.21.2",
        })
        assert valid.status_code == 200
        assert valid.json()["action"] == "publish"
        wrong_protocol = client.post("/stream/internal/mediamtx/auth", json={
            "path": f"live/{session['id']}", "action": "publish", "protocol": "rtmp",
            "user": "nexora", "password": key,
        })
        assert wrong_protocol.status_code == 401
        wrong_key = client.post("/stream/internal/mediamtx/auth", json={
            "path": f"live/{session['id']}", "action": "publish", "protocol": "webrtc",
            "user": "nexora", "password": "invalid-session-key",
        })
        assert wrong_key.status_code == 401

        wrong_path = client.post("/stream/internal/mediamtx/auth", json={
            "path": f"live/other_{session['id']}", "action": "publish", "protocol": "webrtc",
            "user": "nexora", "password": key,
        })
        assert wrong_path.status_code == 401

        other_session = StreamSession(
            id=f"stream_other_{secrets.token_hex(4)}", user_id=user.id, provider_id=provider.id,
            status="ALLOCATED", ingest_path="", publish_key="nxt_live_other_session_key",
            read_key="nxt_read_other_session_key", destination_platform="youtube",
            destination_url="rtmp://a.rtmp.youtube.com/live2", destination_key_masked="****",
            destination_key_encrypted="unused", profile_name="720p60",
            encoding_config={"source_mode": "browser_capture"}, latest_metrics={},
            tokens_per_minute=2, total_tokens_billed=0,
        )
        s.add(other_session)
        s.commit()
        cross_session = client.post("/stream/internal/mediamtx/auth", json={
            "path": f"live/{other_session.id}", "action": "publish", "protocol": "webrtc",
            "user": "nexora", "password": key,
        })
        assert cross_session.status_code == 401

        provider = s.query(Provider).filter_by(id="browser-provider").one()
        claimed = client.post(f"/providers/{provider.id}/streams/claim", headers={
            "X-Provider-Token": backend.PROVIDER_TOKEN,
        })
        command = claimed.json()
        assert command["command"] == "START_STREAM"
        source = urllib.parse.urlsplit(command["session"]["source_url"])
        assert source.path == f"/live/{session['id']}"
        assert urllib.parse.parse_qs(source.query)["token"][0].startswith("nxt_read_")
        assert command["session"]["encoding_config"]["source_mode"] == "browser_capture"
        assert command["session"]["destination_key"] == "private-youtube-key"

        db_session = s.get(StreamSession, session["id"])
        db_session.status = "FAILED"
        s.commit()
        inactive = client.post("/stream/internal/mediamtx/auth", json={
            "path": f"live/{session['id']}", "action": "publish", "protocol": "webrtc",
            "user": "nexora", "password": key,
        })
        assert inactive.status_code == 401
    finally:
        app.dependency_overrides.pop(current_user, None)
        s.close()


def test_browser_capture_rejects_invalid_webrtc_base_url(client, monkeypatch):
    s = TestSessionLocal()
    user = create_user_with_wallet(s, tokens=100)
    create_online_provider(s, pid="invalid-webrtc-provider")
    monkeypatch.setattr(backend, "MEDIAMTX_WEBRTC_URL", "file:///tmp/media")
    try:
        with pytest.raises(HTTPException) as error:
            backend.create_stream_session(backend.StreamSessionCreate(
                source_mode="browser_capture", destination_platform="youtube",
                destination_url="rtmp://a.rtmp.youtube.com/live2", destination_key="valid-key-123",
                profile="720p60",
            ), user, s)
        assert error.value.status_code == 503
        assert "MEDIAMTX_WEBRTC_URL" in error.value.detail
        assert s.query(StreamSession).count() == 0
    finally:
        s.close()


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

    headers = {"X-Provider-Token": backend.PROVIDER_TOKEN}

    # Waiting for OBS is not billable.
    hb1 = client.post(f"/providers/streams/{sess_id}/heartbeat", headers=headers, json={
        "provider_id": prov.id,
        "status": "WAITING_FOR_INPUT",
        "metrics": {}
    })
    assert hb1.status_code == 200
    assert hb1.json()["action"] == "continue"
    db_sess = s.get(StreamSession, sess_id)
    assert db_sess.started_at is None
    assert db_sess.total_tokens_billed == 0

    hb_live = client.post(f"/providers/streams/{sess_id}/heartbeat", headers=headers, json={
        "provider_id": prov.id,
        "status": "STREAMING",
        "metrics": {"fps": 59.9, "bitrate_kbps": 4500, "speed": "1.00x"}
    })
    assert hb_live.status_code == 200

    # Fast-forward time by 65 seconds
    db_sess = s.get(StreamSession, sess_id)
    from datetime import datetime, timedelta, timezone
    db_sess.last_billed_at = datetime.now(timezone.utc) - timedelta(seconds=65)
    s.commit()

    # Second heartbeat: should bill 1 minute (2 tokens for 720p60)
    hb2 = client.post(f"/providers/streams/{sess_id}/heartbeat", headers=headers, json={
        "provider_id": prov.id,
        "status": "STREAMING",
        "metrics": {"fps": 60.0, "bitrate_kbps": 4520, "speed": "1.00x"}
    })
    assert hb2.status_code == 200
    assert hb2.json()["action"] == "continue"
    assert hb2.json()["token_balance"] == 8  # 10 - 2

    # Fast forward by 300 seconds (5 minutes = 10 tokens, balance only has 8!)
    db_sess.last_billed_at = datetime.now(timezone.utc) - timedelta(seconds=305)
    s.commit()

    hb3 = client.post(f"/providers/streams/{sess_id}/heartbeat", headers=headers, json={
        "provider_id": prov.id,
        "status": "STREAMING",
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

        # Exercise the real lifecycle: the provider has claimed the command,
        # so the user's stop request must wait for that process to confirm exit.
        headers = {"X-Provider-Token": backend.PROVIDER_TOKEN}
        claim = client.post(f"/providers/{prov.id}/streams/claim", headers=headers)
        assert claim.status_code == 200
        assert claim.json()["command"] == "START_STREAM"

        # User clicks stop
        stop_resp = client.post(f"/stream/sessions/{sess_id}/stop")
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "STOPPING"
    finally:
        app.dependency_overrides.pop(current_user, None)

    # Provider heartbeat receives stop signal
    hb = client.post(f"/providers/streams/{sess_id}/heartbeat", headers=headers, json={
        "provider_id": prov.id,
        "status": "STARTING",
        "metrics": {"fps": 60}
    })
    assert hb.json()["action"] == "stop"
    assert hb.json()["reason"] == "user_cancelled"

    # Provider confirms stopped
    stopped_resp = client.post(f"/providers/streams/{sess_id}/stopped", headers=headers, json={
        "provider_id": prov.id,
        "status": "STOPPED",
        "metrics": {}
    })
    assert stopped_resp.status_code == 200

    # Provider is back ONLINE
    s.refresh(prov)
    assert prov.status == "ONLINE"

    # Session is COMPLETED
    db_sess = s.get(StreamSession, sess_id)
    s.refresh(db_sess)
    assert db_sess.status == "STOPPED"
