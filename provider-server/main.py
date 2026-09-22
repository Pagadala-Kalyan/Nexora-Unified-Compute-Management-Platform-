"""Nexora provider agent: runs team-submitted Python workloads on this device."""
import os, platform, time, threading, subprocess, sys, tempfile, importlib.util
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
def execute(job):
    global active_jobs
    jid=job["id"]; active_jobs+=1
    print(f"\n[JOB RECEIVED] {jid} | type: {job['workload']} | submitted by: {job.get('submitted_by','unknown user')}")
    started_at=time.perf_counter(); request("POST",f"/providers/jobs/{jid}/update",json={"status":"RUNNING","progress":0})
    try:
        workload=job["workload"]
        size=min(max(int(job["requirements"].get("matrix_size",300)),10),1200)
        total=0; a,b=0,1
        resume_at=int(job["requirements"].get("resume_from_progress",0))
        checkpoint_start=((resume_at // 25) + 1) * 25
        steps=range(checkpoint_start,101,25) if workload != "custom_python" else (100,)
        for progress in steps:
            # Each checkpoint follows work actually completed on this device.
            start=max(0,((progress-25)*size*20)//100); end=(progress*size*20)//100
            if workload == "matrix_multiply": total+=sum((i*i)%97 for i in range(start,end))
            elif workload == "prime_search": total+=sum(1 for n in range(max(2,start),max(2,end)) if all(n%d for d in range(2,int(n**.5)+1)))
            elif workload == "fibonacci":
                start=max(0,((progress-25)*size*100)//100); end=(progress*size*100)//100
                for _ in range(start,end): a,b=b,a+b
                total=len(str(a))
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
            request("POST",f"/providers/jobs/{jid}/update",json={"progress":progress})
            if progress in (25,50,75,100): request("POST",f"/providers/jobs/{jid}/checkpoint",json={"progress":progress,"state":{"iteration":progress,"workload":job["workload"],"provider":PID,"elapsed_seconds":round(time.perf_counter()-started_at,4)}})
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
