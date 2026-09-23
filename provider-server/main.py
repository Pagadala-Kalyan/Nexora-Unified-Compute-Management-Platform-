"""Nexora provider agent: runs team-submitted Python workloads on this device."""
import os, platform, time, threading, subprocess, sys, tempfile, importlib.util
from datetime import datetime
import psutil, requests

BASE=os.getenv("UCMP_BACKEND_URL","http://127.0.0.1:8000").rstrip("/")
TOKEN=os.getenv("PROVIDER_SHARED_TOKEN","local-demo-token")
PID=os.getenv("PROVIDER_ID","laptop-001"); NAME=os.getenv("PROVIDER_NAME",platform.node() or "Nexora Provider")
INTERVAL=int(os.getenv("HEARTBEAT_INTERVAL","5")); HEAD={"X-Provider-Token":TOKEN}
active_jobs=0
def request(method,path,**kwargs): return requests.request(method,BASE+path,headers=HEAD,timeout=10,**kwargs)
def utilization(): return {"cpu":psutil.cpu_percent(),"ram":psutil.virtual_memory().percent,"gpu":0,"disk":psutil.disk_usage('/').percent}
def register():
    data={"id":PID,"name":NAME,"cpu_cores":psutil.cpu_count(logical=True) or 1,"ram_gb":round(psutil.virtual_memory().total/1024**3,1),"gpu_name":None,"gpu_memory_gb":0,"cost_per_hour":float(os.getenv("COST_PER_HOUR","0.15"))}
    request("POST","/providers/register",json=data).raise_for_status(); print(f"Connected as {NAME} ({PID})")
def heartbeat():
    while True:
        try: request("POST",f"/providers/{PID}/heartbeat",json={"status":"BUSY" if active_jobs else "ONLINE","utilization":utilization()}).raise_for_status()
        except requests.RequestException as e: print(f"heartbeat failed: {e}")
        time.sleep(INTERVAL)

def checkpoint(job_id, progress, started_at, workload):
    """Persist a checkpoint only after the corresponding computation finished."""
    request("POST",f"/providers/jobs/{job_id}/update",json={"progress":progress})
    request("POST",f"/providers/jobs/{job_id}/checkpoint",json={"progress":progress,"state":{
        "iteration":progress,"workload":workload,"provider":PID,
        "elapsed_seconds":round(time.perf_counter()-started_at,4),
        "recorded_at":datetime.now().astimezone().isoformat()
    }})

def run_matrix_multiply(size, report):
    """Multiply two real size × size matrices, one quarter of the rows at a time."""
    if not importlib.util.find_spec("torch"):
        raise RuntimeError("Matrix computation requires PyTorch on this provider. Run the provider with its PyTorch virtual environment.")
    import torch
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # Deterministic values make the reported checksum reproducible for a given size.
    left=torch.arange(size*size,dtype=torch.float32,device=device).reshape(size,size).remainder(101)
    right=torch.arange(size*size,dtype=torch.float32,device=device).reshape(size,size).remainder(89)
    checksum=0.0
    for part in range(4):
        row_start=(part*size)//4; row_end=((part+1)*size)//4
        product=torch.matmul(left[row_start:row_end],right)
        if device.type=="cuda": torch.cuda.synchronize()
        checksum+=float(product.sum().item())
        report((part+1)*25)
    return {"operation":"matrix multiplication","matrix_shape":[size,size],"device":str(device),"checksum":round(checksum,3)}

def is_prime(number):
    if number<2: return False
    if number==2: return True
    if number%2==0: return False
    divisor=3
    while divisor*divisor<=number:
        if number%divisor==0: return False
        divisor+=2
    return True

def run_prime_search(limit, report):
    """Find every actual prime from 2 through the requested upper limit."""
    primes=[]
    for part in range(4):
        start=max(2,(part*limit)//4+1); end=((part+1)*limit)//4
        primes.extend(number for number in range(start,end+1) if is_prime(number))
        report((part+1)*25)
    return {"operation":"prime number search","upper_limit":limit,"prime_count":len(primes),"last_prime":primes[-1] if primes else None,"primes":primes}

def run_fibonacci(index, report):
    """Calculate the genuine Fibonacci number at the requested zero-based index."""
    previous,current=0,1
    completed=0
    for part in range(4):
        target=((part+1)*index)//4
        while completed<target:
            previous,current=current,previous+current
            completed+=1
        report((part+1)*25)
    return {"operation":"fibonacci calculation","index":index,"value":previous,"digits":len(str(previous))}

def execute(job):
    global active_jobs
    jid=job["id"]; active_jobs+=1
    print(f"\n[JOB RECEIVED] {jid} | type: {job['workload']} | submitted by: {job.get('submitted_by','unknown user')}")
    started_at=time.perf_counter(); request("POST",f"/providers/jobs/{jid}/update",json={"status":"RUNNING","progress":0})
    try:
        workload=job["workload"]
        size=min(max(int(job["requirements"].get("matrix_size",300)),10),1200)
        report=lambda progress: checkpoint(jid,progress,started_at,workload)
        if workload == "matrix_multiply": total=run_matrix_multiply(size,report)
        elif workload == "prime_search": total=run_prime_search(size,report)
        elif workload == "fibonacci": total=run_fibonacci(size,report)
        elif workload == "custom_python":
            code=job["requirements"].get("python_code","")
            if not code.strip(): raise ValueError("No Python code was supplied")
            filename=job["requirements"].get("file_name","nexora_workload.py")
            with tempfile.TemporaryDirectory(prefix="nexora-job-") as workdir:
                source=os.path.join(workdir, os.path.basename(filename))
                with open(source,"w",encoding="utf-8") as submitted: submitted.write(code)
                process=subprocess.run([sys.executable,"-I",source],capture_output=True,text=True,timeout=int(job["requirements"].get("timeout_seconds",20)),cwd=workdir)
            if process.returncode: raise RuntimeError(process.stderr[-1500:] or "Python workload failed")
            total=process.stdout[-4000:]
            report(100)
        else: raise ValueError(f"Unsupported workload type: {workload}")
        message={"matrix_multiply":"Matrix computation completed","prime_search":"Prime search completed","fibonacci":"Fibonacci computation completed","custom_python":"Uploaded Python code completed"}.get(workload,"Workload completed")
        elapsed=round(time.perf_counter()-started_at,4)
        request("POST",f"/providers/jobs/{jid}/update",json={"status":"COMPLETED","progress":100,"actual_cost":round(.15/3600*elapsed,5),"result":{"message":message,"workload":workload,"input_size":size,"output":total,"provider":PID,"elapsed_seconds":elapsed}})
        print(f"[JOB COMPLETED] {jid} | output:\n{total}\n")
    except Exception as e:
        print(f"[JOB FAILED] {jid} | error: {e}\n")
        request("POST",f"/providers/jobs/{jid}/update",json={"status":"FAILED","result":{"error":str(e)}})
    finally:
        active_jobs=max(0,active_jobs-1)
def listener():
    while True:
        try:
            for job in request("GET",f"/providers/{PID}/jobs/pending").json(): threading.Thread(target=execute,args=(job,),daemon=True).start()
        except requests.RequestException as e: print(f"poll failed: {e}")
        time.sleep(2)
if __name__=="__main__":
    print("Nexora Provider Server — executing workloads on this provider device")
    print(f"Provider Python: {sys.executable}")
    if importlib.util.find_spec("torch"):
        import torch
        print(f"PyTorch: {torch.__version__} | CUDA available: {torch.cuda.is_available()}")
    else: print("PyTorch: not installed for this provider interpreter")
    register(); threading.Thread(target=heartbeat,daemon=True).start(); listener()
