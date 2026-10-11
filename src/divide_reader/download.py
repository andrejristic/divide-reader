"""Download local GGUF models with resume and SHA256 check."""
from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Callable

import httpx

from . import paths
from .providers.catalog import LocalModel


def total_ram_gb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return 8.0


def free_disk_gb(path: Path) -> float:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 1024 ** 3


def target_path(m: LocalModel) -> Path:
    return paths.models_dir() / m.filename


def is_downloaded(m: LocalModel) -> bool:
    p = target_path(m)
    return p.is_file() and p.stat().st_size == m.size


def download(m: LocalModel, progress: Callable[[int, int], None] | None = None,
             cancel: threading.Event | None = None) -> Path:
    dest = target_path(m)
    if is_downloaded(m):
        return dest
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    if free_disk_gb(dest.parent) * 1024 ** 3 < (m.size - have) + 512 * 1024 ** 2:
        raise OSError(f"not enough disk space for {m.label}")
    headers = {"Range": f"bytes={have}-"} if have else {}
    with httpx.stream("GET", m.url, headers=headers, follow_redirects=True, timeout=60) as r:
        if r.status_code == 200:
            have = 0  # server ignored the range; start over
        elif r.status_code != 206:
            r.raise_for_status()
        with open(part, "ab" if have else "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                if cancel is not None and cancel.is_set():
                    raise InterruptedError("download cancelled")
                f.write(chunk)
                have += len(chunk)
                if progress:
                    progress(have, m.size)
    if sha256_file(part) != m.sha256:
        part.unlink()
        raise ValueError(f"{m.filename}: checksum mismatch, file deleted; try again")
    part.rename(dest)
    return dest


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
