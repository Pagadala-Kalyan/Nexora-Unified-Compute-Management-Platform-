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
from pathlib import Path


def get_ffmpeg_binary():
    """Locate FFmpeg: check PATH first, then imageio_ffmpeg fallback."""
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
            if not retry_indefinitely:
                raise

            # If local host was targeted and unreachable, switch to online cloud backend
            if BASE == DEFAULT_LOCAL_URL and attempt >= 2:
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
                        "status": "BUSY" if active_jobs else "ONLINE",
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
    args, _ = parser.parse_known_args()

    if args.token:
        TOKEN = args.token
        HEAD["X-Provider-Token"] = TOKEN

    mode = "online" if args.online else ("local" if args.local else "auto")
    BASE = discover_backend_url(preferred_mode=mode, custom_url=args.url)

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