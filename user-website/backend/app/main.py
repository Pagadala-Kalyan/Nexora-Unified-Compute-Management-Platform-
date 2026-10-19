import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

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

class Register(BaseModel): email: str; password: str = Field(min_length=8)
class Login(Register): pass
class JobCreate(BaseModel): name: str = Field(min_length=2, max_length=100); workload: str = "matrix_multiply"; requirements: dict = Field(default_factory=dict)
class ProviderRegister(BaseModel): id: str; name: str; cpu_cores: int = Field(ge=1); ram_gb: float = Field(gt=0); gpu_name: Optional[str]=None; gpu_memory_gb: float=0; cost_per_hour: float=.25; system_info: Optional[dict]=None
class Heartbeat(BaseModel): status: str="ONLINE"; utilization: dict=Field(default_factory=dict)
class Update(BaseModel): status: Optional[JobStatus]=None; progress: Optional[int]=Field(None, ge=0, le=100); result: Optional[dict]=None; actual_cost: Optional[float]=None; attempt: Optional[int]=None
class DemoTopUp(BaseModel): amount: float = Field(gt=0, le=10000); card_number: str = Field(min_length=12, max_length=23); cardholder: str = Field(min_length=2, max_length=80); expiry: str = Field(min_length=4, max_length=7); cvc: str = Field(min_length=3, max_length=4)
class TokenPurchase(BaseModel): package_id: str

app=FastAPI(title="Nexora UCMP Control Plane", version="0.1.0")
# Allow any local development port (Vite/Next commonly choose a different port
# when one is occupied) while keeping remote browser origins explicitly blocked.
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000").split(","), allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app"), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
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
def provider_auth(x_provider_token: str=Header(...)):
    if not secrets.compare_digest(x_provider_token, PROVIDER_TOKEN): raise HTTPException(401,"Provider authentication failed")
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
    candidates=[p for p in s.query(Provider).all() if p.id!=exclude_id and p.status in ("ONLINE","AVAILABLE") and p.cpu_cores>=requirements.get("cpu_cores",1) and p.ram_gb>=requirements.get("ram_gb",1) and (not requirements.get("gpu_required") or p.gpu_name) and (workload != "video_compress" or (p.system_info or {}).get("ffmpeg_available"))]
    return min(candidates,key=lambda x:x.cost_per_hour/(max(x.reliability,1)/100)) if candidates else None
def recover_lost_providers():
    """Detect provider loss and re-dispatch checkpointed controlled workloads with generation fencing."""
    while True:
        time.sleep(5)
        s=SessionLocal()
        try:
            now=datetime.now(timezone.utc)
            for failed in s.query(Provider).filter(Provider.status.in_(["ONLINE","BUSY","AVAILABLE"])).all():
                last=failed.last_heartbeat if failed.last_heartbeat.tzinfo else failed.last_heartbeat.replace(tzinfo=timezone.utc)
                if (now-last).total_seconds() <= int(os.getenv("HEARTBEAT_TIMEOUT_SECONDS","20")): continue
                failed.status="OFFLINE"
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
                        add_audit(s, "job.recovered", user_id=j.user_id, provider_id=replacement.id, job_id=j.id,
                                  details={"failed_provider": failed.id, "new_provider": replacement.id, "attempt": j.attempt, "checkpoint_id": checkpoint.id if checkpoint else None})
                    else:
                        j.status="FAILED"
                        j.result={"error":"Provider lost; no compatible recovery provider or checkpoint available."}
                        refund_reservation(s,j,f"Refund after provider loss for {j.name}")
                        add_audit(s, "job.failed_unrecoverable", user_id=j.user_id, provider_id=failed.id, job_id=j.id,
                                  details={"failed_provider": failed.id})
            s.commit()
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
                ("providers", [("system_info", "TEXT DEFAULT '{}'")])
            ]:
                existing = [r[1] for r in s.execute(text(f"PRAGMA table_info({table})")).fetchall()]
                for col_name, col_def in cols:
                    if col_name not in existing:
                        s.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))
            s.commit()
    except Exception as ex:
        print(f"[SCHEMA MIGRATION WARNING] {ex}")

@app.on_event("startup")
def init():
    Base.metadata.create_all(engine)
    s=SessionLocal()
    try:
        ensure_schema_columns(s)
        for user in s.query(User).all(): wallet_for(s,user.id)
        s.commit()
    finally: s.close()
    threading.Thread(target=recover_lost_providers,daemon=True,name="provider-recovery-monitor").start()
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
    s.commit();return provider_data(p)
@app.post("/providers/{provider_id}/heartbeat")
def heartbeat(provider_id:str,body:Heartbeat,_=Depends(provider_auth),s:Session=Depends(db)):
    p=s.get(Provider,provider_id)
    if not p: raise HTTPException(404,"Provider not registered")
    p.status=body.status;p.utilization=body.utilization;p.last_heartbeat=datetime.now(timezone.utc);s.commit();return {"ok":True}
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
    add_audit(s,"job.submitted",user_id=u.id,provider_id=p.id,job_id=j.id,details={"workload":body.workload,"estimated_tokens":estimated_tokens});s.commit();return job_data(j,s)
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
    j.status="CANCELLED";s.commit();return job_data(j,s)
@app.post("/jobs/stop-all")
def stop_all_jobs(u:User=Depends(current_user),s:Session=Depends(db)):
    jobs=s.query(Job).filter(Job.user_id==u.id,Job.status.in_(["QUEUED","SCHEDULED","RUNNING","RECOVERING"])).all()
    for j in jobs: j.status="CANCELLED";j.completed_at=datetime.now(timezone.utc)
    s.commit();return {"cancelled":len(jobs)}
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
    return job_data(j,s)

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
    return {
        "id": c.id,
        "seq": c.seq,
        "attempt": c.attempt,
        "progress": c.progress,
        "state_hash": c.state_hash
    }

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
    return {"active_jobs":sum(j.status in ("SCHEDULED","RUNNING","RECOVERING") for j in js),"available_nodes":sum(p.status in ("ONLINE","AVAILABLE") for p in ps),"token_balance":wallet.token_balance,"low_balance":wallet.token_balance<LOW_TOKEN_THRESHOLD,"gpu_utilization":round(sum(p.utilization.get("gpu",0) for p in ps)/n,1),"cpu_utilization":round(sum(p.utilization.get("cpu",0) for p in ps)/n,1),"ram_utilization":round(sum(p.utilization.get("ram",0) for p in ps)/n,1),"recent_jobs":[job_data(j,s) for j in sorted(js,key=lambda x:x.created_at,reverse=True)[:5]]}
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
    add_audit(s,"billing.token_purchase",user_id=u.id,details={"package":package["id"],"tokens":package["tokens"]});s.commit();return {"success":True,"tokens_added":package["tokens"],"previous_balance":before,"new_balance":after}
@app.post("/billing/demo-topup")
def demo_topup(body:DemoTopUp,u:User=Depends(current_user),s:Session=Depends(db)):
    # College-project demo only: card data is validated for form completeness and never stored or transmitted.
    digits="".join(ch for ch in body.card_number if ch.isdigit())
    if len(digits) < 12: raise HTTPException(422,"Enter a valid test card number")
    package=next((x for x in TOKEN_PACKAGES if x["price"]==int(body.amount)),None)
    if not package: raise HTTPException(422,"Choose one of the configured demo packages: $10, $25, or $50")
    wallet=wallet_for(s,u.id);before=wallet.token_balance;after=token_ledger(s,wallet,"PURCHASE",package["tokens"],"PURCHASE",package["id"],f"Purchased {package['tokens']} tokens")
    add_audit(s,"billing.token_purchase",user_id=u.id,details={"package":package["id"],"tokens":package["tokens"]});s.commit()
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

