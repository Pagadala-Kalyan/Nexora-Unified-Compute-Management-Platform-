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

import json
import hashlib
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
# FENCING & CHECKPOINT PROTOCOL
# ============================================================

class FencingError(Exception):
    """Raised when the control plane rejects an update because a newer provider attempt took over."""
    pass


def canonical_hash(data: dict) -> str:
    """Computes a deterministic SHA-256 integrity hash for a checkpoint state dictionary."""
    if not data:
        return ""
    serialized = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def fetch_valid_checkpoint(job_id):
    """
    Fetches the latest valid checkpoint for recovery, verifying integrity hashes
    and falling back to earlier valid checkpoints if the newest is corrupt.
    """
    try:
        res = request("GET", f"/providers/jobs/{job_id}/checkpoints")
        if res.status_code != 200:
            return None
        cps = res.json()
        if not cps or not isinstance(cps, list):
            return None

        # Sort descending by seq, then attempt
        cps.sort(key=lambda x: (x.get("seq", 0), x.get("attempt", 0)), reverse=True)

        for cp in cps:
            payload = cp.get("payload") or {}
            expected_hash = cp.get("state_hash") or ""
            if expected_hash:
                actual_hash = canonical_hash(payload)
                if actual_hash != expected_hash:
                    print(
                        f"[RECOVERY WARNING] Checkpoint {cp.get('id')} seq {cp.get('seq')} "
                        f"corrupted (hash mismatch: expected {expected_hash[:10]}..., got {actual_hash[:10]}...). "
                        f"Falling back to earlier checkpoint..."
                    )
                    continue
            return cp

        print(f"[RECOVERY WARNING] No valid checkpoints found among {len(cps)} candidates.")
        return None
    except Exception as e:
        print(f"[RECOVERY ERROR] Failed to fetch checkpoints for {job_id}: {e}")
        return None


def checkpoint(
    job_id,
    progress,
    started_at,
    workload,
    state_payload,
    attempt=1,
    seq=1
):
    computed_hash = canonical_hash(state_payload)

    # 1. Update job progress with fencing check
    u_res = request(
        "POST",
        f"/providers/jobs/{job_id}/update",
        json={
            "progress": progress,
            "attempt": attempt
        }
    )
    if u_res.status_code == 409:
        raise FencingError(
            f"Stale provider execution fenced out for job {job_id} (attempt {attempt})"
        )

    # 2. Persist genuine state checkpoint with sequence and integrity hash
    c_res = request(
        "POST",
        f"/providers/jobs/{job_id}/checkpoint",
        json={
            "progress": progress,
            "attempt": attempt,
            "seq": seq,
            "state_version": 1,
            "state_hash": computed_hash,
            "state": state_payload
        }
    )
    if c_res.status_code == 409:
        raise FencingError(
            f"Stale provider checkpoint fenced out for job {job_id} (attempt {attempt})"
        )

    return c_res


# ============================================================
# MATRIX MULTIPLICATION (Cooperative Tiling)
# ============================================================

def run_matrix_multiply(size, report, resume_state=None):
    has_torch = importlib.util.find_spec("torch") is not None
    checksum = 0.0
    tile_checksums = []
    start_part = 0

    if resume_state:
        saved_size = resume_state.get("matrix_size")
        if saved_size == size:
            start_part = int(resume_state.get("completed_tiles", 0))
            checksum = float(resume_state.get("accumulated_checksum", 0.0))
            tile_checksums = list(resume_state.get("tile_checksums", []))
            print(
                f"[MATRIX MULTIPLY] Resuming from tile {start_part}/4 with checksum {checksum:.3f}."
            )
        else:
            print(
                f"[MATRIX MULTIPLY WARNING] Matrix size mismatch ({saved_size} != {size}). Starting fresh."
            )

    if has_torch:
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

        for part in range(start_part, 4):
            row_start = (part * size) // 4
            row_end = ((part + 1) * size) // 4

            product = torch.matmul(
                left[row_start:row_end],
                right
            )

            if device.type == "cuda":
                torch.cuda.synchronize()

            part_sum = float(product.sum().item())
            checksum += part_sum
            tile_checksums.append(round(part_sum, 3))

            completed_tiles = part + 1
            state_payload = {
                "workload": "matrix_multiply",
                "matrix_size": size,
                "completed_tiles": completed_tiles,
                "next_tile": completed_tiles,
                "tile_checksums": list(tile_checksums),
                "accumulated_checksum": round(checksum, 3)
            }

            report((part + 1) * 25, state_payload)

        device_name = str(device)
    else:
        # Fallback to NumPy for non-PyTorch test environments
        import numpy as np

        left = (
            np.arange(
                size * size,
                dtype=np.float32
            )
            .reshape(size, size)
            % 101
        )

        right = (
            np.arange(
                size * size,
                dtype=np.float32
            )
            .reshape(size, size)
            % 89
        )

        for part in range(start_part, 4):
            row_start = (part * size) // 4
            row_end = ((part + 1) * size) // 4

            product = np.matmul(
                left[row_start:row_end],
                right
            )

            part_sum = float(product.sum())
            checksum += part_sum
            tile_checksums.append(round(part_sum, 3))

            completed_tiles = part + 1
            state_payload = {
                "workload": "matrix_multiply",
                "matrix_size": size,
                "completed_tiles": completed_tiles,
                "next_tile": completed_tiles,
                "tile_checksums": list(tile_checksums),
                "accumulated_checksum": round(checksum, 3)
            }

            report((part + 1) * 25, state_payload)

        device_name = "numpy-cpu"

    return {
        "operation": "matrix multiplication",
        "matrix_shape": [size, size],
        "device": device_name,
        "checksum": round(checksum, 3)
    }


# ============================================================
# PRIME SEARCH (Partitioned Intervals)
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


def run_prime_search(limit, report, resume_state=None):
    primes = []
    start_part = 0

    if resume_state:
        saved_limit = resume_state.get("limit")
        if saved_limit == limit:
            primes = list(resume_state.get("accumulated_primes", []))
            start_part = int(resume_state.get("completed_slices", 0))
            print(
                f"[PRIME SEARCH] Resuming from slice {start_part}/4 with {len(primes)} primes loaded."
            )
        else:
            print(
                f"[PRIME SEARCH WARNING] Limit mismatch ({saved_limit} != {limit}). Starting fresh."
            )

    for part in range(start_part, 4):
        start = max(
            2,
            (part * limit) // 4 + 1
        )
        end = (
            (part + 1) * limit
        ) // 4

        for number in range(start, end + 1):
            if is_prime(number):
                primes.append(number)

        completed_slices = part + 1
        state_payload = {
            "workload": "prime_search",
            "limit": limit,
            "completed_slices": completed_slices,
            "next_slice": completed_slices,
            "accumulated_primes": list(primes),
            "last_prime": primes[-1] if primes else None
        }

        report((part + 1) * 25, state_payload)

    return {
        "operation": "prime number search",
        "upper_limit": limit,
        "prime_count": len(primes),
        "last_prime": primes[-1] if primes else None,
        "primes": primes
    }


# ============================================================
# FIBONACCI (Exact State Serialization)
# ============================================================

def run_fibonacci(index, report, resume_state=None):
    previous = 0
    current = 1
    completed = 0
    start_part = 0

    if resume_state:
        saved_index = resume_state.get("index")
        if saved_index == index:
            previous = int(resume_state.get("prev_str", "0"))
            current = int(resume_state.get("curr_str", "1"))
            completed = int(resume_state.get("completed_index", 0))
            start_part = int(resume_state.get("completed_slices", 0))
            print(
                f"[FIBONACCI] Resuming from index {completed}/{index} (part {start_part}/4)."
            )
        else:
            print(
                f"[FIBONACCI WARNING] Index mismatch ({saved_index} != {index}). Starting fresh."
            )

    for part in range(start_part, 4):
        target = (
            (part + 1) * index
        ) // 4

        while completed < target:
            previous, current = (
                current,
                previous + current
            )
            completed += 1

        completed_slices = part + 1
        state_payload = {
            "workload": "fibonacci",
            "index": index,
            "completed_index": completed,
            "completed_slices": completed_slices,
            "prev_str": str(previous),
            "curr_str": str(current)
        }

        report((part + 1) * 25, state_payload)

    return {
        "operation": "fibonacci calculation",
        "index": index,
        "value": previous,
        "digits": len(str(previous))
    }


# ============================================================
# JOB EXECUTION
# ============================================================

def execute(job):
    global active_jobs

    jid = job["id"]
    attempt = job.get("attempt", 1) or 1
    recovery_count = job.get("recovery_count", 0) or 0
    is_recovery = (job.get("status") == "RECOVERING") or (recovery_count > 0)

    active_jobs += 1

    print(
        f"\n[JOB RECEIVED] {jid} | "
        f"type: {job['workload']} | "
        f"attempt: {attempt} | "
        f"recovery: {is_recovery} | "
        f"submitted by: {job.get('submitted_by', 'unknown user')}"
    )

    started_at = time.perf_counter()

    # Recovery: Load genuine persisted computation state
    resume_state = None
    seq = 1
    if is_recovery:
        print(f"[JOB RECOVERY] Retrieving latest valid checkpoint for {jid}...")
        valid_cp = fetch_valid_checkpoint(jid)
        if valid_cp:
            resume_state = valid_cp.get("payload")
            seq = int(valid_cp.get("seq", 0)) + 1
            print(
                f"[JOB RECOVERY] Successfully restored checkpoint seq {valid_cp.get('seq')} "
                f"(hash {valid_cp.get('state_hash', '')[:10]}...)"
            )
        else:
            print(f"[JOB RECOVERY] No valid checkpoint available. Starting fresh execution.")

    # Signal RUNNING to control plane with fencing token
    initial_progress = 0
    if resume_state:
        if "completed_slices" in resume_state:
            initial_progress = int(resume_state["completed_slices"]) * 25
        elif "completed_tiles" in resume_state:
            initial_progress = int(resume_state["completed_tiles"]) * 25

    init_res = request(
        "POST",
        f"/providers/jobs/{jid}/update",
        json={
            "status": "RUNNING",
            "progress": initial_progress,
            "attempt": attempt
        }
    )
    if init_res.status_code == 409:
        print(
            f"[FENCING REJECTED] Execution attempt {attempt} for job {jid} rejected by control plane. Aborting."
        )
        active_jobs = max(0, active_jobs - 1)
        return

    seq_tracker = [seq]

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

        def report(progress, state_payload):
            checkpoint(
                jid,
                progress,
                started_at,
                workload,
                state_payload,
                attempt=attempt,
                seq=seq_tracker[0]
            )
            seq_tracker[0] += 1

        if workload == "matrix_multiply":
            total = run_matrix_multiply(
                size,
                report,
                resume_state=resume_state
            )

        elif workload == "prime_search":
            total = run_prime_search(
                size,
                report,
                resume_state=resume_state
            )

        elif workload == "fibonacci":
            total = run_fibonacci(
                size,
                report,
                resume_state=resume_state
            )

        elif workload == "custom_python":
            # Stage 6: Documented Custom Python Recovery Strategy
            # Arbitrary OS subprocess execution state cannot be safely serialized across
            # machine boundaries without specialized virtualization. Therefore, custom Python
            # jobs restart cleanly from the beginning if recovered, logging an explicit audit notice.
            if is_recovery:
                print(
                    f"[CUSTOM PYTHON] Arbitrary subprocesses cannot transparently migrate memory state. "
                    f"Restarting workload cleanly from beginning."
                )

            code = job["requirements"].get(
                "python_code",
                ""
            )

            if not code.strip():
                raise ValueError("No Python code was supplied")

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
            report(100, {"workload": "custom_python", "status": "completed"})

        else:
            raise ValueError(
                f"Unsupported workload type: {workload}"
            )

        message = {
            "matrix_multiply": "Matrix computation completed",
            "prime_search": "Prime search completed",
            "fibonacci": "Fibonacci computation completed",
            "custom_python": "Uploaded Python code completed"
        }.get(
            workload,
            "Workload completed"
        )

        elapsed = round(
            time.perf_counter()
            - started_at,
            4
        )

        comp_res = request(
            "POST",
            f"/providers/jobs/{jid}/update",
            json={
                "status": "COMPLETED",
                "progress": 100,
                "attempt": attempt,
                "actual_cost": round(.15 / 3600 * elapsed, 5),
                "result": {
                    "message": message,
                    "workload": workload,
                    "input_size": size,
                    "output": total,
                    "provider": PID,
                    "attempt": attempt,
                    "recovered": is_recovery,
                    "elapsed_seconds": elapsed
                }
            }
        )
        if comp_res.status_code == 409:
            print(
                f"[FENCING REJECTED] Job completion update for {jid} (attempt {attempt}) rejected by control plane."
            )

        print(
            f"[JOB COMPLETED] {jid} | "
            f"output:\n{total}\n"
        )

    except FencingError as fe:
        print(f"[JOB ABORTED] Fenced out: {fe}\n")

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
                    "attempt": attempt,
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