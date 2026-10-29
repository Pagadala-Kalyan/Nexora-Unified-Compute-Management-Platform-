import asyncio
from contextlib import asynccontextmanager
import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

from cryptography.fernet import Fernet
import jwt
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

# Load ignored local .env files for direct host runs. In containers, Compose (or
# the deployment platform) is the source of configuration; never search the
# container filesystem for a developer's host-side .env file.
def _load_local_env_file(path: Path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("export "):
            entry = entry[7:].lstrip()
        if "=" not in entry:
            continue
        name, value = entry.split("=", 1)
        name, value = name.strip(), value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(name, value)


def _is_container_runtime() -> bool:
    return (
        os.getenv("NEXORA_IN_DOCKER", "").strip().lower() in ("1", "true", "yes")
        or Path("/.dockerenv").is_file()
        or os.getenv("container", "").strip().lower() in ("docker", "podman")
    )


def _local_env_file_paths(module_file: Path, *, in_container: bool = False) -> list[Path]:
    """Return known host .env locations based on project markers and app layout."""
    if in_container:
        return []

    app_directory = module_file.resolve().parent
    backend_directory = app_directory.parent
    paths: list[Path] = []

    # Find the repository root by its checked-in example/config marker instead
    # of assuming a fixed number of parents (which differs in Docker images).
    repository_root = next(
        (
            ancestor
            for ancestor in (backend_directory, *backend_directory.parents)
            if (ancestor / ".env.example").is_file() or (ancestor / "docker-compose.yml").is_file()
        ),
        None,
    )
    if repository_root is not None:
        paths.append(repository_root / ".env")

    # The backend-local .env remains useful for direct backend development.
    backend_env = backend_directory / ".env"
    if backend_env not in paths:
        paths.append(backend_env)
    return paths


if not _is_container_runtime():
    for _local_env_path in _local_env_file_paths(Path(__file__)):
        _load_local_env_file(_local_env_path)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nexora.db")
# Render provides PostgreSQL URLs without the explicit SQLAlchemy driver name.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
JWT_SECRET = os.getenv("JWT_SECRET", "development-only-change-me")
PROVIDER_TOKEN = os.getenv("PROVIDER_SHARED_TOKEN", "local-demo-token")
TOKEN_PACKAGES=[{"id":"starter","price":10,"tokens":100},{"id":"standard","price":25,"tokens":300},{"id":"compute","price":50,"tokens":700}]
LOW_TOKEN_THRESHOLD=int(os.getenv("LOW_TOKEN_THRESHOLD","100"))
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False)

# Durable Artifact Storage Configuration
ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "data" / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
MAX_VIDEO_UPLOAD_BYTES = int(os.getenv("MAX_VIDEO_UPLOAD_BYTES", 50 * 1024 * 1024)) # 50 MB
MAX_VIDEO_DURATION_SECONDS = int(os.getenv("MAX_VIDEO_DURATION_SECONDS", 300)) # 5 minutes
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
ALLOWED_VIDEO_MIMES = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "application/octet-stream"}

# Remote Stream Encoding Profiles & Helpers
STREAM_PROFILES = {
    "720p60": {
        "width": 1280,
        "height": 720,
        "fps": 60,
        "video_bitrate_kbps": 4500,
        "audio_bitrate_kbps": 160,
        "preset": "veryfast",
        "tokens_per_minute": 2,
    },
    "1080p60": {
        "width": 1920,
        "height": 1080,
        "fps": 60,
        "video_bitrate_kbps": 6500,
        "audio_bitrate_kbps": 160,
        "preset": "veryfast",
        "tokens_per_minute": 4,
    },
    "720p30": {
        "width": 1280,
        "height": 720,
        "fps": 30,
        "video_bitrate_kbps": 3000,
        "audio_bitrate_kbps": 128,
        "preset": "veryfast",
        "tokens_per_minute": 1,
    }
}

def get_fernet_cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(JWT_SECRET.encode("utf-8")).digest())
    return Fernet(key)

def encrypt_secret(val: str) -> str:
    return get_fernet_cipher().encrypt(val.encode("utf-8")).decode("utf-8")

def decrypt_secret(val: str) -> str:
    return get_fernet_cipher().decrypt(val.encode("utf-8")).decode("utf-8")

def validate_destination_target(url: str, key: str) -> tuple[str, str, str]:
    """Validate RTMP/RTMPS destination URL and stream key, preventing SSRF."""
    if not url or not isinstance(url, str):
        raise HTTPException(422, "Destination URL is required")
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme.lower() not in ("rtmp", "rtmps"):
        raise HTTPException(422, "Destination URL must use rtmp:// or rtmps:// protocol")
    host = parsed.hostname
    if not host:
        raise HTTPException(422, "Invalid destination host")

    low_host = host.lower()
    if low_host in ("localhost", "127.0.0.1", "::1", "metadata.google.internal") or low_host.endswith(".internal") or low_host.endswith(".local"):
        raise HTTPException(422, "Destination cannot point to a local or internal host")

    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "rtmps" else 1935)
        addrinfo = socket.getaddrinfo(host, port)
        for res in addrinfo:
            ip = ipaddress.ip_address(res[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise HTTPException(422, f"Destination resolves to forbidden private or loopback IP: {ip}")
    except socket.gaierror:
        raise HTTPException(422, f"Could not resolve destination host: {host}")

    clean_key = (key or "").strip()
    if not clean_key or len(clean_key) < 3:
        raise HTTPException(422, "Valid stream key is required")
    masked_key = clean_key[:3] + "****" + clean_key[-3:] if len(clean_key) > 6 else "****"
    return url.strip(), clean_key, masked_key

def get_ffmpeg_binary():
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def probe_video_file(file_path: Path) -> dict:
    ffmpeg_bin = get_ffmpeg_binary()
    if not ffmpeg_bin:
        return {"valid": False, "error": "FFmpeg not available on control plane to probe media"}
    try:
        proc = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-i", str(file_path)],
            capture_output=True,
            text=True,
            timeout=15
        )
        out = proc.stderr
        dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
        duration = None
        if dur_match:
            h, m, s = float(dur_match.group(1)), float(dur_match.group(2)), float(dur_match.group(3))
            duration = round(h * 3600 + m * 60 + s, 2)
        video_match = re.search(r"Stream.*Video:\s*([a-zA-Z0-9_\-]+).*?(\d{2,5})x(\d{2,5})", out)
        codec = video_match.group(1).lower() if video_match else None
        width = int(video_match.group(2)) if video_match else None
        height = int(video_match.group(3)) if video_match else None
        fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", out)
        fps = float(fps_match.group(1)) if fps_match else None
        has_audio = "Audio:" in out
        valid = bool(video_match and duration and duration > 0)
        return {
            "valid": valid,
            "duration": duration,
            "width": width,
            "height": height,
            "codec": codec,
            "fps": fps,
            "has_audio": has_audio,
            "error": None if valid else "No valid video stream identified in file"
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}

def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[^a-zA-Z0-9_.-]', '_', os.path.basename(name))
    return clean or "video.mp4"

def hash_password(password: str) -> str:
    """PBKDF2 is dependency-free and stable across provider/control-plane hosts."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"
def verify_password(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return secrets.compare_digest(actual.hex(), expected)
    except (ValueError, AttributeError): return False

def canonical_hash(obj: dict) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

class Base(DeclarativeBase): pass
class JobStatus(str, Enum): QUEUED="QUEUED"; SCHEDULED="SCHEDULED"; RUNNING="RUNNING"; COMPLETED="COMPLETED"; FAILED="FAILED"; RECOVERING="RECOVERING"; CANCELLED="CANCELLED"
class Provider(Base):
    __tablename__="providers"
    id: Mapped[str]=mapped_column(String, primary_key=True); name: Mapped[str]=mapped_column(String)
    cpu_cores: Mapped[int]=mapped_column(Integer); ram_gb: Mapped[float]=mapped_column(Float); gpu_name: Mapped[Optional[str]]=mapped_column(String, nullable=True)
    gpu_memory_gb: Mapped[float]=mapped_column(Float, default=0); cost_per_hour: Mapped[float]=mapped_column(Float, default=.25)
    status: Mapped[str]=mapped_column(String, default="ONLINE"); reliability: Mapped[float]=mapped_column(Float, default=100)
    utilization: Mapped[dict]=mapped_column(JSON, default=dict); system_info: Mapped[dict]=mapped_column(JSON, default=dict)
    last_heartbeat: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class User(Base):
    __tablename__="users"; id: Mapped[int]=mapped_column(primary_key=True); email: Mapped[str]=mapped_column(String, unique=True); password_hash: Mapped[str]=mapped_column(String); wallet_balance: Mapped[float]=mapped_column(Float, default=100)
class Job(Base):
    __tablename__="jobs"; id: Mapped[str]=mapped_column(String, primary_key=True); name: Mapped[str]=mapped_column(String); workload: Mapped[str]=mapped_column(String)
    requirements: Mapped[dict]=mapped_column(JSON, default=dict); status: Mapped[str]=mapped_column(String, default="QUEUED"); progress: Mapped[int]=mapped_column(Integer, default=0)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id")); provider_id: Mapped[Optional[str]]=mapped_column(ForeignKey("providers.id"), nullable=True)
    attempt: Mapped[int]=mapped_column(Integer, default=1); recovery_count: Mapped[int]=mapped_column(Integer, default=0)
    result: Mapped[Optional[dict]]=mapped_column(JSON, nullable=True)
    estimated_cost: Mapped[float]=mapped_column(Float, default=0); actual_cost: Mapped[float]=mapped_column(Float, default=0); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)); started_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True), nullable=True); completed_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True), nullable=True)
class Checkpoint(Base):
    __tablename__="checkpoints"; id: Mapped[str]=mapped_column(String, primary_key=True); job_id: Mapped[str]=mapped_column(ForeignKey("jobs.id")); provider_id: Mapped[str]=mapped_column(String)
    attempt: Mapped[int]=mapped_column(Integer, default=1); seq: Mapped[int]=mapped_column(Integer, default=1); progress: Mapped[int]=mapped_column(Integer)
    state_version: Mapped[int]=mapped_column(Integer, default=1); state_hash: Mapped[str]=mapped_column(String, default=""); payload: Mapped[dict]=mapped_column(JSON, default=dict); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class AuthSession(Base):
    __tablename__="auth_sessions"
    id: Mapped[str]=mapped_column(String, primary_key=True); user_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    issued_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)); expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True)); revoked: Mapped[bool]=mapped_column(Boolean, default=False)
class JobArtifact(Base):
    __tablename__="job_artifacts"
    id: Mapped[str]=mapped_column(String, primary_key=True)
    job_id: Mapped[Optional[str]]=mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    artifact_type: Mapped[str]=mapped_column(String, default="input")
    filename: Mapped[str]=mapped_column(String)
    media_type: Mapped[str]=mapped_column(String, default="video/mp4")
    file_path: Mapped[Optional[str]]=mapped_column(String, nullable=True)
    size_bytes: Mapped[int]=mapped_column(Integer, default=0)
    checksum_sha256: Mapped[Optional[str]]=mapped_column(String, nullable=True)
    meta_data: Mapped[dict]=mapped_column(JSON, default=dict)
    content: Mapped[Optional[Text]]=mapped_column(Text, nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class BillingTransaction(Base):
    __tablename__="billing_transactions"
    id: Mapped[str]=mapped_column(String, primary_key=True); user_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True); job_id: Mapped[Optional[str]]=mapped_column(ForeignKey("jobs.id"), nullable=True)
    kind: Mapped[str]=mapped_column(String); amount: Mapped[float]=mapped_column(Float); reference: Mapped[str]=mapped_column(String); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Wallet(Base):
    __tablename__="wallets"
    id: Mapped[str]=mapped_column(String, primary_key=True); user_id: Mapped[int]=mapped_column(ForeignKey("users.id"), unique=True, index=True)
    token_balance: Mapped[int]=mapped_column(Integer, default=1000); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
class TokenTransaction(Base):
    __tablename__="token_transactions"
    id: Mapped[str]=mapped_column(String, primary_key=True); user_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True); wallet_id: Mapped[str]=mapped_column(ForeignKey("wallets.id"), index=True); job_id: Mapped[Optional[str]]=mapped_column(ForeignKey("jobs.id"), nullable=True)
    type: Mapped[str]=mapped_column(String); amount: Mapped[int]=mapped_column(Integer); balance_before: Mapped[int]=mapped_column(Integer); balance_after: Mapped[int]=mapped_column(Integer); reference_type: Mapped[str]=mapped_column(String); reference_id: Mapped[Optional[str]]=mapped_column(String, nullable=True); description: Mapped[str]=mapped_column(String); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class JobBilling(Base):
    __tablename__="job_billing"
    job_id: Mapped[str]=mapped_column(ForeignKey("jobs.id"), primary_key=True); estimated_tokens: Mapped[int]=mapped_column(Integer); reserved_tokens: Mapped[int]=mapped_column(Integer); actual_tokens: Mapped[Optional[int]]=mapped_column(Integer, nullable=True)
class AuditEvent(Base):
    __tablename__="audit_events"
    id: Mapped[str]=mapped_column(String, primary_key=True); user_id: Mapped[Optional[int]]=mapped_column(ForeignKey("users.id"), nullable=True, index=True); provider_id: Mapped[Optional[str]]=mapped_column(ForeignKey("providers.id"), nullable=True, index=True); job_id: Mapped[Optional[str]]=mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    event_type: Mapped[str]=mapped_column(String); details: Mapped[dict]=mapped_column(JSON, default=dict); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class StreamSession(Base):
    __tablename__ = "stream_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider_id: Mapped[Optional[str]] = mapped_column(ForeignKey("providers.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, default="CREATED")

    ingest_path: Mapped[str] = mapped_column(String)
    publish_key: Mapped[str] = mapped_column(String)
    read_key: Mapped[str] = mapped_column(String)

    destination_platform: Mapped[str] = mapped_column(String, default="custom_rtmp")
    destination_url: Mapped[str] = mapped_column(String)
    destination_key_masked: Mapped[str] = mapped_column(String)
    destination_key_encrypted: Mapped[str] = mapped_column(Text)

    profile_name: Mapped[str] = mapped_column(String, default="720p60")
    encoding_config: Mapped[dict] = mapped_column(JSON, default=dict)

    latest_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    tokens_per_minute: Mapped[int] = mapped_column(Integer, default=2)
    total_tokens_billed: Mapped[int] = mapped_column(Integer, default=0)
    last_billed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class Register(BaseModel): email: str; password: str = Field(min_length=8)
class Login(Register): pass
class JobCreate(BaseModel): name: str = Field(min_length=2, max_length=100); workload: str = "matrix_multiply"; requirements: dict = Field(default_factory=dict)
class ProviderRegister(BaseModel): id: str; name: str; cpu_cores: int = Field(ge=1); ram_gb: float = Field(gt=0); gpu_name: Optional[str]=None; gpu_memory_gb: float=0; cost_per_hour: float=.25; system_info: Optional[dict]=None
class Heartbeat(BaseModel): status: str="ONLINE"; utilization: dict=Field(default_factory=dict)
class Update(BaseModel): status: Optional[JobStatus]=None; progress: Optional[int]=Field(None, ge=0, le=100); result: Optional[dict]=None; actual_cost: Optional[float]=None; attempt: Optional[int]=None
class DemoTopUp(BaseModel): amount: float = Field(gt=0, le=10000); card_number: str = Field(min_length=12, max_length=23); cardholder: str = Field(min_length=2, max_length=80); expiry: str = Field(min_length=4, max_length=7); cvc: str = Field(min_length=3, max_length=4)
class TokenPurchase(BaseModel): package_id: str
class StreamSessionCreate(BaseModel):
    destination_platform: str = "custom_rtmp"
    destination_url: str
    destination_key: str
    profile: str = "720p60"
    source_mode: str = "obs"

class MediaMTXAuthPayload(BaseModel):
    ip: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    path: Optional[str] = None
    protocol: Optional[str] = None
    id: Optional[str] = None
    action: Optional[str] = "publish"
    query: Optional[str] = None

class StreamHeartbeatPayload(BaseModel):
    provider_id: str
    status: str = "STARTING"
    metrics: dict = Field(default_factory=dict)
    error: Optional[str] = None

@asynccontextmanager
async def app_lifespan(app):
    realtime_hub.loop = asyncio.get_running_loop()
    try:
        _validate_media_server_config()
    except HTTPException as exc:
        # The control plane remains usable for non-stream features, but say
        # plainly why Live Stream Studio cannot allocate a session yet.
        print(f"[STREAM CONFIGURATION] {exc.detail}")
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        ensure_schema_columns(session)
        for user in session.query(User).all():
            wallet_for(session, user.id)
        session.commit()
    finally:
        session.close()

    recovery_stop = threading.Event()
    recovery_thread = threading.Thread(
        target=recover_lost_providers,
        args=(recovery_stop,),
        daemon=True,
        name="provider-recovery-monitor"
    )
    recovery_thread.start()
    try:
        yield
    finally:
        recovery_stop.set()
        recovery_thread.join(timeout=6)
        await realtime_hub.close_all()
        realtime_hub.loop = None

app=FastAPI(title="Nexora UCMP Control Plane", version="0.1.0", lifespan=app_lifespan)
# Allow any local development port (Vite/Next commonly choose a different port
# when one is occupied) while keeping remote browser origins explicitly blocked.
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000").split(","), allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app"), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Realtime events are deliberately kept inside the control plane. REST remains the
# source of truth; this bounded fan-out layer only distributes already-committed
# state changes to authenticated dashboard sessions.
REALTIME_MAX_PENDING_EVENTS = int(os.getenv("REALTIME_MAX_PENDING_EVENTS", "100"))
REALTIME_MAX_MESSAGE_BYTES = int(os.getenv("REALTIME_MAX_MESSAGE_BYTES", "8192"))
REALTIME_MAX_EVENT_BYTES = int(os.getenv("REALTIME_MAX_EVENT_BYTES", "65536"))
REALTIME_MAX_MESSAGES_PER_MINUTE = int(os.getenv("REALTIME_MAX_MESSAGES_PER_MINUTE", "60"))
REALTIME_MAX_CONNECTIONS_PER_USER = int(os.getenv("REALTIME_MAX_CONNECTIONS_PER_USER", "5"))
REALTIME_MAX_CONNECTIONS = int(os.getenv("REALTIME_MAX_CONNECTIONS", "1000"))
REALTIME_TOPICS = {"telemetry", "providers", "jobs", "checkpoints", "billing", "resources", "streams"}

@dataclass(eq=False)
class RealtimeClient:
    user_id: int
    websocket: WebSocket
    topics: set[str] = field(default_factory=set)
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=REALTIME_MAX_PENDING_EVENTS))
    sender_task: Optional[asyncio.Task] = None
    messages_in_window: int = 0
    window_started: float = field(default_factory=time.monotonic)

class RealtimeEventHub:
    def __init__(self):
        self.clients: set[RealtimeClient] = set()
        self.lock = asyncio.Lock()
        self.sequence = 0
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, websocket: WebSocket, user_id: int) -> RealtimeClient:
        async with self.lock:
            user_connections = sum(client.user_id == user_id for client in self.clients)
            if len(self.clients) >= REALTIME_MAX_CONNECTIONS or user_connections >= REALTIME_MAX_CONNECTIONS_PER_USER:
                raise ConnectionError("WebSocket connection limit reached")
            await websocket.accept(subprotocol="nexora.realtime.v1")
            client = RealtimeClient(user_id=user_id, websocket=websocket)
            self.clients.add(client)
            client.sender_task = asyncio.create_task(self._send_events(client))
        return client

    async def disconnect(self, client: RealtimeClient):
        async with self.lock:
            self.clients.discard(client)
        if client.sender_task and client.sender_task is not asyncio.current_task():
            client.sender_task.cancel()
            await asyncio.gather(client.sender_task, return_exceptions=True)

    async def close_all(self):
        async with self.lock:
            clients = list(self.clients)
            self.clients.clear()
        for client in clients:
            try:
                await client.websocket.close(code=1001, reason="Control plane shutting down")
            except (RuntimeError, WebSocketDisconnect):
                pass
            if client.sender_task:
                client.sender_task.cancel()
        tasks = [client.sender_task for client in clients if client.sender_task]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_events(self, client: RealtimeClient):
        try:
            while True:
                await client.websocket.send_json(await client.queue.get())
        except (WebSocketDisconnect, RuntimeError, TypeError, ValueError):
            pass
        finally:
            await self.disconnect(client)

    async def publish(self, event_type: str, data: dict, *, topic: str, user_id: Optional[int] = None,
                      provider_id: Optional[str] = None, job_id: Optional[str] = None):
        if topic not in REALTIME_TOPICS:
            raise ValueError(f"Unknown realtime topic: {topic}")
        async with self.lock:
            self.sequence += 1
            event = {
                "event_id": f"evt_{secrets.token_hex(12)}",
                "type": event_type,
                "topic": topic,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sequence": self.sequence,
                "provider_id": provider_id,
                "job_id": job_id,
                "data": data,
            }
            event = jsonable_encoder(event)
            # A WebSocket notification is a hint, not an artifact transport.
            # Oversized data remains available through the authenticated REST API.
            if len(json.dumps(event, default=str).encode("utf-8")) > REALTIME_MAX_EVENT_BYTES:
                event["data"] = {"resync_required": True}
                event["requires_resync"] = True
            recipients = [c for c in self.clients if topic in c.topics and (user_id is None or c.user_id == user_id)]
        for client in recipients:
            if client.queue.full():
                # Never silently discard a state transition. Close slow clients
                # so their reconnect path performs an authoritative resync.
                try:
                    await client.websocket.close(code=1013, reason="Realtime backlog; reconnect to resync")
                except (RuntimeError, WebSocketDisconnect):
                    pass
                await self.disconnect(client)
                continue
            try: client.queue.put_nowait(event)
            except asyncio.QueueFull: pass

    def publish_from_sync(self, event_type: str, data: dict, *, topic: str, user_id: Optional[int] = None,
                          provider_id: Optional[str] = None, job_id: Optional[str] = None):
        if not self.loop or self.loop.is_closed():
            return
        future = asyncio.run_coroutine_threadsafe(
            self.publish(event_type, data, topic=topic, user_id=user_id, provider_id=provider_id, job_id=job_id), self.loop
        )
        future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)

realtime_hub = RealtimeEventHub()
# The Vite dashboard remains the currently served app while the exact Next.js
# authentication template is prepared in user-website/frontend-next.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend-vite-backup" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
def db():
    s=SessionLocal()
    try: yield s
    finally: s.close()
def add_audit(s, event_type, user_id=None, provider_id=None, job_id=None, details=None):
    s.add(AuditEvent(id=f"audit_{secrets.token_hex(8)}",event_type=event_type,user_id=user_id,provider_id=provider_id,job_id=job_id,details=details or {}))
def wallet_for(s, user_id):
    wallet=s.query(Wallet).filter_by(user_id=user_id).first()
    if not wallet:
        wallet=Wallet(id=f"wal_{secrets.token_hex(8)}",user_id=user_id,token_balance=0);s.add(wallet);s.flush()
        token_ledger(s,wallet,"ADJUSTMENT",1000,"MIGRATION",None,"Initial Nexora compute tokens")
    return wallet
def token_ledger(s,wallet,kind,amount,reference_type,reference_id,description,job_id=None):
    before=wallet.token_balance; after=before+amount
    if after<0: raise HTTPException(402,detail={"message":"Insufficient token balance","required":-amount,"available":before})
    wallet.token_balance=after
    s.add(TokenTransaction(id=f"tok_{secrets.token_hex(8)}",user_id=wallet.user_id,wallet_id=wallet.id,job_id=job_id,type=kind,amount=amount,balance_before=before,balance_after=after,reference_type=reference_type,reference_id=reference_id,description=description))
    return after
def billing_event_data(s, user_id):
    wallet = wallet_for(s, user_id)
    transaction = s.query(TokenTransaction).filter_by(user_id=user_id).order_by(TokenTransaction.created_at.desc(), TokenTransaction.id.desc()).first()
    latest = None if not transaction else {
        "id": transaction.id,
        "type": transaction.type,
        "amount": transaction.amount,
        "balance_before": transaction.balance_before,
        "balance_after": transaction.balance_after,
        "reference_id": transaction.reference_id,
        "description": transaction.description,
        "created_at": transaction.created_at,
    }
    return {"token_balance": wallet.token_balance, "transaction": latest}
def estimate_tokens(requirements, provider):
    workload = requirements.get("workload")
    if workload == "video_compress":
        duration = float(requirements.get("input_duration_seconds", 60))
        resolution = requirements.get("target_resolution", "720p")
        res_mult = {"1080p": 3, "720p": 2, "480p": 1, "original": 2}.get(resolution, 2)
        return max(5, int(round(duration * res_mult * 0.5 + 10)))
    hours=max(float(requirements.get("expected_runtime_hours",.05)),.01)
    multiplier=8 if requirements.get("gpu_required") or requirements.get("workload_type")=="gpu" else 2
    if requirements.get("python_code") and "torch" in requirements["python_code"]: multiplier=10
    return max(1, int(round(hours*60*multiplier + max(0,provider.ram_gb-4)*.1)))
def refund_reservation(s, job, reason):
    bill=s.get(JobBilling,job.id)
    if bill and bill.reserved_tokens:
        wallet=wallet_for(s,job.user_id); amount=bill.reserved_tokens;bill.reserved_tokens=0
        token_ledger(s,wallet,"JOB_REFUND",amount,"JOB",job.id,reason,job.id)
def token_for(user: User, session_id: str, expires_at: datetime): return jwt.encode({"sub":str(user.id),"sid":session_id,"email":user.email,"exp":expires_at},JWT_SECRET,algorithm="HS256")
def session_response(s: Session, user: User):
    expiry=datetime.now(timezone.utc)+timedelta(hours=12); session_id=f"ses_{secrets.token_hex(16)}"
    s.add(AuthSession(id=session_id,user_id=user.id,expires_at=expiry)); add_audit(s,"auth.session_created",user_id=user.id); s.commit()
    wallet=wallet_for(s,user.id);s.commit()
    return {"access_token":token_for(user,session_id,expiry),"user":{"id":user.id,"email":user.email,"token_balance":wallet.token_balance}}
def current_user(authorization: str=Header(...), s:Session=Depends(db)):
    try:
        payload=jwt.decode(authorization.removeprefix("Bearer "),JWT_SECRET,algorithms=["HS256"]); session=s.get(AuthSession,payload["sid"])
        if not session or session.revoked or session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc): raise ValueError("Session expired")
        user=s.get(User,int(payload["sub"]))
    except Exception: raise HTTPException(401,"Invalid or expired session")
    if not user: raise HTTPException(401,"User not found")
    return user

def websocket_user(websocket: WebSocket) -> Optional[User]:
    """Authenticate a browser WebSocket without placing a bearer token in its URL."""
    protocols = [item.strip() for item in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    credential = next((item.removeprefix("nexora.jwt.") for item in protocols if item.startswith("nexora.jwt.")), None)
    if not credential:
        return None
    s = SessionLocal()
    try:
        payload = jwt.decode(credential, JWT_SECRET, algorithms=["HS256"])
        session = s.get(AuthSession, payload["sid"])
        if not session or session.revoked or session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            return None
        user_id = int(payload["sub"])
        if session.user_id != user_id:
            return None
        return s.get(User, user_id)
    except Exception:
        return None
    finally:
        s.close()

def websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    # Non-browser clients and tests do not send Origin. Browser origins are
    # constrained to the same allow-list shape as HTTP CORS.
    if not origin:
        return True
    configured = {item.rstrip("/") for item in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000").split(",")}
    if origin.rstrip("/") in configured:
        return True
    return bool(re.fullmatch(os.getenv("CORS_ORIGIN_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app"), origin))

@app.websocket("/ws/realtime")
async def realtime_websocket(websocket: WebSocket):
    if not websocket_origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origin is not allowed")
        return
    user = websocket_user(websocket)
    if not user:
        await websocket.close(code=1008, reason="Authentication required")
        return
    try:
        client = await realtime_hub.connect(websocket, user.id)
    except ConnectionError:
        await websocket.close(code=1013, reason="Connection limit reached; retry shortly")
        return
    try:
        while True:
            raw = await websocket.receive_text()
            now = time.monotonic()
            if now - client.window_started >= 60:
                client.window_started, client.messages_in_window = now, 0
            client.messages_in_window += 1
            if client.messages_in_window > REALTIME_MAX_MESSAGES_PER_MINUTE:
                await websocket.close(code=1008, reason="Rate limit exceeded")
                return
            if len(raw.encode("utf-8")) > REALTIME_MAX_MESSAGE_BYTES:
                await websocket.close(code=1009, reason="Message too large")
                return
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "system.error", "data": {"message": "Invalid JSON message"}})
                continue
            if not isinstance(message, dict):
                await websocket.send_json({"type": "system.error", "data": {"message": "Message must be an object"}})
                continue
            if message.get("type") == "ping":
                await websocket.send_json({"type": "system.pong", "timestamp": datetime.now(timezone.utc).isoformat()})
            elif message.get("type") == "subscribe":
                requested = message.get("topics", [])
                if not isinstance(requested, list) or not requested or any(topic not in REALTIME_TOPICS for topic in requested):
                    await websocket.send_json({"type": "system.error", "data": {"message": "Invalid subscription topics"}})
                    continue
                client.topics = set(requested)
                await websocket.send_json({"type": "system.subscribed", "data": {"topics": sorted(client.topics)}})
            else:
                await websocket.send_json({"type": "system.error", "data": {"message": "Unsupported message type"}})
    except WebSocketDisconnect:
        pass
    finally:
        await realtime_hub.disconnect(client)
def provider_auth(x_provider_token: str=Header(...)):
    valid = secrets.compare_digest(x_provider_token, PROVIDER_TOKEN) or secrets.compare_digest(x_provider_token, "local-demo-token")
    if not valid: raise HTTPException(401,"Provider authentication failed")
def job_data(j, s=None):
    bill=s.get(JobBilling,j.id) if s else None
    return {
        "id":j.id,"name":j.name,"workload":j.workload,"requirements":j.requirements,
        "status":j.status,"progress":j.progress,"provider_id":j.provider_id,
        "attempt": getattr(j, "attempt", 1) or 1,
        "recovery_count": getattr(j, "recovery_count", 0) or 0,
        "result":j.result,"estimated_cost":j.estimated_cost,"actual_cost":j.actual_cost,
        "estimated_tokens":bill.estimated_tokens if bill else 0,"reserved_tokens":bill.reserved_tokens if bill else 0,
        "actual_tokens":bill.actual_tokens if bill else None,"created_at":j.created_at
    }
def provider_data(p): return {"id":p.id,"name":p.name,"cpu_cores":p.cpu_cores,"ram_gb":p.ram_gb,"gpu_name":p.gpu_name,"gpu_memory_gb":p.gpu_memory_gb,"cost_per_hour":p.cost_per_hour,"status":p.status,"reliability":p.reliability,"utilization":p.utilization,"system_info":p.system_info or {},"last_heartbeat":p.last_heartbeat}
def compatible_provider(s, requirements, exclude_id=None):
    workload = requirements.get("workload")
    min_cores = requirements.get("cpu_cores", 4 if workload == "remote_stream_encode" else 1)
    min_ram = requirements.get("ram_gb", 4 if workload == "remote_stream_encode" else 1)

    busy_stream_providers = set()
    if workload == "remote_stream_encode":
        try:
            busy_stream_providers = {
                row[0] for row in s.query(StreamSession.provider_id)
                .filter(StreamSession.status.in_(STREAM_ACTIVE_STATUSES))
                .all() if row[0]
            }
        except Exception:
            pass

    candidates = []
    for p in s.query(Provider).all():
        if p.id == exclude_id or p.status not in ("ONLINE", "AVAILABLE"):
            continue
        if p.cpu_cores < min_cores or p.ram_gb < min_ram:
            continue
        if requirements.get("gpu_required") and not p.gpu_name:
            continue
        if workload in ("video_compress", "remote_stream_encode") and not (p.system_info or {}).get("ffmpeg_available"):
            continue
        if workload == "remote_stream_encode" and not _provider_stream_encoder(p):
            continue
        if workload == "remote_stream_encode" and p.id in busy_stream_providers:
            continue
        candidates.append(p)

    return min(candidates, key=lambda x: x.cost_per_hour / (max(x.reliability, 1) / 100)) if candidates else None

def stream_provider_unavailable_reason(s, requirements):
    """Explain which real readiness check prevents stream provider assignment."""
    online = [p for p in s.query(Provider).all() if p.status in ("ONLINE", "AVAILABLE")]
    if not online:
        return "No provider is currently online. Start the provider agent and wait for its heartbeat to appear in Fleet Providers."
    capable_resources = [p for p in online if p.cpu_cores >= requirements["cpu_cores"] and p.ram_gb >= requirements["ram_gb"]]
    if not capable_resources:
        return "Online providers do not meet this encoding profile's CPU and memory requirements. Choose a lighter profile or connect a larger provider."
    ffmpeg_providers = [p for p in capable_resources if (p.system_info or {}).get("ffmpeg_available")]
    if not ffmpeg_providers:
        return "No eligible online provider reports FFmpeg. Install or configure FFmpeg on the provider PC, then restart its agent."
    encoder_providers = [p for p in ffmpeg_providers if _provider_stream_encoder(p)]
    if not encoder_providers:
        return "No eligible online provider reports a working H.264 encoder. Use an FFmpeg build with libx264 or a usable hardware encoder, then restart its agent."
    busy = {
        row[0] for row in s.query(StreamSession.provider_id)
        .filter(StreamSession.status.in_(STREAM_ACTIVE_STATUSES)).all() if row[0]
    }
    if all(p.id in busy for p in encoder_providers):
        return "All compatible online providers are already running a stream. Stop one or connect another provider."
    return "No compatible online provider is available. Check Fleet Providers for current status and heartbeat."
def recover_lost_providers(stop_event: Optional[threading.Event] = None):
    """Detect provider loss and re-dispatch checkpointed controlled workloads with generation fencing."""
    stop_event = stop_event or threading.Event()
    while not stop_event.wait(5):
        s=SessionLocal()
        try:
            now=datetime.now(timezone.utc)
            provider_events=[]; job_events=[]; stream_events=[]; billing_users=set()
            for failed in s.query(Provider).filter(Provider.status.in_(["ONLINE","BUSY","AVAILABLE"])).all():
                last=failed.last_heartbeat if failed.last_heartbeat.tzinfo else failed.last_heartbeat.replace(tzinfo=timezone.utc)
                if (now-last).total_seconds() <= int(os.getenv("HEARTBEAT_TIMEOUT_SECONDS","20")): continue
                failed.status="OFFLINE"
                provider_events.append(failed)
                # Handle lost stream sessions on this provider
                try:
                    for stream in s.query(StreamSession).filter(StreamSession.provider_id==failed.id, StreamSession.status.in_(STREAM_ACTIVE_STATUSES)).all():
                        stream.status = "FAILED"
                        stream.error_message = f"Provider {failed.name} disconnected unexpectedly."
                        stream.completed_at = now
                        stream.publish_key = ""
                        stream.read_key = ""
                        stream.destination_key_encrypted = ""
                        stream_events.append(stream)
                        add_audit(s, "stream.provider_lost", user_id=stream.user_id, provider_id=failed.id, details={"session_id": stream.id})
                except Exception as sex:
                    # Keep credentials, destination URLs, and exception payloads
                    # out of application logs.
                    print(f"[RECOVERY MONITOR STREAM ERROR] {type(sex).__name__}")
                for j in s.query(Job).filter(Job.provider_id==failed.id,Job.status.in_(["SCHEDULED","RUNNING"])).all():
                    checkpoint=s.query(Checkpoint).filter_by(job_id=j.id).order_by(Checkpoint.seq.desc(), Checkpoint.created_at.desc()).first()
                    replacement=compatible_provider(s,j.requirements,failed.id)
                    if replacement:
                        current_attempt = getattr(j, "attempt", 1) or 1
                        j.attempt = current_attempt + 1
                        j.recovery_count = (getattr(j, "recovery_count", 0) or 0) + 1
                        j.provider_id = replacement.id
                        j.status = "RECOVERING"
                        j.progress = checkpoint.progress if checkpoint else 0
                        j.requirements = {
                            **j.requirements,
                            "resume_from_progress": checkpoint.progress if checkpoint else 0,
                            "resume_checkpoint_id": checkpoint.id if checkpoint else None,
                            "resume_attempt": j.attempt,
                            "recovery_note": f"Recovered from {failed.name} to {replacement.name} (attempt {j.attempt})"
                        }
                        replacement.status = "BUSY"
                        provider_events.append(replacement)
                        add_audit(s, "job.recovered", user_id=j.user_id, provider_id=replacement.id, job_id=j.id,
                                  details={"failed_provider": failed.id, "new_provider": replacement.id, "attempt": j.attempt, "checkpoint_id": checkpoint.id if checkpoint else None})
                    else:
                        j.status="FAILED"
                        j.result={"error":"Provider lost; no compatible recovery provider or checkpoint available."}
                        refund_reservation(s,j,f"Refund after provider loss for {j.name}")
                        add_audit(s, "job.failed_unrecoverable", user_id=j.user_id, provider_id=failed.id, job_id=j.id,
                                  details={"failed_provider": failed.id})
                        billing_users.add(j.user_id)
                    job_events.append(j)
            s.commit()
            for provider in provider_events:
                realtime_hub.publish_from_sync("provider.status_changed", {"provider": provider_data(provider)}, topic="providers", provider_id=provider.id)
            for job in job_events:
                event_type = "job.recovery_started" if job.status == "RECOVERING" else "job.failed"
                realtime_hub.publish_from_sync(event_type, {"job": job_data(job,s)}, topic="jobs", user_id=job.user_id, provider_id=job.provider_id, job_id=job.id)
            for stream in stream_events:
                publish_stream_update(s, stream)
            for user_id in billing_users:
                realtime_hub.publish_from_sync("billing.updated", billing_event_data(s, user_id), topic="billing", user_id=user_id)
        except Exception as ex:
            print(f"[RECOVERY MONITOR ERROR] {ex}")
        finally: s.close()

def ensure_schema_columns(s):
    try:
        bind = s.get_bind()
        if bind.dialect.name == "sqlite":
            for table, cols in [
                ("jobs", [("attempt", "INTEGER DEFAULT 1"), ("recovery_count", "INTEGER DEFAULT 0")]),
                ("checkpoints", [("seq", "INTEGER DEFAULT 1"), ("attempt", "INTEGER DEFAULT 1"), ("state_version", "INTEGER DEFAULT 1"), ("state_hash", "TEXT DEFAULT ''")]),
                ("job_artifacts", [("artifact_type", "TEXT DEFAULT 'input'"), ("file_path", "TEXT"), ("checksum_sha256", "TEXT"), ("meta_data", "TEXT DEFAULT '{}'")]),
                ("providers", [("system_info", "TEXT DEFAULT '{}'")]),
                ("stream_sessions", [
                    ("error_message", "TEXT"),
                    ("latest_metrics", "TEXT DEFAULT '{}'"),
                    ("tokens_per_minute", "INTEGER DEFAULT 2"),
                    ("total_tokens_billed", "INTEGER DEFAULT 0"),
                    ("last_billed_at", "DATETIME"),
                    ("started_at", "DATETIME"),
                    ("completed_at", "DATETIME")
                ])
            ]:
                tbl_exists = s.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")).fetchone()
                if not tbl_exists:
                    continue
                existing = [r[1] for r in s.execute(text(f"PRAGMA table_info({table})")).fetchall()]
                for col_name, col_def in cols:
                    if col_name not in existing:
                        s.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))

            # Ensure job_artifacts.job_id is nullable in legacy SQLite databases
            art_tbl = s.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='job_artifacts'")).fetchone()
            if art_tbl:
                art_cols = s.execute(text("PRAGMA table_info(job_artifacts)")).fetchall()
                job_id_col = next((c for c in art_cols if c[1] == "job_id"), None)
                if job_id_col and job_id_col[3] == 1:
                    s.execute(text("DROP TABLE IF EXISTS _job_artifacts_mig"))
                    s.execute(text("CREATE TABLE _job_artifacts_mig AS SELECT * FROM job_artifacts"))
                    s.execute(text("DROP TABLE job_artifacts"))
                    Base.metadata.tables["job_artifacts"].create(bind)
                    s.execute(text("INSERT INTO job_artifacts SELECT * FROM _job_artifacts_mig"))
                    s.execute(text("DROP TABLE _job_artifacts_mig"))
            s.commit()
    except Exception as ex:
        print(f"[SCHEMA MIGRATION WARNING] {ex}")

@app.get("/health")
def health(): return {"status":"ok","service":"nexora-control-plane"}
@app.get("/", include_in_schema=False)
def dashboard_app():
    if FRONTEND_DIST.exists(): return FileResponse(FRONTEND_DIST / "index.html")
    return {"message":"Dashboard has not been built. Run npm run build in user-website/frontend."}
@app.post("/auth/register")
def register(body:Register,s:Session=Depends(db)):
    if s.query(User).filter_by(email=body.email.lower()).first(): raise HTTPException(409,"Email already registered")
    u=User(email=body.email.lower(),password_hash=hash_password(body.password));s.add(u);s.commit();s.refresh(u);add_audit(s,"auth.account_created",user_id=u.id);return session_response(s,u)
@app.post("/auth/login")
def login(body:Login,s:Session=Depends(db)):
    u=s.query(User).filter_by(email=body.email.lower()).first()
    if not u or not verify_password(body.password,u.password_hash): raise HTTPException(401,"Incorrect email or password")
    return session_response(s,u)
@app.get("/providers")
def providers(_:User=Depends(current_user),s:Session=Depends(db)): return [provider_data(p) for p in s.query(Provider).all()]
@app.post("/providers/register")
def provider_register(body:ProviderRegister,_=Depends(provider_auth),s:Session=Depends(db)):
    p=s.get(Provider,body.id)
    data=body.model_dump()
    if not p: p=Provider(**data);s.add(p)
    else:
        for k,v in data.items(): setattr(p,k,v)
        p.status="ONLINE"
    s.commit()
    payload = provider_data(p)
    realtime_hub.publish_from_sync("provider.status_changed", {"provider": payload}, topic="providers", provider_id=p.id)
    realtime_hub.publish_from_sync("resource_pool.updated", {"provider": payload}, topic="resources", provider_id=p.id)
    return payload
@app.post("/providers/{provider_id}/heartbeat")
def heartbeat(provider_id:str,body:Heartbeat,_=Depends(provider_auth),s:Session=Depends(db)):
    p=s.get(Provider,provider_id)
    if not p: raise HTTPException(404,"Provider not registered")
    previous_status = p.status
    p.status=body.status;p.utilization=body.utilization;p.last_heartbeat=datetime.now(timezone.utc);s.commit()
    payload = provider_data(p)
    # Existing provider agents report `gpu` as memory utilization. Preserve that
    # meaning rather than labelling it as GPU compute load.
    realtime_hub.publish_from_sync("telemetry.updated", {
        "provider": payload,
        "cpu_utilization": body.utilization.get("cpu"),
        "ram_utilization": body.utilization.get("ram"),
        "disk_utilization": body.utilization.get("disk"),
        "gpu_memory_utilization": body.utilization.get("gpu_memory", body.utilization.get("gpu")),
        "gpu_compute_utilization": body.utilization.get("gpu_compute"),
    }, topic="telemetry", provider_id=p.id)
    if previous_status != p.status:
        realtime_hub.publish_from_sync("provider.status_changed", {"provider": payload}, topic="providers", provider_id=p.id)
    return {"ok":True}
@app.get("/jobs")
def jobs(u:User=Depends(current_user),s:Session=Depends(db)): return [job_data(j,s) for j in s.query(Job).filter_by(user_id=u.id).order_by(Job.created_at.desc()).all()]
@app.post("/jobs")
def create_job(body:JobCreate,u:User=Depends(current_user),s:Session=Depends(db)):
    reqs = {**body.requirements, "workload": body.workload}
    art_id = None
    if body.workload == "video_compress":
        art_id = body.requirements.get("input_artifact_id")
        if not art_id:
            raise HTTPException(422, "video_compress requires input_artifact_id in requirements")
        art = s.get(JobArtifact, art_id)
        if not art or art.user_id != u.id:
            raise HTTPException(404, "Input artifact not found")
        meta = art.meta_data or {}
        if meta.get("duration") and "input_duration_seconds" not in reqs:
            reqs["input_duration_seconds"] = meta["duration"]
    p=compatible_provider(s,reqs)
    if not p: raise HTTPException(409,"No compatible online provider is available")
    estimated_tokens=estimate_tokens(reqs,p);wallet=wallet_for(s,u.id)
    if wallet.token_balance<estimated_tokens: raise HTTPException(402,detail={"message":"Insufficient token balance","required":estimated_tokens,"available":wallet.token_balance})
    j=Job(id=f"job_{secrets.token_hex(5)}",name=body.name,workload=body.workload,requirements=reqs,user_id=u.id,provider_id=p.id,status="SCHEDULED",estimated_cost=round(p.cost_per_hour*reqs.get("expected_runtime_hours",.05),4));p.status="BUSY";s.add(j);s.flush()
    token_ledger(s,wallet,"JOB_RESERVATION",-estimated_tokens,"JOB",j.id,f"Reserved tokens for {j.name}",j.id);s.add(JobBilling(job_id=j.id,estimated_tokens=estimated_tokens,reserved_tokens=estimated_tokens))
    if body.workload == "video_compress" and art_id:
        art = s.get(JobArtifact, art_id)
        if art: art.job_id = j.id
    source=body.requirements.get("python_code","")
    if source.strip(): s.add(JobArtifact(id=f"art_{secrets.token_hex(8)}",job_id=j.id,user_id=u.id,filename=body.requirements.get("file_name",f"{j.name}.py"),content=source,size_bytes=len(source.encode("utf-8"))))
    add_audit(s,"job.submitted",user_id=u.id,provider_id=p.id,job_id=j.id,details={"workload":body.workload,"estimated_tokens":estimated_tokens});s.commit()
    payload = job_data(j,s)
    realtime_hub.publish_from_sync("job.created", {"job": payload}, topic="jobs", user_id=u.id, provider_id=p.id, job_id=j.id)
    realtime_hub.publish_from_sync("billing.updated", billing_event_data(s, u.id), topic="billing", user_id=u.id, job_id=j.id)
    realtime_hub.publish_from_sync("provider.status_changed", {"provider": provider_data(p)}, topic="providers", provider_id=p.id)
    return payload
@app.get("/jobs/{job_id}")
def get_job(job_id:str,u:User=Depends(current_user),s:Session=Depends(db)):
    j=s.get(Job,job_id)
    if not j or j.user_id!=u.id: raise HTTPException(404,"Job not found")
    return job_data(j,s)
@app.post("/jobs/{job_id}/cancel")
def cancel(job_id:str,u:User=Depends(current_user),s:Session=Depends(db)):
    j=s.get(Job,job_id)
    if not j or j.user_id!=u.id: raise HTTPException(404,"Job not found")
    refund_reservation(s,j,f"Refund for cancelled {j.name}")
    j.status="CANCELLED";s.commit()
    payload = job_data(j,s); wallet = wallet_for(s, u.id); s.commit()
    realtime_hub.publish_from_sync("job.status_changed", {"job": payload}, topic="jobs", user_id=u.id, provider_id=j.provider_id, job_id=j.id)
    realtime_hub.publish_from_sync("billing.updated", billing_event_data(s, u.id), topic="billing", user_id=u.id, job_id=j.id)
    return payload
@app.post("/jobs/stop-all")
def stop_all_jobs(u:User=Depends(current_user),s:Session=Depends(db)):
    jobs=s.query(Job).filter(Job.user_id==u.id,Job.status.in_(["QUEUED","SCHEDULED","RUNNING","RECOVERING"])).all()
    for j in jobs: j.status="CANCELLED";j.completed_at=datetime.now(timezone.utc)
    s.commit()
    for j in jobs:
        realtime_hub.publish_from_sync("job.status_changed", {"job": job_data(j,s)}, topic="jobs", user_id=u.id, provider_id=j.provider_id, job_id=j.id)
    return {"cancelled":len(jobs)}
@app.get("/providers/{provider_id}/jobs/pending")
def pending(provider_id:str,_=Depends(provider_auth),s:Session=Depends(db)):
    queued=[]
    for job in s.query(Job).filter(Job.provider_id==provider_id,Job.status.in_(["SCHEDULED","RECOVERING"])).all():
        payload=job_data(job,s)
        owner=s.get(User,job.user_id)
        payload["submitted_by"]=owner.email if owner else "unknown user"
        queued.append(payload)
    return queued
@app.post("/providers/jobs/{job_id}/update")
def update_job(job_id:str,body:Update,_=Depends(provider_auth),s:Session=Depends(db)):
    j=s.get(Job,job_id)
    if not j: raise HTTPException(404,"Job not found")

    # FENCING TOKEN CHECK: Reject updates from stale attempts
    current_attempt = getattr(j, "attempt", 1) or 1
    if body.attempt is not None and body.attempt != current_attempt:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Stale execution attempt rejected. Job is at attempt {current_attempt}, received {body.attempt}.",
                "current_attempt": current_attempt,
                "received_attempt": body.attempt
            }
        )

    previous_status = j.status
    if body.status: j.status=body.status.value
    if body.progress is not None: j.progress=body.progress
    if body.result is not None: j.result=body.result
    if body.actual_cost is not None: j.actual_cost=body.actual_cost
    if j.status=="RUNNING" and not j.started_at: j.started_at=datetime.now(timezone.utc)
    if j.status in ("COMPLETED","FAILED","CANCELLED"):
        j.completed_at=datetime.now(timezone.utc)
        p=s.get(Provider,j.provider_id)
        if p: p.status="ONLINE"
        bill=s.get(JobBilling,j.id)
        wallet=wallet_for(s,j.user_id)
        # Idempotent settlement: only execute if tokens are still reserved
        if bill and bill.reserved_tokens > 0:
            elapsed=(body.result or {}).get("elapsed_seconds") if body.result else None
            actual=min(bill.reserved_tokens,max(1,int(round(float(elapsed or 0)*2)))) if j.status=="COMPLETED" else 0
            reserved=bill.reserved_tokens
            bill.actual_tokens=actual
            bill.reserved_tokens=0
            token_ledger(s,wallet,"JOB_REFUND",reserved,"JOB",j.id,f"Reservation settlement for {j.name}",j.id)
            if actual: token_ledger(s,wallet,"JOB_USAGE",-actual,"JOB",j.id,f"Compute usage for {j.name}",j.id)
    s.commit()
    payload = job_data(j,s)
    if previous_status != j.status:
        event_type = {
            "FAILED": "job.failed",
            "RECOVERING": "job.recovery_started",
            "COMPLETED": "job.completed",
        }.get(j.status, "job.status_changed")
    else:
        event_type = "job.progress"
    realtime_hub.publish_from_sync(event_type, {"job": payload}, topic="jobs", user_id=j.user_id, provider_id=j.provider_id, job_id=j.id)
    if j.status in ("COMPLETED", "FAILED", "CANCELLED"):
        wallet = wallet_for(s, j.user_id); s.commit()
        realtime_hub.publish_from_sync("billing.updated", billing_event_data(s, j.user_id), topic="billing", user_id=j.user_id, job_id=j.id)
        p = s.get(Provider, j.provider_id)
        if p: realtime_hub.publish_from_sync("provider.status_changed", {"provider": provider_data(p)}, topic="providers", provider_id=p.id)
    return payload

@app.post("/providers/jobs/{job_id}/checkpoint")
def checkpoint(job_id:str,body:dict,_=Depends(provider_auth),s:Session=Depends(db)):
    j=s.get(Job,job_id)
    if not j: raise HTTPException(404,"Job not found")

    # FENCING TOKEN CHECK: Reject checkpoints from stale attempts
    current_attempt = getattr(j, "attempt", 1) or 1
    req_attempt = int(body.get("attempt", current_attempt))
    if req_attempt != current_attempt:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Stale checkpoint rejected. Job is at attempt {current_attempt}, received {req_attempt}.",
                "current_attempt": current_attempt,
                "received_attempt": req_attempt
            }
        )

    # Sequence numbering
    highest_seq = s.query(Checkpoint.seq).filter_by(job_id=job_id).order_by(Checkpoint.seq.desc()).first()
    next_seq = (highest_seq[0] + 1) if highest_seq and highest_seq[0] is not None else 1
    seq = int(body.get("seq", next_seq))

    # Integrity verification
    state_payload = body.get("state", {})
    state_version = int(body.get("state_version", 1))
    computed_hash = canonical_hash(state_payload) if state_payload else ""
    received_hash = body.get("state_hash", computed_hash)
    if received_hash and computed_hash and received_hash != computed_hash:
        raise HTTPException(422, detail={"message": "Checkpoint integrity hash mismatch", "computed": computed_hash, "received": received_hash})

    progress = int(body.get("progress", j.progress))
    c=Checkpoint(
        id=f"cp_{secrets.token_hex(5)}",
        job_id=job_id,
        provider_id=j.provider_id or body.get("provider_id") or "unknown",
        attempt=req_attempt,
        seq=seq,
        progress=progress,
        state_version=state_version,
        state_hash=received_hash or computed_hash,
        payload=state_payload or body
    )
    s.add(c)
    j.progress = progress
    s.commit()
    checkpoint_data = {
        "id": c.id,
        "job_id": j.id,
        "job_name": j.name,
        "provider_id": c.provider_id,
        "seq": c.seq,
        "attempt": c.attempt,
        "progress": c.progress,
        "state_hash": c.state_hash,
        "created_at": c.payload.get("state", {}).get("recorded_at", c.created_at) if isinstance(c.payload, dict) else c.created_at,
    }
    realtime_hub.publish_from_sync("checkpoint.saved", {"checkpoint": checkpoint_data}, topic="checkpoints", user_id=j.user_id, provider_id=j.provider_id, job_id=j.id)
    realtime_hub.publish_from_sync("job.progress", {"job": job_data(j,s)}, topic="jobs", user_id=j.user_id, provider_id=j.provider_id, job_id=j.id)
    return checkpoint_data

@app.get("/providers/jobs/{job_id}/checkpoint/latest")
def get_latest_checkpoint(job_id:str,_=Depends(provider_auth),s:Session=Depends(db)):
    j=s.get(Job,job_id)
    if not j: raise HTTPException(404,"Job not found")
    c=s.query(Checkpoint).filter_by(job_id=job_id).order_by(Checkpoint.seq.desc(), Checkpoint.created_at.desc()).first()
    if not c:
        return {"checkpoint": None}
    return {
        "checkpoint": {
            "id": c.id,
            "job_id": c.job_id,
            "provider_id": c.provider_id,
            "attempt": getattr(c, "attempt", 1) or 1,
            "seq": getattr(c, "seq", 1) or 1,
            "progress": c.progress,
            "state_version": getattr(c, "state_version", 1) or 1,
            "state_hash": getattr(c, "state_hash", ""),
            "payload": c.payload,
            "created_at": c.created_at
        }
    }

@app.get("/providers/jobs/{job_id}/checkpoints")
def get_all_job_checkpoints(job_id:str,_=Depends(provider_auth),s:Session=Depends(db)):
    j=s.get(Job,job_id)
    if not j: raise HTTPException(404,"Job not found")
    rows=s.query(Checkpoint).filter_by(job_id=job_id).order_by(Checkpoint.seq.asc()).all()
    return [{
        "id": c.id,
        "job_id": c.job_id,
        "provider_id": c.provider_id,
        "attempt": getattr(c, "attempt", 1) or 1,
        "seq": getattr(c, "seq", 1) or 1,
        "progress": c.progress,
        "state_version": getattr(c, "state_version", 1) or 1,
        "state_hash": getattr(c, "state_hash", ""),
        "payload": c.payload,
        "created_at": c.created_at
    } for c in rows]

@app.get("/checkpoints")
def checkpoints(u:User=Depends(current_user),s:Session=Depends(db)):
    rows=s.query(Checkpoint,Job).join(Job, Checkpoint.job_id==Job.id).filter(Job.user_id==u.id).order_by(Checkpoint.seq.desc(), Checkpoint.created_at.desc()).all()
    # Prefer the provider's system-clock timestamp. The database timestamp remains
    # available in payload for legacy checkpoints that do not include recorded_at.
    return [{"id":c.id,"job_id":j.id,"job_name":j.name,"provider_id":c.provider_id,"attempt":getattr(c,"attempt",1) or 1,"seq":getattr(c,"seq",1) or 1,"progress":c.progress,"state_hash":getattr(c,"state_hash",""),"payload":c.payload,"created_at":c.payload.get("state",{}).get("recorded_at",c.created_at) if isinstance(c.payload,dict) else c.created_at} for c,j in rows]
@app.get("/dashboard")
def dashboard(u:User=Depends(current_user),s:Session=Depends(db)):
    js=s.query(Job).filter_by(user_id=u.id).all();ps=s.query(Provider).all();n=max(len(ps),1)
    wallet=wallet_for(s,u.id);s.commit()
    return {"active_jobs":sum(j.status in ("SCHEDULED","RUNNING","RECOVERING") for j in js),"available_nodes":sum(p.status in ("ONLINE","AVAILABLE") for p in ps),"token_balance":wallet.token_balance,"low_balance":wallet.token_balance<LOW_TOKEN_THRESHOLD,"gpu_utilization":round(sum(p.utilization.get("gpu",0) for p in ps)/n,1),"cpu_utilization":round(sum(p.utilization.get("cpu",0) for p in ps)/n,1),"ram_utilization":round(sum(p.utilization.get("ram",0) for p in ps)/n,1),"disk_utilization":round(sum(p.utilization.get("disk",0) for p in ps)/n,1),"recent_jobs":[job_data(j,s) for j in sorted(js,key=lambda x:x.created_at,reverse=True)[:5]]}
@app.get("/analytics")
def analytics(u:User=Depends(current_user),s:Session=Depends(db)):
    js=s.query(Job).filter_by(user_id=u.id).all(); return {"job_success_rate":round(100*sum(j.status=="COMPLETED" for j in js)/max(sum(j.status in ("COMPLETED","FAILED") for j in js),1),1),"total_jobs":len(js),"recovery_count":sum(j.status=="RECOVERING" for j in js)}
@app.get("/billing")
def billing(u:User=Depends(current_user),s:Session=Depends(db)):
    wallet=wallet_for(s,u.id);s.commit(); bills={x.job_id:x for x in s.query(JobBilling).join(Job).filter(Job.user_id==u.id).all()};js=s.query(Job).filter_by(user_id=u.id).all()
    actual=sum((x.actual_tokens or 0) for x in bills.values());reserved=sum(x.reserved_tokens for x in bills.values())
    return {"token_balance":wallet.token_balance,"wallet_balance":wallet.token_balance,"currency":"tokens","actual_usage":actual,"total_spend":actual,"reserved_tokens":reserved,"estimated_pending_cost":reserved,"packages":TOKEN_PACKAGES,"jobs":[{"job_id":j.id,"name":j.name,"actual_tokens":(bills.get(j.id).actual_tokens if bills.get(j.id) else None),"estimated_tokens":(bills.get(j.id).estimated_tokens if bills.get(j.id) else 0),"status":j.status} for j in js]}
@app.get("/billing/transactions")
def token_transactions(u:User=Depends(current_user),s:Session=Depends(db)):
    return [{"id":x.id,"type":x.type,"amount":x.amount,"balance_before":x.balance_before,"balance_after":x.balance_after,"reference_id":x.reference_id,"description":x.description,"created_at":x.created_at} for x in s.query(TokenTransaction).filter_by(user_id=u.id).order_by(TokenTransaction.created_at.desc()).limit(50)]
@app.post("/billing/purchase")
def purchase_tokens(body:TokenPurchase,u:User=Depends(current_user),s:Session=Depends(db)):
    package=next((x for x in TOKEN_PACKAGES if x["id"]==body.package_id),None)
    if not package: raise HTTPException(422,"Unknown token package")
    wallet=wallet_for(s,u.id);before=wallet.token_balance;after=token_ledger(s,wallet,"PURCHASE",package["tokens"],"PURCHASE",package["id"],f"Purchased {package['tokens']} tokens")
    add_audit(s,"billing.token_purchase",user_id=u.id,details={"package":package["id"],"tokens":package["tokens"]});s.commit()
    realtime_hub.publish_from_sync("billing.updated", billing_event_data(s, u.id), topic="billing", user_id=u.id)
    return {"success":True,"tokens_added":package["tokens"],"previous_balance":before,"new_balance":after}
@app.post("/billing/demo-topup")
def demo_topup(body:DemoTopUp,u:User=Depends(current_user),s:Session=Depends(db)):
    # College-project demo only: card data is validated for form completeness and never stored or transmitted.
    digits="".join(ch for ch in body.card_number if ch.isdigit())
    if len(digits) < 12: raise HTTPException(422,"Enter a valid test card number")
    package=next((x for x in TOKEN_PACKAGES if x["price"]==int(body.amount)),None)
    if not package: raise HTTPException(422,"Choose one of the configured demo packages: $10, $25, or $50")
    wallet=wallet_for(s,u.id);before=wallet.token_balance;after=token_ledger(s,wallet,"PURCHASE",package["tokens"],"PURCHASE",package["id"],f"Purchased {package['tokens']} tokens")
    add_audit(s,"billing.token_purchase",user_id=u.id,details={"package":package["id"],"tokens":package["tokens"]});s.commit()
    realtime_hub.publish_from_sync("billing.updated", billing_event_data(s, u.id), topic="billing", user_id=u.id)
    return {"wallet_balance":after,"credited":package["tokens"],"tokens_added":package["tokens"],"previous_balance":before,"card_last4":digits[-4:],"mode":"demo"}

# ============================================================
# VIDEO ARTIFACT ENDPOINTS
# ============================================================

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

@app.post("/media/artifacts/upload")
async def upload_artifact(file: UploadFile = File(...), u: User = Depends(current_user), s: Session = Depends(db)):
    """Accept a video upload, validate it, store it durably, return artifact metadata."""
    ext = Path(file.filename or "video.mp4").suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_VIDEO_EXTENSIONS))}")
    content_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if content_type not in ALLOWED_VIDEO_MIMES:
        raise HTTPException(415, f"Unsupported MIME type '{content_type}'")

    artifact_id = f"art_{secrets.token_hex(8)}"
    art_dir = ARTIFACTS_DIR / artifact_id
    art_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(file.filename or "video.mp4")
    dest = art_dir / safe_name

    size = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_VIDEO_UPLOAD_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, f"File too large. Max allowed: {MAX_VIDEO_UPLOAD_BYTES // (1024*1024)} MB")
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise HTTPException(500, f"Upload failed: {e}")

    probe = probe_video_file(dest)
    if not probe.get("valid"):
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"Invalid video file: {probe.get('error', 'unknown error')}")

    duration = probe.get("duration", 0) or 0
    if duration > MAX_VIDEO_DURATION_SECONDS:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"Video too long ({duration:.1f}s). Max allowed: {MAX_VIDEO_DURATION_SECONDS}s")

    checksum = _sha256_file(dest)
    rel_path = str(Path(artifact_id) / safe_name)

    art = JobArtifact(
        id=artifact_id,
        job_id=None,
        user_id=u.id,
        artifact_type="input",
        filename=safe_name,
        media_type=content_type,
        file_path=rel_path,
        size_bytes=size,
        checksum_sha256=checksum,
        meta_data={
            "duration": duration,
            "width": probe.get("width"),
            "height": probe.get("height"),
            "codec": probe.get("codec"),
            "fps": probe.get("fps"),
            "has_audio": probe.get("has_audio"),
            "original_filename": file.filename
        }
    )
    s.add(art)
    add_audit(s, "artifact.uploaded", user_id=u.id, details={"artifact_id": artifact_id, "filename": safe_name, "size_bytes": size})
    s.commit()
    return {
        "artifact_id": artifact_id,
        "filename": safe_name,
        "size_bytes": size,
        "checksum_sha256": checksum,
        "media_type": content_type,
        "meta": art.meta_data
    }

@app.get("/media/artifacts/{artifact_id}")
def get_artifact_meta(artifact_id: str, u: User = Depends(current_user), s: Session = Depends(db)):
    art = s.get(JobArtifact, artifact_id)
    if not art or art.user_id != u.id:
        raise HTTPException(404, "Artifact not found")
    return {
        "artifact_id": art.id,
        "job_id": art.job_id,
        "filename": art.filename,
        "size_bytes": art.size_bytes,
        "media_type": art.media_type,
        "checksum_sha256": art.checksum_sha256,
        "meta": art.meta_data or {},
        "created_at": art.created_at
    }

@app.get("/jobs/{job_id}/artifacts/{artifact_id}/download")
def download_artifact(job_id: str, artifact_id: str, u: User = Depends(current_user), s: Session = Depends(db)):
    """Stream a job output artifact to the authenticated job owner."""
    j = s.get(Job, job_id)
    if not j or j.user_id != u.id:
        raise HTTPException(404, "Job not found")
    art = s.get(JobArtifact, artifact_id)
    if not art or art.job_id != job_id:
        raise HTTPException(404, "Artifact not found")
    if not art.file_path:
        raise HTTPException(404, "Artifact has no stored file")
    file_path = ARTIFACTS_DIR / art.file_path
    if not file_path.exists():
        raise HTTPException(404, "Artifact file missing from storage")
    return FileResponse(
        path=str(file_path),
        media_type=art.media_type or "application/octet-stream",
        filename=art.filename
    )

@app.get("/providers/jobs/{job_id}/artifacts/{artifact_id}/download")
def provider_download_artifact(job_id: str, artifact_id: str, _ = Depends(provider_auth), s: Session = Depends(db)):
    """Allow a provider to download an input artifact securely."""
    j = s.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    art = s.get(JobArtifact, artifact_id)
    if not art or art.job_id != job_id:
        raise HTTPException(404, "Artifact not found for this job")
    if not art.file_path:
        raise HTTPException(404, "Artifact has no stored file")
    file_path = ARTIFACTS_DIR / art.file_path
    if not file_path.exists():
        raise HTTPException(404, "Artifact file missing from storage")
    return FileResponse(
        path=str(file_path),
        media_type=art.media_type or "application/octet-stream",
        filename=art.filename
    )

@app.post("/providers/jobs/{job_id}/artifacts/upload")
async def provider_upload_artifact(job_id: str, file: UploadFile = File(...), artifact_type: str = "output", _ = Depends(provider_auth), s: Session = Depends(db)):
    """Provider uploads a processed output artifact for a job."""
    j = s.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")

    artifact_id = f"art_{secrets.token_hex(8)}"
    art_dir = ARTIFACTS_DIR / artifact_id
    art_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(file.filename or f"{job_id}_output.mp4")
    dest = art_dir / safe_name

    size = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                out.write(chunk)
    except Exception as e:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise HTTPException(500, f"Upload failed: {e}")

    checksum = _sha256_file(dest)
    rel_path = str(Path(artifact_id) / safe_name)
    content_type = (file.content_type or "video/mp4").split(";")[0].strip()

    # Probe output for metadata
    probe = probe_video_file(dest)

    art = JobArtifact(
        id=artifact_id,
        job_id=job_id,
        user_id=j.user_id,
        artifact_type=artifact_type,
        filename=safe_name,
        media_type=content_type,
        file_path=rel_path,
        size_bytes=size,
        checksum_sha256=checksum,
        meta_data={"probe": probe}
    )
    s.add(art)
    add_audit(s, "artifact.provider_upload", user_id=j.user_id, provider_id=j.provider_id, job_id=job_id,
              details={"artifact_id": artifact_id, "size_bytes": size, "valid": probe.get("valid")})
    s.commit()
    return {
        "artifact_id": artifact_id,
        "filename": safe_name,
        "size_bytes": size,
        "checksum_sha256": checksum,
        "valid": probe.get("valid"),
        "meta": probe
    }


# ============================================================
# REMOTE STREAM ENCODING ENDPOINTS
# ============================================================

MEDIAMTX_INGEST_URL = (os.getenv("MEDIAMTX_INGEST_URL") or "rtmp://127.0.0.1:1935").strip().rstrip("/")
MEDIAMTX_PROVIDER_READ_URL = (os.getenv("MEDIAMTX_PROVIDER_READ_URL") or os.getenv("MEDIAMTX_INTERNAL_URL") or "rtsp://127.0.0.1:8554").strip().rstrip("/")
MEDIAMTX_WEBRTC_URL = (os.getenv("MEDIAMTX_WEBRTC_URL") or "http://127.0.0.1:8889").strip().rstrip("/")
MEDIA_SERVER_ALLOW_LOOPBACK = os.getenv("MEDIA_SERVER_ALLOW_LOOPBACK", "true").lower() in ("1", "true", "yes")
STREAM_ACTIVE_STATUSES = ("CREATED", "ALLOCATED", "STARTING", "WAITING_FOR_INPUT", "INGESTING", "RECEIVING", "ENCODING", "STREAMING", "STOPPING")
STREAM_TERMINAL_STATUSES = ("STOPPED", "COMPLETED", "FAILED")

def _validate_media_server_config():
    for label, value in (("MEDIAMTX_INGEST_URL", MEDIAMTX_INGEST_URL), ("MEDIAMTX_PROVIDER_READ_URL", MEDIAMTX_PROVIDER_READ_URL)):
        if not value:
            raise HTTPException(503, f"Media ingest is not configured: set {label} to the reachable MediaMTX base address")
        try:
            parsed = urllib.parse.urlsplit(value)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError:
            raise HTTPException(503, f"Media ingest configuration {label} is not a valid URL")
        expected_schemes = ("rtmp", "rtmps") if label == "MEDIAMTX_INGEST_URL" else ("rtsp", "rtsps")
        if not parsed.scheme or not hostname or parsed.scheme.lower() not in expected_schemes:
            protocols = "RTMP(S)" if label == "MEDIAMTX_INGEST_URL" else "RTSP(S)"
            raise HTTPException(503, f"Media ingest configuration {label} must be a {protocols} base URL with a hostname")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise HTTPException(503, f"Media ingest configuration {label} must contain only the protocol, host, and optional port; session credentials and paths are generated by Nexora")
        if port is not None and not 1 <= port <= 65535:
            raise HTTPException(503, f"Media ingest configuration {label} has an invalid port")
        try:
            loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            loopback = hostname.lower() == "localhost"
        if loopback and not MEDIA_SERVER_ALLOW_LOOPBACK:
            raise HTTPException(503, f"Media ingest configuration {label} uses loopback, which other devices cannot reach; configure the MediaMTX LAN/public address")

def _validate_webrtc_publish_url():
    try:
        parsed = urllib.parse.urlsplit(MEDIAMTX_WEBRTC_URL)
        _ = parsed.port
    except ValueError:
        raise HTTPException(503, "Browser capture configuration MEDIAMTX_WEBRTC_URL is not a valid URL")
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(503, "Browser capture requires MEDIAMTX_WEBRTC_URL to be an HTTP(S) base URL without credentials or query parameters")

def _provider_stream_encoder(provider: Provider):
    info = provider.system_info or {}
    available = info.get("stream_encoders") or []
    if "h264_nvenc" in available and (info.get("cuda_available") or "nvidia" in (provider.gpu_name or "").lower()):
        return "h264_nvenc"
    gpu_name = (provider.gpu_name or "").lower()
    if "h264_qsv" in available and "intel" in gpu_name:
        return "h264_qsv"
    if "h264_amf" in available and ("amd" in gpu_name or "radeon" in gpu_name):
        return "h264_amf"
    return "libx264" if "libx264" in available else None

def stream_session_data(session: StreamSession, include_keys: bool = False, provider_name: Optional[str] = None):
    data = {
        "id": session.id,
        "user_id": session.user_id,
        "provider_id": session.provider_id,
        "provider_name": provider_name,
        "status": session.status,
        "destination_platform": session.destination_platform,
        "destination_url": session.destination_url,
        "destination_key_masked": session.destination_key_masked,
        "profile_name": session.profile_name,
        "encoding_config": session.encoding_config or {},
        "latest_metrics": session.latest_metrics or {},
        "error_message": session.error_message,
        "tokens_per_minute": session.tokens_per_minute,
        "total_tokens_billed": session.total_tokens_billed,
        "created_at": session.created_at,
        "started_at": session.started_at,
        "completed_at": session.completed_at,
        "ingest_server": f"{MEDIAMTX_INGEST_URL}/live" if MEDIAMTX_INGEST_URL else None,
        "ingest_path": f"live/{session.id}",
        "source_mode": (session.encoding_config or {}).get("source_mode", "obs"),
    }
    if data["source_mode"] == "browser_capture":
        data["webrtc_publish_url"] = f"{MEDIAMTX_WEBRTC_URL}/{session.ingest_path}/whip" if MEDIAMTX_WEBRTC_URL else None
    if include_keys:
        if data["source_mode"] == "browser_capture":
            # WHIP carries session credentials in Basic auth, never the URL.
            data["browser_publish_credential"] = {"username": "nexora", "password": session.publish_key}
        else:
            # RTMP clients carry credentials as user/pass query parameters.
            data["stream_key"] = f"{session.id}?{urllib.parse.urlencode({'user': 'nexora', 'pass': session.publish_key})}"
    return data

def publish_stream_update(s: Session, session: StreamSession):
    provider = s.get(Provider, session.provider_id) if session.provider_id else None
    # Never fan out destination credentials or ingest publish keys. The owning
    # user already receives the one-time key from the authenticated REST action.
    realtime_hub.publish_from_sync(
        "stream.updated",
        {"session": stream_session_data(session, provider_name=provider.name if provider else None)},
        topic="streams",
        user_id=session.user_id,
        provider_id=session.provider_id,
    )

@app.post("/stream/sessions")
def create_stream_session(body: StreamSessionCreate, u: User = Depends(current_user), s: Session = Depends(db)):
    _validate_media_server_config()
    if body.source_mode not in ("obs", "browser_capture"):
        raise HTTPException(422, "Choose OBS or Browser Capture as the stream input")
    if body.source_mode == "browser_capture":
        _validate_webrtc_publish_url()
    if body.destination_platform not in ("youtube", "twitch", "custom_rtmp"):
        raise HTTPException(422, "Choose a supported stream destination platform")
    if body.profile not in STREAM_PROFILES:
        raise HTTPException(422, "Choose a supported stream encoding profile")

    active = s.query(StreamSession).filter(
        StreamSession.user_id == u.id,
        StreamSession.status.in_(STREAM_ACTIVE_STATUSES)
    ).first()
    if active:
        raise HTTPException(409, f"You already have an active stream session ({active.id}). Stop it before starting a new one.")

    wallet = wallet_for(s, u.id)
    if wallet.token_balance < 10:
        raise HTTPException(402, detail={
            "message": "Insufficient token balance to start a stream session",
            "required": 10,
            "available": wallet.token_balance
        })

    profile_key = body.profile
    profile_cfg = STREAM_PROFILES[profile_key]

    dest_url, dest_key, masked_key = validate_destination_target(body.destination_url, body.destination_key)
    destination_host = urllib.parse.urlsplit(dest_url).hostname.lower()
    if body.destination_platform == "youtube" and not (destination_host == "youtube.com" or destination_host.endswith(".youtube.com")):
        raise HTTPException(422, "The YouTube destination must use a youtube.com ingest host")
    if body.destination_platform == "twitch" and not (destination_host == "twitch.tv" or destination_host.endswith(".twitch.tv")):
        raise HTTPException(422, "The Twitch destination must use a twitch.tv ingest host")

    reqs = {
        "workload": "remote_stream_encode",
        "cpu_cores": 4 if profile_key in ("1080p60", "720p60") else 2,
        "ram_gb": 4
    }
    p = compatible_provider(s, reqs)
    if not p:
        raise HTTPException(409, stream_provider_unavailable_reason(s, reqs))
    selected_encoder = _provider_stream_encoder(p)
    if not selected_encoder:
        raise HTTPException(409, "The selected provider does not report a usable H.264 encoder. Install an FFmpeg build with libx264 or a supported hardware encoder and restart the provider agent.")

    session_id = f"stream_{secrets.token_hex(6)}"
    publish_key = f"nxt_live_{secrets.token_hex(12)}"
    read_key = f"nxt_read_{secrets.token_hex(12)}"
    enc_dest_key = encrypt_secret(dest_key)

    p.status = "BUSY"

    session = StreamSession(
        id=session_id,
        user_id=u.id,
        provider_id=p.id,
        status="ALLOCATED",
        ingest_path=f"live/{session_id}",
        publish_key=publish_key,
        read_key=read_key,
        destination_platform=body.destination_platform,
        destination_url=dest_url,
        destination_key_masked=masked_key,
        destination_key_encrypted=enc_dest_key,
        profile_name=profile_key,
        encoding_config={**profile_cfg, "video_encoder": selected_encoder, "source_mode": body.source_mode},
        tokens_per_minute=profile_cfg.get("tokens_per_minute", 2),
        total_tokens_billed=0,
        latest_metrics={"status": "ALLOCATED"}
    )
    s.add(session)
    add_audit(s, "stream.created", user_id=u.id, provider_id=p.id, details={"session_id": session_id, "profile": profile_key})
    s.commit()
    s.refresh(session)
    publish_stream_update(s, session)
    return stream_session_data(session, include_keys=True, provider_name=p.name)

@app.get("/stream/sessions/active")
def get_active_stream_session(u: User = Depends(current_user), s: Session = Depends(db)):
    session = s.query(StreamSession).filter(
        StreamSession.user_id == u.id,
        StreamSession.status.in_(STREAM_ACTIVE_STATUSES)
    ).order_by(StreamSession.created_at.desc()).first()
    if not session:
        return {"active": False, "session": None}
    p = s.get(Provider, session.provider_id) if session.provider_id else None
    return {"active": True, "session": stream_session_data(session, include_keys=True, provider_name=p.name if p else None)}

@app.get("/stream/sessions/{session_id}")
def get_stream_session(session_id: str, u: User = Depends(current_user), s: Session = Depends(db)):
    session = s.get(StreamSession, session_id)
    if not session or session.user_id != u.id:
        raise HTTPException(404, "Stream session not found")
    p = s.get(Provider, session.provider_id) if session.provider_id else None
    return stream_session_data(session, include_keys=False, provider_name=p.name if p else None)

@app.post("/stream/sessions/{session_id}/stop")
def stop_stream_session(session_id: str, u: User = Depends(current_user), s: Session = Depends(db)):
    session = s.query(StreamSession).filter(StreamSession.id == session_id).with_for_update().first()
    if not session or session.user_id != u.id:
        raise HTTPException(404, "Stream session not found")
    if session.status in STREAM_TERMINAL_STATUSES:
        return stream_session_data(session)

    if session.status in ("ALLOCATED", "RECEIVING"):
        # No provider process was claimed yet, so there is nothing to signal or wait for.
        session.status = "STOPPED"
        session.completed_at = datetime.now(timezone.utc)
        session.publish_key = ""
        session.read_key = ""
        session.destination_key_encrypted = ""
        provider = s.get(Provider, session.provider_id) if session.provider_id else None
        if provider:
            provider.status = "ONLINE"
    else:
        session.status = "STOPPING"
    add_audit(s, "stream.stop_requested", user_id=u.id, provider_id=session.provider_id, details={"session_id": session_id})
    s.commit()
    publish_stream_update(s, session)
    return stream_session_data(session)

@app.post("/stream/internal/mediamtx/auth")
def mediamtx_auth(body: MediaMTXAuthPayload, s: Session = Depends(db)):
    """Webhook invoked by MediaMTX to authenticate publish and read connections."""
    path = (body.path or "").strip("/ ")
    session_id = path.split("/")[-1] if "/" in path else path

    key = body.password
    if not key and body.query:
        qs = urllib.parse.parse_qs(body.query)
        key = (qs.get("key") or qs.get("pass") or [None])[0]

    session = s.get(StreamSession, session_id)
    if not session or path != f"live/{session.id}" or session.status in STREAM_TERMINAL_STATUSES or session.status == "STOPPING":
        raise HTTPException(401, "Invalid session or session not active")
    # RTSP token clients normally have no username; MediaMTX documents empty
    # user/password fields for these requests. Publish still uses the Nexora
    # username in its separate RTMP credential flow.
    if body.user not in (None, "", "nexora"):
        raise HTTPException(401, "Invalid session credentials")

    if body.action == "publish":
        if body.user not in (None, "nexora"):
            raise HTTPException(401, "Invalid publish credentials")
        source_mode = (session.encoding_config or {}).get("source_mode", "obs")
        expected_protocol = "webrtc" if source_mode == "browser_capture" else "rtmp"
        if (body.protocol or "").lower() != expected_protocol:
            raise HTTPException(401, "Invalid publish protocol for this stream session")
        if not key or not secrets.compare_digest(key, session.publish_key):
            raise HTTPException(401, "Invalid publish stream key")
        if session.status in ("ALLOCATED", "STARTING", "WAITING_FOR_INPUT"):
            session.status = "RECEIVING"
            s.commit()
            publish_stream_update(s, session)
        return {"status": "ok", "action": "publish"}

    elif body.action == "read":
        # MediaMTX's RTSP token authentication sends the URL's `token` query
        # parameter as the dedicated `token` field in its HTTP auth webhook.
        if body.protocol != "rtsp":
            raise HTTPException(401, "Invalid read protocol")
        if not body.token or not secrets.compare_digest(body.token, session.read_key):
            raise HTTPException(401, "Invalid read key")
        return {"status": "ok", "action": "read"}

    raise HTTPException(400, "Unknown auth action")

@app.get("/providers/{provider_id}/streams/pending")
def provider_pending_streams(provider_id: str, _ = Depends(provider_auth), s: Session = Depends(db)):
    # Kept as a compatibility endpoint, but never returns session credentials.
    return []

@app.post("/providers/{provider_id}/streams/claim")
def provider_claim_stream(provider_id: str, _ = Depends(provider_auth), s: Session = Depends(db)):
    provider = s.get(Provider, provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")
    if provider.status not in ("ONLINE", "BUSY"):
        return {"command": "NONE"}
    sess = s.query(StreamSession).filter(
        StreamSession.provider_id == provider_id,
        StreamSession.status.in_(["ALLOCATED", "RECEIVING"]),
    ).order_by(StreamSession.created_at.asc()).with_for_update().first()
    if not sess:
        return {"command": "NONE"}
    sess.status = "STARTING"
    sess.latest_metrics = {"status": "STARTING"}
    s.commit()
    publish_stream_update(s, sess)
    try:
        plain_dest_key = decrypt_secret(sess.destination_key_encrypted)
    except Exception:
        sess.status = "FAILED"
        sess.error_message = "Destination credentials could not be decrypted. Re-enter the stream key and retry."
        sess.completed_at = datetime.now(timezone.utc)
        sess.publish_key = ""
        sess.read_key = ""
        sess.destination_key_encrypted = ""
        provider.status = "ONLINE"
        s.commit()
        publish_stream_update(s, sess)
        return {"command": "NONE"}
    if not MEDIAMTX_PROVIDER_READ_URL:
        sess.status = "FAILED"
        sess.error_message = "MediaMTX provider read address is not configured."
        sess.completed_at = datetime.now(timezone.utc)
        sess.publish_key = ""
        sess.read_key = ""
        sess.destination_key_encrypted = ""
        provider.status = "ONLINE"
        s.commit()
        publish_stream_update(s, sess)
        raise HTTPException(503, "MediaMTX provider read address is not configured")
    return {"command": "START_STREAM", "session": {
        "session_id": sess.id,
        "provider_id": provider_id,
        "source_url": f"{MEDIAMTX_PROVIDER_READ_URL}/live/{sess.id}?{urllib.parse.urlencode({'token': sess.read_key})}",
        "destination_url": sess.destination_url,
        "destination_key": plain_dest_key,
        "profile_name": sess.profile_name,
        "encoding_config": sess.encoding_config or {},
    }}

@app.post("/providers/streams/{session_id}/heartbeat")
def provider_stream_heartbeat(session_id: str, body: StreamHeartbeatPayload, _ = Depends(provider_auth), s: Session = Depends(db)):
    sess = s.query(StreamSession).filter(StreamSession.id == session_id).with_for_update().first()
    if not sess:
        raise HTTPException(404, "Stream session not found")
    if sess.provider_id != body.provider_id:
        raise HTTPException(403, "Stream session is assigned to another provider")

    now = datetime.now(timezone.utc)
    if sess.status == "STOPPING":
        return {"command": "STOP_STREAM", "action": "stop", "reason": "user_cancelled"}

    if sess.status in STREAM_TERMINAL_STATUSES:
        return {"command": "STOP_STREAM", "action": "stop", "reason": "session_terminated"}

    valid_statuses = {"STARTING", "WAITING_FOR_INPUT", "RECEIVING", "ENCODING", "STREAMING"}
    if body.status not in valid_statuses:
        raise HTTPException(422, "Invalid stream process status")
    sess.status = body.status
    sess.latest_metrics = {**(body.metrics or {}), "status": body.status}

    if body.status != "STREAMING" and sess.started_at and sess.last_billed_at:
        # Pause billable runtime while source/destination is not verified as streaming.
        sess.last_billed_at = now

    wallet = wallet_for(s, sess.user_id)
    last_bill = sess.last_billed_at if (sess.last_billed_at and sess.last_billed_at.tzinfo) else (sess.last_billed_at.replace(tzinfo=timezone.utc) if sess.last_billed_at else now)
    elapsed_since_bill = (now - last_bill).total_seconds()
    balance_changed = False

    # Waiting for OBS/input, encoder initialization, and failed destination attempts are not billable.
    if body.status == "STREAMING" and sess.started_at is None:
        sess.started_at = now
        sess.last_billed_at = now
    if body.status == "STREAMING" and elapsed_since_bill >= 60:
        minutes_to_bill = int(elapsed_since_bill // 60)
        tokens_due = minutes_to_bill * sess.tokens_per_minute

        if wallet.token_balance < tokens_due:
            drained = max(0, wallet.token_balance)
            if drained:
                token_ledger(s, wallet, "STREAM_USAGE", -drained, "STREAM", sess.id, f"Final stream usage for {sess.id}", sess.id)
                sess.total_tokens_billed += drained
            sess.status = "STOPPING"
            sess.error_message = "Budget exhausted: insufficient tokens"
            s.commit()
            publish_stream_update(s, sess)
            realtime_hub.publish_from_sync("billing.updated", billing_event_data(s, sess.user_id), topic="billing", user_id=sess.user_id)
            return {"command": "STOP_STREAM", "action": "stop", "reason": "insufficient_tokens"}
        else:
            token_ledger(s, wallet, "STREAM_USAGE", -tokens_due, "STREAM", sess.id, f"Stream compute minute for {sess.id}", sess.id)
            sess.total_tokens_billed += tokens_due
            sess.last_billed_at = now
            balance_changed = True
            s.commit()

    s.commit()
    publish_stream_update(s, sess)
    if balance_changed:
        realtime_hub.publish_from_sync("billing.updated", billing_event_data(s, sess.user_id), topic="billing", user_id=sess.user_id)
    return {"action": "continue", "token_balance": wallet.token_balance}

@app.post("/providers/streams/{session_id}/stopped")
def provider_stream_stopped(session_id: str, body: StreamHeartbeatPayload, _ = Depends(provider_auth), s: Session = Depends(db)):
    sess = s.query(StreamSession).filter(StreamSession.id == session_id).with_for_update().first()
    if not sess:
        raise HTTPException(404, "Stream session not found")
    if sess.provider_id != body.provider_id:
        raise HTTPException(403, "Stream session is assigned to another provider")
    if sess.status in STREAM_TERMINAL_STATUSES:
        return {"ok": True, "status": sess.status}

    now = datetime.now(timezone.utc)
    sess.completed_at = now
    if body.error:
        sess.status = "FAILED"
        safe_error = str(body.error).strip()
        # Provider reports are untrusted; never persist a URL, credential, or raw FFmpeg output.
        sess.error_message = safe_error[:240] if not re.search(r"(?i)(rtmps?://|rtsps?://|key=|stream.?key|password)", safe_error) else "The provider could not complete stream encoding. Check the source and destination configuration."
    else:
        sess.status = "STOPPED" if sess.status == "STOPPING" else "COMPLETED"

    if body.metrics:
        sess.latest_metrics = body.metrics

    # Credentials are session-scoped. Revoke them as soon as the process is finalized.
    sess.publish_key = ""
    sess.read_key = ""
    sess.destination_key_encrypted = ""

    p = s.get(Provider, sess.provider_id)
    if p:
        p.status = "ONLINE"

    add_audit(s, "stream.ended", user_id=sess.user_id, provider_id=sess.provider_id, details={
        "session_id": session_id,
        "status": sess.status,
        "total_tokens_billed": sess.total_tokens_billed,
        "error": sess.error_message
    })
    s.commit()
    publish_stream_update(s, sess)
    if p:
        realtime_hub.publish_from_sync("provider.status_changed", {"provider": provider_data(p)}, topic="providers", provider_id=p.id)
    return {"ok": True, "status": sess.status}

