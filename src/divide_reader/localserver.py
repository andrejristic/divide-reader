"""Starts and stops the bundled llama-server.

The package ships two builds: cpu (with runtime-selected variants down to
AVX-only processors) and vulkan (any GPU with a Vulkan driver: NVIDIA, AMD,
Intel). Vulkan is used when a Vulkan device is present, otherwise cpu.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from . import paths
from .providers.catalog import LOCAL_PORT


def has_vulkan_gpu() -> bool:
    """True when vulkaninfo reports a real (non-CPU) device."""
    exe = shutil.which("vulkaninfo")
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "--summary"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    types = [ln for ln in out.splitlines() if "deviceType" in ln]
    return any("CPU" not in ln for ln in types)


def find_server(prefer_gpu: bool | None = None) -> tuple[Path, str]:
    """Return (llama-server path, 'vulkan'|'cpu'|'system')."""
    root = paths.llama_dir()
    gpu = has_vulkan_gpu() if prefer_gpu is None else prefer_gpu
    order = ["vulkan", "cpu"] if gpu else ["cpu"]
    for flavour in order:
        exe = root / flavour / "llama-server"
        if exe.is_file() and os.access(exe, os.X_OK):
            return exe, flavour
    exe = shutil.which("llama-server")
    if exe:
        return Path(exe), "system"
    raise FileNotFoundError(f"llama-server not found in {root} or on PATH")


class LocalServer:
    def __init__(self, model_path: Path, extra_args: tuple[str, ...] = (), port: int = LOCAL_PORT,
                 ctx: int = 8192, prefer_gpu: bool | None = None):
        self.model_path = Path(model_path)
        self.extra_args = extra_args
        self.port = port
        self.ctx = ctx
        self.prefer_gpu = prefer_gpu
        self.proc: subprocess.Popen | None = None
        self.flavour = ""
        self.log_path = paths.data_dir() / "llama-server.log"

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self, timeout: float = 600.0) -> None:
        if self.proc and self.proc.poll() is None:
            return
        exe, self.flavour = find_server(self.prefer_gpu)
        args = [str(exe), "-m", str(self.model_path), "--host", "127.0.0.1", "--port", str(self.port),
                "-c", str(self.ctx), "--jinja", *self.extra_args]
        if self.flavour == "vulkan":
            args += ["-ngl", "999"]
        log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, cwd=str(exe.parent))
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server exited (code {self.proc.returncode}); see {self.log_path}")
            try:
                if httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=2).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(1)
        self.stop()
        raise TimeoutError("llama-server did not become ready")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


def downloaded_models() -> list[Path]:
    return sorted(paths.models_dir().glob("*.gguf"))
