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
import shutil
import argparse
import queue
import re
import urllib.parse
from pathlib import Path


def get_ffmpeg_binary():
    """Locate FFmpeg using an explicit executable path, PATH, then imageio_ffmpeg."""
    configured = os.getenv("NEXORA_FFMPEG_PATH") or os.getenv("FFMPEG_PATH")
    if configured:
        configured = configured.strip().strip('"')
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        # Also allow a command name that can be resolved using the Windows PATH.
        return shutil.which(configured)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def get_ffmpeg_version():
    """Return FFmpeg version string or None if not available."""
    binary = get_ffmpeg_binary()
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return None
        first_line = result.stdout.split("\n")[0].strip()
        return first_line or "unknown"
    except Exception:
        return None


# ============================================================
# BACKEND CONFIGURATION & CONNECTIVITY DISCOVERY
# ============================================================

DEFAULT_LOCAL_URL = "http://127.0.0.1:8000"
DEFAULT_ONLINE_URL = "https://nexora-unified-compute-management.onrender.com"

def check_backend_health(url: str, timeout: float = 3.0) -> bool:
    """Probes /health endpoint to check if control plane is responding."""
    try:
        clean = url.rstrip("/")
        resp = requests.get(f"{clean}/health", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False

def discover_backend_url(preferred_mode: str = "auto", custom_url: str = None) -> str:
    """
    Discovers the active Nexora control plane URL:
    - If custom_url or UCMP_BACKEND_URL is set, prioritizes it.
    - If preferred_mode is 'online', targets DEFAULT_ONLINE_URL.
    - If preferred_mode is 'local', targets DEFAULT_LOCAL_URL.
    - If preferred_mode is 'auto', probes LOCAL first, then ONLINE cloud backend.
    """
    if custom_url:
        return custom_url.rstrip("/")

    env_url = os.getenv("UCMP_BACKEND_URL")
    if env_url:
        return env_url.rstrip("/")

    if preferred_mode == "online":
        return DEFAULT_ONLINE_URL
    elif preferred_mode == "local":
        return DEFAULT_LOCAL_URL

    # Auto discovery: check if local dev server is active first
    print("[CONNECTIVITY] Probing local control plane (127.0.0.1:8000)...")
    if check_backend_health(DEFAULT_LOCAL_URL, timeout=1.5):
        print(f"[CONNECTIVITY] Found active local control plane at {DEFAULT_LOCAL_URL}")
        return DEFAULT_LOCAL_URL

    print("[CONNECTIVITY] Probing cloud control plane (onrender.com)...")
    if check_backend_health(DEFAULT_ONLINE_URL, timeout=3.5):
        print(f"[CONNECTIVITY] Found active cloud control plane at {DEFAULT_ONLINE_URL}")
        return DEFAULT_ONLINE_URL

    # If neither responded immediately (e.g. Render waking up), default to online cloud
    print(f"[CONNECTIVITY] Localhost offline. Targeting cloud control plane at {DEFAULT_ONLINE_URL}")
    return DEFAULT_ONLINE_URL

BASE = os.getenv(
    "UCMP_BACKEND_URL",
    DEFAULT_ONLINE_URL
).rstrip("/")

is_connected = False
ALLOW_LOCAL_BACKEND_FAILOVER = False

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
active_streams = {}
active_streams_lock = threading.Lock()


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

    if not gpu_name:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3, check=True,
            )
            rows = [row.split(",", 1) for row in result.stdout.splitlines() if "," in row]
            if rows:
                gpu_name = ", ".join(row[0].strip() for row in rows)
                gpu_count = len(rows)
                gpu_memory_gb = round(sum(float(row[1].strip()) for row in rows) / 1024, 2)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    if not gpu_name and platform.system() == "Windows":
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=5,
            )
            names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if names:
                gpu_name = ", ".join(names)
                gpu_count = len(names)
        except (OSError, subprocess.SubprocessError):
            pass

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

def get_stream_encoders():
    """Return H.264 encoders compiled in FFmpeg and able to initialize here."""
    binary = get_ffmpeg_binary()
    if not binary:
        return []
    try:
        result = subprocess.run([binary, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=8)
        text = (result.stdout or "") + (result.stderr or "")
        compiled = [name for name in ("libx264", "h264_nvenc", "h264_qsv", "h264_amf") if re.search(rf"\b{name}\b", text)]
        working = []
        for name in compiled:
            try:
                probe = subprocess.run(
                    [binary, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=1",
                     "-frames:v", "1", "-c:v", name, "-f", "null", "-"],
                    capture_output=True, text=True, timeout=8
                )
                if probe.returncode == 0:
                    working.append(name)
            except (OSError, subprocess.SubprocessError):
                continue
        return working
    except (OSError, subprocess.SubprocessError):
        return []

STREAM_ENCODERS = get_stream_encoders()


# ============================================================
# HTTP REQUEST
# ============================================================

def request(method, path, **kwargs):
    timeout = kwargs.pop("timeout", 15)
    return requests.request(
        method,
        BASE + path,
        headers=HEAD,
        timeout=timeout,
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

    gpu_memory_percent = None
    gpu_compute_percent = None

    # nvidia-smi reports device-wide hardware utilization and memory, including
    # work from processes other than this provider agent.
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2, check=True
        )
        compute_values = []
        memory_values = []
        for line in result.stdout.splitlines():
            fields = [field.strip() for field in line.split(",")]
            if len(fields) != 3 or any(value in ("", "N/A", "[Not Supported]") for value in fields):
                continue
            compute, used_mb, total_mb = (float(value) for value in fields)
            if total_mb > 0:
                compute_values.append(compute)
                memory_values.append(used_mb / total_mb * 100)
        if compute_values:
            gpu_compute_percent = round(sum(compute_values) / len(compute_values), 1)
            gpu_memory_percent = round(sum(memory_values) / len(memory_values), 1)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass

    # Torch allocator usage is a truthful fallback for this process' own GPU
    # memory only. GPU compute stays unavailable when hardware telemetry is absent.
    if gpu_memory_percent is None:
        try:
            if SYSTEM_INFO["cuda_available"] and importlib.util.find_spec("torch"):
                import torch
                memory_values = []
                for index in range(torch.cuda.device_count()):
                    total = torch.cuda.get_device_properties(index).total_memory
                    used = max(torch.cuda.memory_allocated(index), torch.cuda.memory_reserved(index))
                    if total > 0:
                        memory_values.append(used / total * 100)
                if memory_values:
                    gpu_memory_percent = round(sum(memory_values) / len(memory_values), 1)
        except Exception:
            pass

    return {

        "cpu": cpu_percent,

        "ram": ram_percent,

        "gpu": gpu_memory_percent,

        "gpu_memory": gpu_memory_percent,

        "gpu_compute": gpu_compute_percent,

        "disk": disk_percent
    }


# ============================================================
# PROVIDER REGISTRATION
# ============================================================

def register(retry_indefinitely=True):
    global BASE, is_connected

    # Backend currently requires these fields.
    # Additional hardware information is included
    # separately in provider metadata if your backend
    # is extended to store it.

    _ffmpeg_bin = get_ffmpeg_binary()
    _ffmpeg_ver = get_ffmpeg_version() if _ffmpeg_bin else None

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
            ),

        "system_info": {
            **SYSTEM_INFO,
            "ffmpeg_available": bool(_ffmpeg_bin),
            "ffmpeg_version": _ffmpeg_ver,
            "stream_encode_capable": bool(_ffmpeg_bin and STREAM_ENCODERS),
            "stream_encoders": STREAM_ENCODERS,
        }
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
        f"FFmpeg    : "
        f"{_ffmpeg_ver or ('Available' if _ffmpeg_bin else 'None')}"
    )
    print(f"H.264 encoders: {', '.join(STREAM_ENCODERS) if STREAM_ENCODERS else 'None (streaming unavailable)'}")
    print(
        f"OS        : "
        f"{SYSTEM_INFO['os']}"
    )
    print("--------------------------------")
    print()

    attempt = 1
    backoff = 3
    while True:
        try:
            print(f"[CONNECTING] Registering with control plane at {BASE}...")
            response = request(
                "POST",
                "/providers/register",
                json=data,
                timeout=15
            )
            response.raise_for_status()
            is_connected = True
            print(f"[ONLINE] Successfully connected and registered as {NAME} ({PID})")
            return response
        except Exception as e:
            is_connected = False
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code in (401, 403):
                raise RuntimeError(
                    f"Provider authentication was rejected by {BASE} (HTTP {status_code}). "
                    "Set PROVIDER_SHARED_TOKEN to the same value on this provider and backend; "
                    "the token value is intentionally not shown."
                ) from None
            if not retry_indefinitely:
                raise

            # Only auto-discovered local endpoints may fail over, and only for
            # transport failures. An HTTP response proves a server was reached
            # and must not silently register the provider elsewhere.
            transport_failure = isinstance(e, (requests.ConnectionError, requests.Timeout))
            if ALLOW_LOCAL_BACKEND_FAILOVER and BASE == DEFAULT_LOCAL_URL and attempt >= 2 and transport_failure:
                print(f"[AUTO-FAILOVER] Localhost unreachable. Switching to cloud control plane ({DEFAULT_ONLINE_URL})...")
                BASE = DEFAULT_ONLINE_URL

            print(f"[OFFLINE] Cannot reach control plane at {BASE} ({e})")
            print(f"          Retrying in {backoff}s... (Render free instances take ~50s to wake from sleep)")
            time.sleep(backoff)
            backoff = min(15, backoff + 2)
            attempt += 1


# ============================================================
# HEARTBEAT
# ============================================================

def heartbeat():
    global is_connected
    while True:
        if is_connected:
            try:
                res = request(
                    "POST",
                    f"/providers/{PID}/heartbeat",
                    json={
                        "status": "BUSY" if active_jobs or active_streams else "ONLINE",
                        "utilization": utilization()
                    },
                    timeout=8
                )
                if res.status_code == 404:
                    print("[NOTICE] Registration expired or control plane rebooted. Re-registering...")
                    try:
                        register(retry_indefinitely=False)
                    except Exception:
                        pass
                else:
                    res.raise_for_status()
            except requests.RequestException:
                if is_connected:
                    print(f"[HEARTBEAT] Connection to {BASE} interrupted. Entering standby.")
                    is_connected = False
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
# VIDEO COMPRESSION WORKLOAD
# ============================================================

COMPRESSION_PROFILES = {
    "high":            {"crf": 20, "preset": "slow"},
    "balanced":        {"crf": 26, "preset": "faster"},
    "max_compression": {"crf": 32, "preset": "fast"},
}
CODEC_MAP = {
    "h264": "libx264",
    "h265": "libx265",
    "vp9":  "libvpx-vp9",
}
RES_SCALE = {
    "1080p": "scale='min(1920,iw)':-2",
    "720p":  "scale='min(1280,iw)':-2",
    "480p":  "scale='min(854,iw)':-2",
}

def _probe_video(path):
    """Run ffprobe-style check via ffmpeg -i and parse stderr."""
    import re as _re
    binary = get_ffmpeg_binary()
    if not binary:
        return {"valid": False, "error": "FFmpeg not found"}
    try:
        proc = subprocess.run(
            [binary, "-hide_banner", "-i", str(path)],
            capture_output=True, text=True, timeout=15
        )
        out = proc.stderr
        dur_m = _re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
        duration = None
        if dur_m:
            h, m, s = float(dur_m.group(1)), float(dur_m.group(2)), float(dur_m.group(3))
            duration = round(h * 3600 + m * 60 + s, 2)
        vid_m = _re.search(r"Stream.*Video:\s*([a-zA-Z0-9_\-]+).*?(\d{2,5})x(\d{2,5})", out)
        valid = bool(vid_m and duration and duration > 0)
        return {
            "valid": valid,
            "duration": duration,
            "codec": vid_m.group(1).lower() if vid_m else None,
            "width": int(vid_m.group(2)) if vid_m else None,
            "height": int(vid_m.group(3)) if vid_m else None,
            "has_audio": "Audio:" in out,
            "error": None if valid else "No valid video stream"
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def run_video_compress(job, report_progress):
    """
    Download input artifact from control plane, compress with FFmpeg,
    validate output, upload to control plane, return structured report.
    """
    import re as _re

    binary = get_ffmpeg_binary()
    if not binary:
        raise RuntimeError("FFmpeg binary not found on this provider")

    reqs = job["requirements"]
    artifact_id = reqs.get("input_artifact_id")
    if not artifact_id:
        raise ValueError("video_compress job missing input_artifact_id")

    codec_key = reqs.get("codec", "h264")
    profile_key = reqs.get("compression_profile", "balanced")
    target_res = reqs.get("target_resolution", "720p")
    strip_audio = reqs.get("strip_audio", False)

    encoder = CODEC_MAP.get(codec_key, "libx264")
    profile = COMPRESSION_PROFILES.get(profile_key, COMPRESSION_PROFILES["balanced"])

    jid = job["id"]

    with tempfile.TemporaryDirectory(prefix=f"nexora-video-{jid}-") as workdir:
        workdir = Path(workdir)

        # --- Download input artifact ---
        report_progress(5, {"workload": "video_compress", "stage": "downloading"})
        dl_resp = request(
            "GET",
            f"/providers/jobs/{jid}/artifacts/{artifact_id}/download",
            stream=True
        )
        dl_resp.raise_for_status()

        cd = dl_resp.headers.get("content-disposition", "")
        fn_match = _re.search(r'filename=["\']?([^"\'\s]+)["\']?', cd)
        input_filename = fn_match.group(1) if fn_match else "input.mp4"
        input_path = workdir / input_filename

        with open(input_path, "wb") as f:
            if hasattr(dl_resp, "iter_content"):
                for chunk in dl_resp.iter_content(65536):
                    f.write(chunk)
            elif hasattr(dl_resp, "iter_bytes"):
                for chunk in dl_resp.iter_bytes(65536):
                    f.write(chunk)
            else:
                f.write(dl_resp.content)

        print(f"[VIDEO] Downloaded input: {input_path} ({input_path.stat().st_size} bytes)")

        # --- Validate input ---
        probe_in = _probe_video(input_path)
        if not probe_in["valid"]:
            raise ValueError(f"Input video invalid: {probe_in.get('error')}")

        input_size = input_path.stat().st_size
        duration = probe_in.get("duration", 0) or 0

        # --- Build FFmpeg command using argument array ---
        output_path = workdir / f"{jid}_output.mp4"
        vf_filters = []
        if target_res in RES_SCALE and target_res != "original":
            vf_filters.append(RES_SCALE[target_res])

        cmd = [binary, "-y", "-i", str(input_path)]

        if vf_filters:
            cmd += ["-vf", ",".join(vf_filters)]

        cmd += ["-c:v", encoder]

        if encoder in ("libx264", "libx265"):
            cmd += ["-crf", str(profile["crf"]), "-preset", profile["preset"]]
        elif encoder == "libvpx-vp9":
            cmd += ["-crf", str(profile["crf"]), "-b:v", "0"]

        if strip_audio:
            cmd += ["-an"]
        else:
            cmd += ["-c:a", "aac", "-b:a", "128k"]

        cmd += ["-movflags", "+faststart"]
        cmd += ["-progress", "pipe:1", "-nostats"]
        cmd += [str(output_path)]

        print(f"[VIDEO] Running FFmpeg: {' '.join(cmd)}")
        report_progress(10, {"workload": "video_compress", "stage": "encoding", "input_duration": duration})

        # --- Execute FFmpeg with stdout progress parsing ---
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # Prevent pipe deadlock
            text=True
        )

        last_reported = 10
        total_us = duration * 1_000_000 if duration > 0 else 1

        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us="):
                try:
                    out_time_us = int(line.split("=", 1)[1])
                    pct = min(90, 10 + int(80 * out_time_us / total_us))
                    if pct > last_reported + 4:
                        report_progress(pct, {
                            "workload": "video_compress",
                            "stage": "encoding",
                            "progress_pct": pct,
                            "out_time_us": out_time_us
                        })
                        last_reported = pct
                except (ValueError, ZeroDivisionError):
                    pass

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg exited with code {proc.returncode}")

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("FFmpeg produced no output file")

        # --- Validate output ---
        report_progress(92, {"workload": "video_compress", "stage": "validating"})
        probe_out = _probe_video(output_path)
        if not probe_out["valid"]:
            raise RuntimeError(f"Output video invalid after encoding: {probe_out.get('error')}")

        output_size = output_path.stat().st_size
        compression_ratio = round(input_size / max(output_size, 1), 3)

        print(f"[VIDEO] Output validated: {output_size} bytes, ratio {compression_ratio}x")

        # --- Upload output artifact to control plane ---
        report_progress(95, {"workload": "video_compress", "stage": "uploading"})
        with open(output_path, "rb") as fp:
            up_resp = request(
                "POST",
                f"/providers/jobs/{jid}/artifacts/upload",
                files={
                    "file": (output_path.name, fp, "video/mp4")
                },
                params={"artifact_type": "output"}
            )
        up_resp.raise_for_status()
        upload_meta = up_resp.json()

        output_artifact_id = upload_meta["artifact_id"]
        print(f"[VIDEO] Output artifact uploaded: {output_artifact_id}")

    return {
        "operation": "video_compress",
        "input_artifact_id": artifact_id,
        "output_artifact_id": output_artifact_id,
        "input_size_bytes": input_size,
        "output_size_bytes": output_size,
        "compression_ratio": compression_ratio,
        "codec": codec_key,
        "profile": profile_key,
        "target_resolution": target_res,
        "duration_seconds": duration,
        "input_probe": probe_in,
        "output_probe": probe_out,
    }


# ============================================================
# REMOTE STREAM ENCODING WORKLOAD
# ============================================================

def _stream_error_message(lines, input_seen):
    text = " ".join(lines).lower()
    if any(term in text for term in ("403", "unauthorized", "authentication failed", "invalid stream key", "publish.badname", "publish failed", "server error")):
        if not input_seen:
            return "The provider could not authenticate its read access to Nexora ingest. Stop and recreate the stream session."
        return "The destination rejected the stream credentials. Verify the destination stream key and try again."
    if input_seen and any(term in text for term in (
        "error writing header", "error writing trailer", "error muxing a packet", "av_interleaved_write_frame",
        "broken pipe", "failed to write packet", "could not write", "connection reset by peer",
    )):
        return "FFmpeg received media but could not publish encoded output to the destination. Verify the destination ingest URL, stream key, and network connection."
    if any(term in text for term in ("connection refused", "connection timed out", "network is unreachable", "could not resolve", "end of file")):
        if not input_seen:
            return "The provider could not read media from Nexora ingest. Confirm OBS or Browser Capture is publishing to this session and that the provider can reach MediaMTX."
        return "The provider could not reach the destination server. Check its address and network availability."
    if "encoder" in text and any(term in text for term in ("not found", "cannot load", "failed to open", "no capable devices")):
        return "The selected FFmpeg encoder is not available on this provider. Install a supported FFmpeg build and retry."
    if not input_seen:
        return "No media input arrived before the provider timeout. Start OBS or Browser Capture publishing to Nexora before the timeout and try again."
    return "The provider could not complete stream encoding. Check the input and destination configuration."


def _build_stream_ffmpeg_args(binary, stream_data, cfg, encoder):
    """Build a safe-argument-list FFmpeg command; never log the credential URL."""
    width, height = int(cfg.get("width", 1280)), int(cfg.get("height", 720))
    fps = int(cfg.get("fps", 30))
    v_bitrate = int(cfg.get("video_bitrate_kbps", 3000))
    a_bitrate = int(cfg.get("audio_bitrate_kbps", 160))
    destination_url = urllib.parse.urlsplit(stream_data["destination_url"])
    destination_key = urllib.parse.quote(stream_data.get("destination_key", ""), safe="/-_.~")
    destination_path = f"{destination_url.path.rstrip('/')}/{destination_key}" if destination_key else destination_url.path
    destination = urllib.parse.urlunsplit((destination_url.scheme, destination_url.netloc, destination_path, destination_url.query, ""))

    args = [binary, "-hide_banner", "-nostdin", "-loglevel", "info", "-rtsp_transport", "tcp",
            "-i", stream_data["source_url"], "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "-r", str(fps), "-c:v", encoder]
    if encoder == "libx264":
        args += ["-preset", cfg.get("preset", "veryfast")]
    elif encoder == "h264_nvenc":
        args += ["-preset", "p4"]
    elif encoder == "h264_qsv":
        args += ["-preset", "veryfast"]
    elif encoder == "h264_amf":
        args += ["-quality", "balanced"]
    args += ["-b:v", f"{v_bitrate}k", "-maxrate", f"{v_bitrate + 500}k", "-bufsize", f"{v_bitrate * 2}k",
             "-pix_fmt", "yuv420p", "-g", str(fps * 2), "-c:a", "aac", "-b:a", f"{a_bitrate}k", "-ar", "48000",
             "-f", "flv", "-stats_period", "1", "-progress", "pipe:1", "-nostats", destination]
    return args


def run_stream_encoder(stream_data, stop_event, retry_attempt=0, input_deadline=None):
    """Run one session-scoped FFmpeg process; only measured FFmpeg progress is reported."""
    session_id = stream_data["session_id"]
    provider_id = stream_data["provider_id"]
    binary = get_ffmpeg_binary()
    proc = None
    error_lines = []
    input_seen = False
    state_lock = threading.Lock()
    metrics = {"status": "STARTING"}
    status_value = ["STARTING"]
    started = time.monotonic()
    input_timeout = max(1, int(os.getenv("STREAM_INPUT_TIMEOUT_SECONDS", "180")))
    # A provider can claim a session before OBS or Browser Capture has started
    # publishing. Keep the session and its short-lived ingest credential valid
    # through this entire initial-input window, even when RTSP DESCRIBE returns
    # 404 and FFmpeg exits immediately.
    input_deadline = input_deadline if input_deadline is not None else started + input_timeout
    stdout_queue = queue.Queue()
    stderr_queue = queue.Queue()
    requested_stop = [False]
    last_heartbeat = 0.0
    readers = []
    retrying = False

    def update_status(new_status):
        with state_lock:
            if status_value[0] == new_status:
                return False
            status_value[0] = new_status
            metrics["status"] = new_status
            snapshot = dict(metrics)
        try:
            response = request("POST", f"/providers/streams/{session_id}/heartbeat", json={
                "provider_id": provider_id, "status": new_status, "metrics": snapshot,
            }, timeout=8)
            if response.status_code == 200:
                reply = response.json()
                return reply.get("command") == "STOP_STREAM" or reply.get("action") == "stop"
        except requests.RequestException:
            print("[STREAM STATUS] Could not report a state change; will retry on heartbeat.")
        return False

    def progress_reader():
        try:
            for line in proc.stdout:
                stdout_queue.put(line.rstrip("\r\n"))
        finally:
            stdout_queue.put(None)

    def diagnostic_reader():
        nonlocal input_seen
        try:
            for line in proc.stderr:
                low = line.lower()
                if "input #0" in low:
                    input_seen = True
                    stderr_queue.put("INPUT")
                if input_seen:
                    fps_match = re.search(r"\b(\d+(?:\.\d+)?)\s*fps\b", low)
                    if fps_match:
                        with state_lock:
                            metrics["input_fps"] = float(fps_match.group(1))
                    bitrate_match = re.search(r"\bbitrate:\s*(\d+(?:\.\d+)?)\s*kb/s", low)
                    if bitrate_match:
                        with state_lock:
                            metrics["input_bitrate_kbps"] = float(bitrate_match.group(1))
                if any(word in low for word in ("error", "failed", "refused", "timed out", "unauthorized", "403", "not found", "no capable devices", "cannot load", "end of file")):
                    error_lines.append(line[:400])
        finally:
            stderr_queue.put(None)

    print(f"\n[STREAM RECEIVED] {session_id} | profile: {stream_data.get('profile_name')} | assigned provider: {provider_id}")
    print("[STREAM] Waiting for authenticated source input; destination credentials are hidden.")
    if not binary:
        error = "FFmpeg is not installed or could not be found on this provider."
        try:
            request("POST", f"/providers/streams/{session_id}/stopped", json={"provider_id": provider_id, "status": "FAILED", "error": error})
        except requests.RequestException:
            pass
        with active_streams_lock:
            active_streams.pop(session_id, None)
        return

    cfg = stream_data.get("encoding_config") or {}
    fps = int(cfg.get("fps", 30))
    encoders = set(STREAM_ENCODERS)
    selected = cfg.get("video_encoder", "libx264")
    if selected not in encoders:
        selected = "libx264" if "libx264" in encoders else None
    if not selected:
        try:
            request("POST", f"/providers/streams/{session_id}/stopped", json={"provider_id": provider_id, "status": "FAILED", "error": "No compatible H.264 encoder is available in FFmpeg on this provider."})
        except requests.RequestException:
            pass
        with active_streams_lock:
            active_streams.pop(session_id, None)
        return

    args = _build_stream_ffmpeg_args(binary, stream_data, cfg, selected)

    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        readers = [threading.Thread(target=progress_reader, daemon=True), threading.Thread(target=diagnostic_reader, daemon=True)]
        for reader in readers:
            reader.start()
        if update_status("WAITING_FOR_INPUT"):
            stop_event.set()
        progress_values = {}
        saw_progress = False
        last_input_at = time.monotonic()
        while proc.poll() is None and not stop_event.is_set():
            try:
                line = stdout_queue.get(timeout=0.5)
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    progress_values[key] = value
                    if key == "progress":
                        frame = int(progress_values.get("frame", "0") or 0)
                        measured = {}
                        try:
                            measured["fps"] = round(float(progress_values["fps"]), 2)
                        except (KeyError, ValueError):
                            pass
                        bitrate = progress_values.get("bitrate", "").replace("kbits/s", "").strip()
                        try:
                            measured["bitrate_kbps"] = round(float(bitrate), 1)
                        except ValueError:
                            pass
                        if progress_values.get("speed"):
                            measured["speed"] = progress_values["speed"]
                        try:
                            measured["dropped_frames"] = int(progress_values["drop_frames"])
                        except (KeyError, ValueError):
                            pass
                        measured["uptime_seconds"] = max(0, int(time.monotonic() - started))
                        with state_lock:
                            metrics.update(measured)
                        if frame > 0:
                            last_input_at = time.monotonic()
                            if update_status("ENCODING"):
                                stop_event.set()
                            if progress_values.get("progress") == "continue" and not stop_event.is_set():
                                if update_status("STREAMING"):
                                    stop_event.set()
                            saw_progress = True
                elif line is None:
                    time.sleep(0.1)
            except queue.Empty:
                pass
            while True:
                try:
                    diagnostic = stderr_queue.get_nowait()
                except queue.Empty:
                    break
                if diagnostic == "INPUT":
                    input_seen = True
                    last_input_at = time.monotonic()
                    if status_value[0] == "WAITING_FOR_INPUT":
                        update_status("RECEIVING")
            if ((not input_seen and time.monotonic() >= input_deadline)
                    or (input_seen and time.monotonic() - last_input_at > input_timeout)):
                error_lines.append("input timeout")
                break
            now = time.monotonic()
            if now - last_heartbeat >= 5:
                with state_lock:
                    current_state, snapshot = status_value[0], dict(metrics)
                try:
                    response = request("POST", f"/providers/streams/{session_id}/heartbeat", json={
                        "provider_id": provider_id, "status": current_state, "metrics": snapshot,
                    }, timeout=8)
                    response.raise_for_status()
                    command_reply = response.json()
                    if command_reply.get("command") == "STOP_STREAM" or command_reply.get("action") == "stop":
                        requested_stop[0] = True
                        stop_event.set()
                        break
                except (requests.RequestException, ValueError):
                    print("[STREAM HEARTBEAT] Control plane unavailable; retrying.")
                last_heartbeat = now

        for reader in readers:
            reader.join(timeout=1)
        while True:
            try:
                diagnostic = stderr_queue.get_nowait()
            except queue.Empty:
                break
            if diagnostic == "INPUT":
                input_seen = True

        if stop_event.is_set():
            final_status = "STOPPED" if requested_stop[0] or status_value[0] == "STOPPING" else "STOPPED"
            failure = None
        else:
            return_code = proc.poll()
            if return_code is None:
                failure = _stream_error_message(error_lines, input_seen)
                final_status = "FAILED"
            elif return_code != 0:
                failure = _stream_error_message(error_lines, input_seen)
                final_status = "FAILED"
            elif not saw_progress:
                failure = "The input ended before FFmpeg produced an encoded output frame."
                final_status = "FAILED"
            else:
                failure = None
                final_status = "COMPLETED"

        failure_text = " ".join(error_lines).lower()
        selected_encoder = (stream_data.get("encoding_config") or {}).get("video_encoder", selected)
        hardware_initialization_failure = (
            not saw_progress and selected_encoder != "libx264"
            and any(term in failure_text for term in ("encoder", "cuda", "nvenc", "qsv", "amf", "device"))
        )
        software_fallback = (
            final_status == "FAILED" and selected_encoder != "libx264"
            and "libx264" in encoders and hardware_initialization_failure
        )
        transient_network = (
            final_status == "FAILED" and retry_attempt < 2
            and any(term in failure_text for term in ("connection refused", "connection timed out", "network is unreachable", "could not resolve", "end of file"))
            and not any(term in failure_text for term in ("401", "403", "unauthorized", "invalid stream key", "input timeout"))
        )
        # For browser-based input modes (camera, simulation, screen capture),
        # RTSP 401/403 errors that occur before any input was detected are
        # transient: they indicate MediaMTX has not yet relayed the WebRTC WHIP
        # stream to RTSP. Treat these as "waiting for publisher" so we retry
        # instead of failing immediately.
        source_mode = (stream_data.get("encoding_config") or {}).get("source_mode", "obs")
        browser_modes = ("browser_capture", "browser_camera", "browser_simulation")
        is_browser_mode = source_mode in browser_modes
        browser_auth_pending = (
            is_browser_mode
            and not input_seen
            and not saw_progress
            and final_status == "FAILED"
            and time.monotonic() < input_deadline
            and any(term in failure_text for term in ("401", "403", "unauthorized", "not found", "404", "end of file", "connection refused"))
            and not any(term in failure_text for term in ("encoder", "cuda", "nvenc", "qsv", "amf", "no capable devices", "input timeout"))
        )
        waiting_for_publisher = (
            final_status == "FAILED" and not input_seen and not saw_progress
            and time.monotonic() < input_deadline
            and any(term in failure_text for term in (
                "404", "not found", "no stream", "end of file", "connection refused",
                "connection timed out", "connection reset", "input timeout",
            ))
            and not any(term in failure_text for term in (
                "401", "403", "unauthorized", "authentication failed", "invalid stream key",
                "encoder", "cuda", "nvenc", "qsv", "amf", "no capable devices",
            ))
        )
        # browser_auth_pending supersedes normal waiting_for_publisher check
        if browser_auth_pending:
            waiting_for_publisher = True
        if not stop_event.is_set() and (software_fallback or transient_network or waiting_for_publisher):
            if software_fallback:
                print(f"[STREAM] Hardware encoder {selected_encoder} failed to initialize; retrying with libx264.")
                stream_data["encoding_config"]["video_encoder"] = "libx264"
            elif waiting_for_publisher:
                if browser_auth_pending:
                    remaining = max(0, int(input_deadline - time.monotonic()))
                    print(f"[STREAM] Browser/WebRTC stream not yet relayed to RTSP — waiting for WHIP publish to complete ({remaining}s remaining).")
                else:
                    print("[STREAM] Ingest is not publishing yet; keeping the assigned session available while waiting for source media.")
            else:
                print(f"[STREAM] Media connection interrupted; reconnect attempt {retry_attempt + 1} of 2.")
            retrying = True
            with state_lock:
                metrics.clear()
            if update_status("STARTING") or update_status("WAITING_FOR_INPUT"):
                stop_event.set()
            backoff_seconds = min(2 * (retry_attempt + 1), max(0, input_deadline - time.monotonic())) if waiting_for_publisher else 2 * (retry_attempt + 1)
            if stop_event.wait(backoff_seconds):
                retrying = False
                final_status = "STOPPED"
                failure = None
            elif waiting_for_publisher:
                return run_stream_encoder(stream_data, stop_event, 0, input_deadline)
            else:
                return run_stream_encoder(stream_data, stop_event, retry_attempt + 1)
    except (OSError, subprocess.SubprocessError) as exc:
        # Do not include exception text because process arguments can contain private URLs.
        failure = "FFmpeg could not start on this provider. Verify the installed FFmpeg build and retry."
        final_status = "FAILED"
    finally:
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        with state_lock:
            final_metrics = dict(metrics)
        if not retrying:
            try:
                request("POST", f"/providers/streams/{session_id}/stopped", json={
                    "provider_id": provider_id, "status": final_status,
                    "metrics": final_metrics, "error": failure,
                }, timeout=8)
            except requests.RequestException:
                print("[STREAM END] Could not report session termination to control plane.")
            if final_status == "FAILED" and failure:
                print(f"[STREAM ERROR] {session_id} | {failure}")
            print(f"[STREAM {final_status}] {session_id} | encoder: {selected} | input detected: {bool(input_seen)}")
            with active_streams_lock:
                active_streams.pop(session_id, None)


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

        elif workload == "video_compress":
            video_result = run_video_compress(job, report)
            total = video_result

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

                stdin_input = job["requirements"].get("stdin_input") or ""
                process = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        source
                    ],
                    input=stdin_input if stdin_input else None,
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
            "custom_python": "Uploaded Python code completed",
            "video_compress": "Video compression completed"
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
                    "input_size": size if workload != "video_compress" else None,
                    "output": total,
                    "video": total if isinstance(total, dict) and total.get("operation") == "video_compress" else None,
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
    global is_connected
    while True:
        try:
            if not is_connected:
                # In offline standby: probe health before polling
                if check_backend_health(BASE, timeout=3.5):
                    print(f"[RECONNECTED] Control plane at {BASE} is reachable! Re-registering...")
                    try:
                        register(retry_indefinitely=False)
                    except Exception:
                        time.sleep(3)
                        continue
                else:
                    time.sleep(5)
                    continue

            response = request(
                "GET",
                f"/providers/{PID}/jobs/pending",
                timeout=10
            )
            response.raise_for_status()

            jobs = response.json()
            for job in jobs:
                threading.Thread(
                    target=execute,
                    args=(job,),
                    daemon=True
                ).start()

            # Claim one assigned stream through the existing authenticated provider API.
            if not active_streams:
                try:
                    s_resp = request(
                        "POST",
                        f"/providers/{PID}/streams/claim",
                        timeout=5
                    )
                    if s_resp.status_code == 200:
                        command = s_resp.json()
                        stream_data = command.get("session") if command.get("command") == "START_STREAM" else None
                        if stream_data and stream_data.get("provider_id") == PID:
                            session_id = stream_data.get("session_id")
                            # Allow the local provider to override the RTSP source URL
                            # given by the backend. Useful when the provider runs locally
                            # (connected to the online Render control plane) but reads
                            # from the local Docker MediaMTX instead of Render's loopback.
                            rtsp_override = os.getenv("PROVIDER_RTSP_BASE_URL", "").strip().rstrip("/")
                            if rtsp_override and stream_data.get("source_url"):
                                orig_parsed = urllib.parse.urlsplit(stream_data["source_url"])
                                new_parsed = urllib.parse.urlsplit(rtsp_override)
                                if new_parsed.scheme and new_parsed.netloc:
                                    stream_data = dict(stream_data)
                                    # Rebuild: override scheme+host, keep path+query from original
                                    stream_data["source_url"] = urllib.parse.urlunsplit((
                                        new_parsed.scheme,
                                        new_parsed.netloc,
                                        orig_parsed.path,
                                        orig_parsed.query,
                                        "",
                                    ))
                                    print(f"[STREAM] RTSP source URL overridden by PROVIDER_RTSP_BASE_URL: {new_parsed.scheme}://{new_parsed.netloc}{orig_parsed.path}")
                            stop_event = threading.Event()
                            with active_streams_lock:
                                if not active_streams:
                                    active_streams[session_id] = stop_event
                                    threading.Thread(
                                        target=run_stream_encoder,
                                        args=(stream_data, stop_event),
                                        daemon=True,
                                        name=f"nexora-stream-{session_id}",
                                    ).start()
                except Exception:
                    pass

        except requests.RequestException as e:
            if is_connected:
                print(f"[OFFLINE] Connection dropped ({e}). Polling paused until control plane reconnects.")
                is_connected = False
            time.sleep(5)
        else:
            time.sleep(2)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nexora Compute Provider Node")
    parser.add_argument("--online", action="store_true", help="Connect to cloud control plane (Render)")
    parser.add_argument("--local", action="store_true", help="Connect to localhost control plane (127.0.0.1:8000)")
    parser.add_argument("--url", type=str, default=None, help="Custom control plane URL")
    parser.add_argument("--token", type=str, default=None, help="Provider shared secret token")
    parser.add_argument("--id", type=str, default=None, help="Custom provider ID (for secondary/recovery nodes)")
    parser.add_argument("--name", type=str, default=None, help="Custom provider display name")
    args, _ = parser.parse_known_args()

    if args.id:
        PID = args.id.strip()
    if args.name:
        NAME = args.name.strip()

    if args.token:
        TOKEN = args.token
        HEAD["X-Provider-Token"] = TOKEN

    mode = "online" if args.online else ("local" if args.local else "auto")
    BASE = discover_backend_url(preferred_mode=mode, custom_url=args.url)
    ALLOW_LOCAL_BACKEND_FAILOVER = (
        mode == "auto" and not args.url and not os.getenv("UCMP_BACKEND_URL")
    )

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
