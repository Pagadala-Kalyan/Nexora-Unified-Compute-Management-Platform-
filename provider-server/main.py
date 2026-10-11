"""Nexora provider agent: runs team-submitted Python workloads on this device."""

import os
import platform
import time
import threading
import subprocess
import sys
import tempfile
import importlib.util
import uuid

from datetime import datetime

import psutil
import requests


# ============================================================
# BACKEND CONFIGURATION
# ============================================================

BASE = os.getenv(
    "UCMP_BACKEND_URL",
    "http://127.0.0.1:8000"
).rstrip("/")

TOKEN = os.getenv(
    "PROVIDER_SHARED_TOKEN",
    "local-demo-token"
)


# ============================================================
# PERSISTENT PROVIDER ID
# ============================================================

PROVIDER_ID_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".provider_id"
)


def get_provider_id():

    # Optional manual override
    configured_id = os.getenv("PROVIDER_ID")

    if configured_id:
        return configured_id.strip()

    # Reuse existing ID
    if os.path.exists(PROVIDER_ID_FILE):

        try:
            with open(
                PROVIDER_ID_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                saved_id = file.read().strip()

            if saved_id:
                return saved_id

        except OSError:
            pass

    # Generate a unique ID for this machine
    provider_id = (
        f"provider-{uuid.uuid4().hex[:12]}"
    )

    try:

        with open(
            PROVIDER_ID_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(provider_id)

    except OSError as e:

        print(
            f"Warning: Could not save provider ID: {e}"
        )

    return provider_id


PID = get_provider_id()

NAME = os.getenv(
    "PROVIDER_NAME",
    platform.node() or "Nexora Provider"
)

INTERVAL = int(
    os.getenv("HEARTBEAT_INTERVAL", "5")
)

HEAD = {
    "X-Provider-Token": TOKEN
}

active_jobs = 0


# ============================================================
# SYSTEM INFORMATION
# ============================================================

def get_system_info():

    # -------------------------
    # CPU
    # -------------------------

    cpu_name = platform.processor()

    if not cpu_name:
        cpu_name = platform.uname().processor

    physical_cpu_cores = (
        psutil.cpu_count(logical=False) or 1
    )

    logical_cpu_cores = (
        psutil.cpu_count(logical=True) or 1
    )

    cpu_frequency = psutil.cpu_freq()

    cpu_frequency_ghz = None

    if cpu_frequency:
        cpu_frequency_ghz = round(
            cpu_frequency.max / 1000,
            2
        )

    # -------------------------
    # RAM
    # -------------------------

    memory = psutil.virtual_memory()

    total_ram_gb = round(
        memory.total / (1024 ** 3),
        2
    )

    available_ram_gb = round(
        memory.available / (1024 ** 3),
        2
    )

    # -------------------------
    # GPU
    # -------------------------

    gpu_name = None
    gpu_memory_gb = 0
    cuda_available = False
    gpu_count = 0

    try:

        if importlib.util.find_spec("torch"):

            import torch

            cuda_available = torch.cuda.is_available()

            if cuda_available:

                gpu_count = torch.cuda.device_count()

                gpu_names = []

                total_gpu_memory = 0

                for index in range(gpu_count):

                    name = torch.cuda.get_device_name(index)

                    gpu_names.append(name)

                    properties = (
                        torch.cuda.get_device_properties(index)
                    )

                    total_gpu_memory += (
                        properties.total_memory
                        / (1024 ** 3)
                    )

                gpu_name = ", ".join(gpu_names)

                gpu_memory_gb = round(
                    total_gpu_memory,
                    2
                )

    except Exception as e:

        print(
            f"GPU detection warning: {e}"
        )

    # -------------------------
    # Disk
    # -------------------------

    try:

        disk = psutil.disk_usage(
            os.path.abspath(os.sep)
        )

        disk_total_gb = round(
            disk.total / (1024 ** 3),
            2
        )

        disk_free_gb = round(
            disk.free / (1024 ** 3),
            2
        )

    except Exception:

        disk_total_gb = 0
        disk_free_gb = 0

    # -------------------------
    # Platform
    # -------------------------

    return {

        "os": platform.system(),

        "os_version": platform.version(),

        "architecture": platform.machine(),

        "hostname": platform.node(),

        "cpu_name": cpu_name,

        "cpu_physical_cores":
            physical_cpu_cores,

        "cpu_logical_cores":
            logical_cpu_cores,

        "cpu_max_frequency_ghz":
            cpu_frequency_ghz,

        "ram_total_gb":
            total_ram_gb,

        "ram_available_gb":
            available_ram_gb,

        "gpu_name":
            gpu_name,

        "gpu_count":
            gpu_count,

        "gpu_memory_gb":
            gpu_memory_gb,

        "cuda_available":
            cuda_available,

        "disk_total_gb":
            disk_total_gb,

        "disk_free_gb":
            disk_free_gb
    }


SYSTEM_INFO = get_system_info()


# ============================================================
# HTTP REQUEST
# ============================================================

def request(method, path, **kwargs):

    return requests.request(
        method,
        BASE + path,
        headers=HEAD,
        timeout=10,
        **kwargs
    )


# ============================================================
# RESOURCE UTILIZATION
# ============================================================

def utilization():

    cpu_percent = psutil.cpu_percent(
        interval=None
    )

    ram_percent = (
        psutil.virtual_memory().percent
    )

    disk_percent = (
        psutil.disk_usage(
            os.path.abspath(os.sep)
        ).percent
    )

    gpu_percent = 0

    try:

        if (
            SYSTEM_INFO["cuda_available"]
            and importlib.util.find_spec("torch")
        ):

            import torch

            gpu_values = []

            for index in range(
                torch.cuda.device_count()
            ):

                allocated = (
                    torch.cuda.memory_allocated(index)
                )

                reserved = (
                    torch.cuda.memory_reserved(index)
                )

                total = (
                    torch.cuda.get_device_properties(index)
                    .total_memory
                )

                used = max(
                    allocated,
                    reserved
                )

                if total > 0:

                    gpu_values.append(
                        used / total * 100
                    )

            if gpu_values:

                gpu_percent = round(
                    sum(gpu_values)
                    / len(gpu_values),
                    1
                )

    except Exception:
        gpu_percent = 0

    return {

        "cpu": cpu_percent,

        "ram": ram_percent,

        "gpu": gpu_percent,

        "disk": disk_percent
    }


# ============================================================
# PROVIDER REGISTRATION
# ============================================================

def register():

    # Backend currently requires these fields.
    # Additional hardware information is included
    # separately in provider metadata if your backend
    # is extended to store it.

    data = {

        "id": PID,

        "name": NAME,

        "cpu_cores":
            SYSTEM_INFO["cpu_logical_cores"],

        "ram_gb":
            SYSTEM_INFO["ram_total_gb"],

        "gpu_name":
            SYSTEM_INFO["gpu_name"],

        "gpu_memory_gb":
            SYSTEM_INFO["gpu_memory_gb"],

        "cost_per_hour":
            float(
                os.getenv(
                    "COST_PER_HOUR",
                    "0.15"
                )
            )
    }

    print()
    print("Detected provider hardware")
    print("--------------------------------")
    print(
        f"CPU       : "
        f"{SYSTEM_INFO['cpu_name']}"
    )
    print(
        f"CPU cores : "
        f"{SYSTEM_INFO['cpu_logical_cores']}"
    )
    print(
        f"RAM       : "
        f"{SYSTEM_INFO['ram_total_gb']} GB"
    )
    print(
        f"GPU       : "
        f"{SYSTEM_INFO['gpu_name'] or 'None'}"
    )
    print(
        f"GPU memory: "
        f"{SYSTEM_INFO['gpu_memory_gb']} GB"
    )
    print(
        f"CUDA      : "
        f"{SYSTEM_INFO['cuda_available']}"
    )
    print(
        f"OS        : "
        f"{SYSTEM_INFO['os']}"
    )
    print("--------------------------------")
    print()

    response = request(
        "POST",
        "/providers/register",
        json=data
    )

    response.raise_for_status()

    print(
        f"Connected as {NAME} ({PID})"
    )


# ============================================================
# HEARTBEAT
# ============================================================

def heartbeat():

    while True:

        try:

            request(
                "POST",
                f"/providers/{PID}/heartbeat",
                json={
                    "status":
                        "BUSY"
                        if active_jobs
                        else "ONLINE",

                    "utilization":
                        utilization()
                }
            ).raise_for_status()

        except requests.RequestException as e:

            print(
                f"heartbeat failed: {e}"
            )

        time.sleep(INTERVAL)


# ============================================================
# CHECKPOINT
# ============================================================

def checkpoint(
    job_id,
    progress,
    started_at,
    workload
):

    request(
        "POST",
        f"/providers/jobs/{job_id}/update",
        json={
            "progress": progress
        }
    )

    request(
        "POST",
        f"/providers/jobs/{job_id}/checkpoint",
        json={
            "progress": progress,

            "state": {

                "iteration": progress,

                "workload": workload,

                "provider": PID,

                "elapsed_seconds":
                    round(
                        time.perf_counter()
                        - started_at,
                        4
                    ),

                "recorded_at":
                    datetime.now()
                    .astimezone()
                    .isoformat()
            }
        }
    )


# ============================================================
# MATRIX MULTIPLICATION
# ============================================================

def run_matrix_multiply(size, report):

    if not importlib.util.find_spec("torch"):

        raise RuntimeError(
            "Matrix computation requires PyTorch."
        )

    import torch

    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    left = (
        torch.arange(
            size * size,
            dtype=torch.float32,
            device=device
        )
        .reshape(size, size)
        .remainder(101)
    )

    right = (
        torch.arange(
            size * size,
            dtype=torch.float32,
            device=device
        )
        .reshape(size, size)
        .remainder(89)
    )

    checksum = 0.0

    for part in range(4):

        row_start = (
            part * size
        ) // 4

        row_end = (
            (part + 1) * size
        ) // 4

        product = torch.matmul(
            left[row_start:row_end],
            right
        )

        if device.type == "cuda":
            torch.cuda.synchronize()

        checksum += float(
            product.sum().item()
        )

        report(
            (part + 1) * 25
        )

    return {

        "operation":
            "matrix multiplication",

        "matrix_shape":
            [size, size],

        "device":
            str(device),

        "checksum":
            round(checksum, 3)
    }


# ============================================================
# PRIME SEARCH
# ============================================================

def is_prime(number):

    if number < 2:
        return False

    if number == 2:
        return True

    if number % 2 == 0:
        return False

    divisor = 3

    while divisor * divisor <= number:

        if number % divisor == 0:
            return False

        divisor += 2

    return True


def run_prime_search(limit, report):

    primes = []

    for part in range(4):

        start = max(
            2,
            (part * limit) // 4 + 1
        )

        end = (
            (part + 1) * limit
        ) // 4

        primes.extend(
            number
            for number in range(
                start,
                end + 1
            )
            if is_prime(number)
        )

        report(
            (part + 1) * 25
        )

    return {

        "operation":
            "prime number search",

        "upper_limit":
            limit,

        "prime_count":
            len(primes),

        "last_prime":
            primes[-1]
            if primes
            else None,

        "primes":
            primes
    }


# ============================================================
# FIBONACCI
# ============================================================

def run_fibonacci(index, report):

    previous = 0
    current = 1
    completed = 0

    for part in range(4):

        target = (
            (part + 1) * index
        ) // 4

        while completed < target:

            previous, current = (
                current,
                previous + current
            )

            completed += 1

        report(
            (part + 1) * 25
        )

    return {

        "operation":
            "fibonacci calculation",

        "index":
            index,

        "value":
            previous,

        "digits":
            len(str(previous))
    }


# ============================================================
# JOB EXECUTION
# ============================================================

def execute(job):

    global active_jobs

    jid = job["id"]

    active_jobs += 1

    print(
        f"\n[JOB RECEIVED] {jid} | "
        f"type: {job['workload']} | "
        f"submitted by: "
        f"{job.get('submitted_by', 'unknown user')}"
    )

    started_at = time.perf_counter()

    request(
        "POST",
        f"/providers/jobs/{jid}/update",
        json={
            "status": "RUNNING",
            "progress": 0
        }
    )

    try:

        workload = job["workload"]

        size = min(
            max(
                int(
                    job["requirements"].get(
                        "matrix_size",
                        300
                    )
                ),
                10
            ),
            1200
        )

        report = lambda progress: checkpoint(
            jid,
            progress,
            started_at,
            workload
        )

        if workload == "matrix_multiply":

            total = run_matrix_multiply(
                size,
                report
            )

        elif workload == "prime_search":

            total = run_prime_search(
                size,
                report
            )

        elif workload == "fibonacci":

            total = run_fibonacci(
                size,
                report
            )

        elif workload == "custom_python":

            code = job["requirements"].get(
                "python_code",
                ""
            )

            if not code.strip():

                raise ValueError(
                    "No Python code was supplied"
                )

            filename = job["requirements"].get(
                "file_name",
                "nexora_workload.py"
            )

            with tempfile.TemporaryDirectory(
                prefix="nexora-job-"
            ) as workdir:

                source = os.path.join(
                    workdir,
                    os.path.basename(filename)
                )

                with open(
                    source,
                    "w",
                    encoding="utf-8"
                ) as submitted:

                    submitted.write(code)

                process = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        source
                    ],
                    capture_output=True,
                    text=True,
                    timeout=int(
                        job["requirements"].get(
                            "timeout_seconds",
                            20
                        )
                    ),
                    cwd=workdir
                )

            if process.returncode:

                raise RuntimeError(
                    process.stderr[-1500:]
                    or "Python workload failed"
                )

            total = process.stdout[-4000:]

            report(100)

        else:

            raise ValueError(
                f"Unsupported workload type: {workload}"
            )

        message = {

            "matrix_multiply":
                "Matrix computation completed",

            "prime_search":
                "Prime search completed",

            "fibonacci":
                "Fibonacci computation completed",

            "custom_python":
                "Uploaded Python code completed"

        }.get(
            workload,
            "Workload completed"
        )

        elapsed = round(
            time.perf_counter()
            - started_at,
            4
        )

        request(
            "POST",
            f"/providers/jobs/{jid}/update",
            json={

                "status":
                    "COMPLETED",

                "progress":
                    100,

                "actual_cost":
                    round(
                        .15 / 3600 * elapsed,
                        5
                    ),

                "result": {

                    "message":
                        message,

                    "workload":
                        workload,

                    "input_size":
                        size,

                    "output":
                        total,

                    "provider":
                        PID,

                    "elapsed_seconds":
                        elapsed
                }
            }
        )

        print(
            f"[JOB COMPLETED] {jid} | "
            f"output:\n{total}\n"
        )

    except Exception as e:

        print(
            f"[JOB FAILED] {jid} | "
            f"error: {e}\n"
        )

        try:

            request(
                "POST",
                f"/providers/jobs/{jid}/update",
                json={
                    "status": "FAILED",
                    "result": {
                        "error": str(e)
                    }
                }
            )

        except requests.RequestException as update_error:

            print(
                f"Could not report job failure: "
                f"{update_error}"
            )

    finally:

        active_jobs = max(
            0,
            active_jobs - 1
        )


# ============================================================
# LISTENER
# ============================================================

def listener():

    while True:

        try:

            response = request(
                "GET",
                f"/providers/{PID}/jobs/pending"
            )

            response.raise_for_status()

            jobs = response.json()

            for job in jobs:

                threading.Thread(
                    target=execute,
                    args=(job,),
                    daemon=True
                ).start()

        except requests.RequestException as e:

            print(
                f"poll failed: {e}"
            )

        time.sleep(2)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print()
    print(
        "=============================================="
    )
    print(
        "       NEXORA PROVIDER SERVER"
    )
    print(
        "=============================================="
    )

    print(
        f"Provider Name : {NAME}"
    )

    print(
        f"Provider ID   : {PID}"
    )

    print(
        f"Backend       : {BASE}"
    )

    print()

    print(
        "Detected Hardware"
    )

    print(
        "----------------------------------------------"
    )

    print(
        f"CPU           : "
        f"{SYSTEM_INFO['cpu_name']}"
    )

    print(
        f"Physical Cores: "
        f"{SYSTEM_INFO['cpu_physical_cores']}"
    )

    print(
        f"Logical Cores : "
        f"{SYSTEM_INFO['cpu_logical_cores']}"
    )

    print(
        f"CPU Max Clock : "
        f"{SYSTEM_INFO['cpu_max_frequency_ghz']} GHz"
    )

    print(
        f"RAM           : "
        f"{SYSTEM_INFO['ram_total_gb']} GB"
    )

    print(
        f"GPU           : "
        f"{SYSTEM_INFO['gpu_name'] or 'None'}"
    )

    print(
        f"GPU Count     : "
        f"{SYSTEM_INFO['gpu_count']}"
    )

    print(
        f"GPU Memory    : "
        f"{SYSTEM_INFO['gpu_memory_gb']} GB"
    )

    print(
        f"CUDA Available: "
        f"{SYSTEM_INFO['cuda_available']}"
    )

    print(
        f"Operating Sys.: "
        f"{SYSTEM_INFO['os']}"
    )

    print(
        f"Architecture  : "
        f"{SYSTEM_INFO['architecture']}"
    )

    print(
        "----------------------------------------------"
    )

    print(
        f"Provider Python: {sys.executable}"
    )

    if importlib.util.find_spec("torch"):

        import torch

        print(
            f"PyTorch       : "
            f"{torch.__version__}"
        )

        print(
            f"CUDA          : "
            f"{torch.cuda.is_available()}"
        )

    else:

        print(
            "PyTorch       : Not installed"
        )

    print()

    register()

    threading.Thread(
        target=heartbeat,
        daemon=True
    ).start()

    listener()