import hashlib
import os
import secrets
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nexora.db")
# Render provides PostgreSQL URLs without the explicit SQLAlchemy driver name.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
JWT_SECRET = os.getenv("JWT_SECRET", "development-only-change-me")
PROVIDER_TOKEN = os.getenv("PROVIDER_SHARED_TOKEN", "local-demo-token")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
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

class Base(DeclarativeBase): pass
class JobStatus(str, Enum): QUEUED="QUEUED"; SCHEDULED="SCHEDULED"; RUNNING="RUNNING"; COMPLETED="COMPLETED"; FAILED="FAILED"; RECOVERING="RECOVERING"; CANCELLED="CANCELLED"
class Provider(Base):
    __tablename__="providers"
    id: Mapped[str]=mapped_column(String, primary_key=True); name: Mapped[str]=mapped_column(String)
    cpu_cores: Mapped[int]=mapped_column(Integer); ram_gb: Mapped[float]=mapped_column(Float); gpu_name: Mapped[Optional[str]]=mapped_column(String, nullable=True)
    gpu_memory_gb: Mapped[float]=mapped_column(Float, default=0); cost_per_hour: Mapped[float]=mapped_column(Float, default=.25)
    status: Mapped[str]=mapped_column(String, default="ONLINE"); reliability: Mapped[float]=mapped_column(Float, default=100)
    utilization: Mapped[dict]=mapped_column(JSON, default=dict); last_heartbeat: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class User(Base):
    __tablename__="users"; id: Mapped[int]=mapped_column(primary_key=True); email: Mapped[str]=mapped_column(String, unique=True); password_hash: Mapped[str]=mapped_column(String); wallet_balance: Mapped[float]=mapped_column(Float, default=100)
class Job(Base):
    __tablename__="jobs"; id: Mapped[str]=mapped_column(String, primary_key=True); name: Mapped[str]=mapped_column(String); workload: Mapped[str]=mapped_column(String)
    requirements: Mapped[dict]=mapped_column(JSON, default=dict); status: Mapped[str]=mapped_column(String, default="QUEUED"); progress: Mapped[int]=mapped_column(Integer, default=0)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id")); provider_id: Mapped[Optional[str]]=mapped_column(ForeignKey("providers.id"), nullable=True); result: Mapped[Optional[dict]]=mapped_column(JSON, nullable=True)
    estimated_cost: Mapped[float]=mapped_column(Float, default=0); actual_cost: Mapped[float]=mapped_column(Float, default=0); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)); started_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True), nullable=True); completed_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True), nullable=True)
class Checkpoint(Base):
    __tablename__="checkpoints"; id: Mapped[str]=mapped_column(String, primary_key=True); job_id: Mapped[str]=mapped_column(ForeignKey("jobs.id")); provider_id: Mapped[str]=mapped_column(String); progress: Mapped[int]=mapped_column(Integer); payload: Mapped[dict]=mapped_column(JSON, default=dict); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Register(BaseModel): email: str; password: str = Field(min_length=8)
class Login(Register): pass
class JobCreate(BaseModel): name: str = Field(min_length=2, max_length=100); workload: str = "matrix_multiply"; requirements: dict = Field(default_factory=dict)
class ProviderRegister(BaseModel): id: str; name: str; cpu_cores: int = Field(ge=1); ram_gb: float = Field(gt=0); gpu_name: Optional[str]=None; gpu_memory_gb: float=0; cost_per_hour: float=.25
class Heartbeat(BaseModel): status: str="ONLINE"; utilization: dict=Field(default_factory=dict)
class Update(BaseModel): status: Optional[JobStatus]=None; progress: Optional[int]=Field(None, ge=0, le=100); result: Optional[dict]=None; actual_cost: Optional[float]=None
class DemoTopUp(BaseModel): amount: float = Field(gt=0, le=10000); card_number: str = Field(min_length=12, max_length=23); cardholder: str = Field(min_length=2, max_length=80); expiry: str = Field(min_length=4, max_length=7); cvc: str = Field(min_length=3, max_length=4)

app=FastAPI(title="Nexora UCMP Control Plane", version="0.1.0")
# Allow any local development port (Vite/Next commonly choose a different port
# when one is occupied) while keeping remote browser origins explicitly blocked.
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000").split(","), allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?"), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
# The Vite dashboard remains the currently served app while the exact Next.js
# authentication template is prepared in user-website/frontend-next.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend-vite-backup" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
def db():
    s=SessionLocal()
    try: yield s
    finally: s.close()
def token_for(user: User): return jwt.encode({"sub":str(user.id),"email":user.email,"exp":datetime.now(timezone.utc)+timedelta(hours=12)},JWT_SECRET,algorithm="HS256")
def current_user(authorization: str=Header(...), s:Session=Depends(db)):
    try: user=s.get(User,int(jwt.decode(authorization.removeprefix("Bearer "),JWT_SECRET,algorithms=["HS256"])["sub"]))
    except Exception: raise HTTPException(401,"Invalid or expired session")
    if not user: raise HTTPException(401,"User not found")
    return user
def provider_auth(x_provider_token: str=Header(...)):
    if not secrets.compare_digest(x_provider_token, PROVIDER_TOKEN): raise HTTPException(401,"Provider authentication failed")
def job_data(j): return {"id":j.id,"name":j.name,"workload":j.workload,"requirements":j.requirements,"status":j.status,"progress":j.progress,"provider_id":j.provider_id,"result":j.result,"estimated_cost":j.estimated_cost,"actual_cost":j.actual_cost,"created_at":j.created_at}
def provider_data(p): return {"id":p.id,"name":p.name,"cpu_cores":p.cpu_cores,"ram_gb":p.ram_gb,"gpu_name":p.gpu_name,"gpu_memory_gb":p.gpu_memory_gb,"cost_per_hour":p.cost_per_hour,"status":p.status,"reliability":p.reliability,"utilization":p.utilization,"last_heartbeat":p.last_heartbeat}
def compatible_provider(s, requirements, exclude_id=None):
    candidates=[p for p in s.query(Provider).all() if p.id!=exclude_id and p.status in ("ONLINE","AVAILABLE") and p.cpu_cores>=requirements.get("cpu_cores",1) and p.ram_gb>=requirements.get("ram_gb",1) and (not requirements.get("gpu_required") or p.gpu_name)]
    return min(candidates,key=lambda x:x.cost_per_hour/(max(x.reliability,1)/100)) if candidates else None
def recover_lost_providers():
    """Detect provider loss and re-dispatch checkpointed controlled workloads."""
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
                    checkpoint=s.query(Checkpoint).filter_by(job_id=j.id).order_by(Checkpoint.created_at.desc()).first()
                    replacement=compatible_provider(s,j.requirements,failed.id)
                    if checkpoint and replacement:
                        j.provider_id=replacement.id; j.status="RECOVERING"; j.progress=checkpoint.progress
                        j.requirements={**j.requirements,"resume_from_progress":checkpoint.progress,"recovery_note":f"Recovered from {failed.name}"}; replacement.status="BUSY"
                    else: j.status="FAILED"; j.result={"error":"Provider lost; no compatible recovery provider or checkpoint available."}
            s.commit()
        finally: s.close()

@app.on_event("startup")
def init():
    Base.metadata.create_all(engine)
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
    u=User(email=body.email.lower(),password_hash=hash_password(body.password));s.add(u);s.commit();s.refresh(u);return {"access_token":token_for(u),"user":{"id":u.id,"email":u.email,"wallet_balance":u.wallet_balance}}
@app.post("/auth/login")
def login(body:Login,s:Session=Depends(db)):
    u=s.query(User).filter_by(email=body.email.lower()).first()
    if not u or not verify_password(body.password,u.password_hash): raise HTTPException(401,"Incorrect email or password")
    return {"access_token":token_for(u),"user":{"id":u.id,"email":u.email,"wallet_balance":u.wallet_balance}}
@app.get("/providers")
def providers(_:User=Depends(current_user),s:Session=Depends(db)): return [provider_data(p) for p in s.query(Provider).all()]
@app.post("/providers/register")
def provider_register(body:ProviderRegister,_=Depends(provider_auth),s:Session=Depends(db)):
    p=s.get(Provider,body.id)
    if not p: p=Provider(**body.model_dump());s.add(p)
    else:
        for k,v in body.model_dump().items(): setattr(p,k,v)
        p.status="ONLINE"
    s.commit();return provider_data(p)
@app.post("/providers/{provider_id}/heartbeat")
def heartbeat(provider_id:str,body:Heartbeat,_=Depends(provider_auth),s:Session=Depends(db)):
    p=s.get(Provider,provider_id)
    if not p: raise HTTPException(404,"Provider not registered")
    p.status=body.status;p.utilization=body.utilization;p.last_heartbeat=datetime.now(timezone.utc);s.commit();return {"ok":True}
@app.get("/jobs")
def jobs(u:User=Depends(current_user),s:Session=Depends(db)): return [job_data(j) for j in s.query(Job).filter_by(user_id=u.id).order_by(Job.created_at.desc()).all()]
@app.post("/jobs")
def create_job(body:JobCreate,u:User=Depends(current_user),s:Session=Depends(db)):
    p=compatible_provider(s,body.requirements)
    if not p: raise HTTPException(409,"No compatible online provider is available")
    j=Job(id=f"job_{secrets.token_hex(5)}",name=body.name,workload=body.workload,requirements=body.requirements,user_id=u.id,provider_id=p.id,status="SCHEDULED",estimated_cost=round(p.cost_per_hour*body.requirements.get("expected_runtime_hours",.05),4));p.status="BUSY";s.add(j);s.commit();return job_data(j)
@app.get("/jobs/{job_id}")
def get_job(job_id:str,u:User=Depends(current_user),s:Session=Depends(db)):
    j=s.get(Job,job_id)
    if not j or j.user_id!=u.id: raise HTTPException(404,"Job not found")
    return job_data(j)
@app.post("/jobs/{job_id}/cancel")
def cancel(job_id:str,u:User=Depends(current_user),s:Session=Depends(db)):
    j=s.get(Job,job_id)
    if not j or j.user_id!=u.id: raise HTTPException(404,"Job not found")
    j.status="CANCELLED";s.commit();return job_data(j)
@app.post("/jobs/stop-all")
def stop_all_jobs(u:User=Depends(current_user),s:Session=Depends(db)):
    jobs=s.query(Job).filter(Job.user_id==u.id,Job.status.in_(["QUEUED","SCHEDULED","RUNNING","RECOVERING"])).all()
    for j in jobs: j.status="CANCELLED";j.completed_at=datetime.now(timezone.utc)
    s.commit();return {"cancelled":len(jobs)}
@app.get("/providers/{provider_id}/jobs/pending")
def pending(provider_id:str,_=Depends(provider_auth),s:Session=Depends(db)): return [job_data(j) for j in s.query(Job).filter(Job.provider_id==provider_id,Job.status.in_(["SCHEDULED","RECOVERING"])).all()]
@app.post("/providers/jobs/{job_id}/update")
def update_job(job_id:str,body:Update,_=Depends(provider_auth),s:Session=Depends(db)):
    j=s.get(Job,job_id)
    if not j: raise HTTPException(404,"Job not found")
    if body.status: j.status=body.status.value
    if body.progress is not None:j.progress=body.progress
    if body.result is not None:j.result=body.result
    if body.actual_cost is not None:j.actual_cost=body.actual_cost
    if j.status=="RUNNING" and not j.started_at:j.started_at=datetime.now(timezone.utc)
    if j.status in ("COMPLETED","FAILED","CANCELLED"):
        j.completed_at=datetime.now(timezone.utc);p=s.get(Provider,j.provider_id);p.status="ONLINE"
    s.commit();return job_data(j)
@app.post("/providers/jobs/{job_id}/checkpoint")
def checkpoint(job_id:str,body:dict,_=Depends(provider_auth),s:Session=Depends(db)):
    j=s.get(Job,job_id)
    if not j: raise HTTPException(404,"Job not found")
    c=Checkpoint(id=f"cp_{secrets.token_hex(5)}",job_id=job_id,provider_id=j.provider_id,progress=int(body.get("progress",0)),payload=body);s.add(c);s.commit();return {"id":c.id,"progress":c.progress}
@app.get("/checkpoints")
def checkpoints(u:User=Depends(current_user),s:Session=Depends(db)):
    rows=s.query(Checkpoint,Job).join(Job, Checkpoint.job_id==Job.id).filter(Job.user_id==u.id).order_by(Checkpoint.created_at.desc()).all()
    return [{"id":c.id,"job_id":j.id,"job_name":j.name,"provider_id":c.provider_id,"progress":c.progress,"payload":c.payload,"created_at":c.created_at} for c,j in rows]
@app.get("/dashboard")
def dashboard(u:User=Depends(current_user),s:Session=Depends(db)):
    js=s.query(Job).filter_by(user_id=u.id).all();ps=s.query(Provider).all();n=max(len(ps),1)
    return {"active_jobs":sum(j.status in ("SCHEDULED","RUNNING","RECOVERING") for j in js),"available_nodes":sum(p.status in ("ONLINE","AVAILABLE") for p in ps),"monthly_spending":round(sum(j.actual_cost for j in js),4),"gpu_utilization":round(sum(p.utilization.get("gpu",0) for p in ps)/n,1),"cpu_utilization":round(sum(p.utilization.get("cpu",0) for p in ps)/n,1),"ram_utilization":round(sum(p.utilization.get("ram",0) for p in ps)/n,1),"recent_jobs":[job_data(j) for j in sorted(js,key=lambda x:x.created_at,reverse=True)[:5]]}
@app.get("/analytics")
def analytics(u:User=Depends(current_user),s:Session=Depends(db)):
    js=s.query(Job).filter_by(user_id=u.id).all(); return {"job_success_rate":round(100*sum(j.status=="COMPLETED" for j in js)/max(sum(j.status in ("COMPLETED","FAILED") for j in js),1),1),"total_jobs":len(js),"recovery_count":sum(j.status=="RECOVERING" for j in js)}
@app.get("/billing")
def billing(u:User=Depends(current_user),s:Session=Depends(db)):
    js=s.query(Job).filter_by(user_id=u.id).all()
    return {"wallet_balance":u.wallet_balance,"total_spend":round(sum(j.actual_cost for j in js),4),"estimated_pending_cost":round(sum(j.estimated_cost for j in js if j.status in ("SCHEDULED","RUNNING","RECOVERING")),4),"jobs":[{"job_id":j.id,"name":j.name,"cost":j.actual_cost,"estimated_cost":j.estimated_cost,"status":j.status} for j in js]}
@app.post("/billing/demo-topup")
def demo_topup(body:DemoTopUp,u:User=Depends(current_user),s:Session=Depends(db)):
    # College-project demo only: card data is validated for form completeness and never stored or transmitted.
    digits="".join(ch for ch in body.card_number if ch.isdigit())
    if len(digits) < 12: raise HTTPException(422,"Enter a valid test card number")
    u.wallet_balance=round(u.wallet_balance+body.amount,2);s.commit()
    return {"wallet_balance":u.wallet_balance,"credited":body.amount,"card_last4":digits[-4:],"mode":"demo"}
