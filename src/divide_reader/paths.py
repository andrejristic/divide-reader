"""Where things live on disk."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP = "divide-reader"


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def projects_dir() -> Path:
    d = data_dir() / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP
    d.mkdir(parents=True, exist_ok=True)
    return d / "settings.json"


def install_dir() -> Path:
    """Folder of the installed program (/opt/divide-reader in the .deb, or the PyInstaller bundle)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    env = os.environ.get("DIVIDE_READER_HOME")
    if env:
        return Path(env)
    return Path("/opt") / APP


def llama_dir() -> Path:
    """Bundled llama.cpp builds: <install>/llama/{cpu,vulkan}/llama-server."""
    env = os.environ.get("DIVIDE_READER_LLAMA")
    return Path(env) if env else install_dir() / "llama"
