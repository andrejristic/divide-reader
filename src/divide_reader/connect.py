"""Turn a start-screen choice (provider + model + session login) into a ready Provider."""
from __future__ import annotations

from pathlib import Path

import httpx

from . import localserver, providers
from .auth import Session
from .providers.base import ModelSpec, Provider, ProviderSpec
from .providers.catalog import LOCAL_MODELS, provider as get_spec


class Connection:
    """Holds the provider and, for the built-in model, the running llama-server."""

    def __init__(self, provider: Provider, server: localserver.LocalServer | None = None):
        self.provider = provider
        self.server = server

    def close(self) -> None:
        if self.server:
            self.server.stop()


def local_model_spec(path: Path) -> ModelSpec:
    for m in LOCAL_MODELS:
        if m.filename == path.name:
            return ModelSpec(path.name, m.label, free=True)
    return ModelSpec(path.name, path.stem, free=True)


def server_args_for(path: Path) -> tuple[str, ...]:
    for m in LOCAL_MODELS:
        if m.filename == path.name:
            return m.server_args
    return ()


def ollama_models(base: str = "http://127.0.0.1:11434") -> list[str]:
    r = httpx.get(f"{base}/api/tags", timeout=5)
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]


def openrouter_models(key: str | None = None) -> list[ModelSpec]:
    """Live model list with prices (USD per token in the API, converted to per 1M)."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = httpx.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=20)
    r.raise_for_status()
    out = []
    for m in r.json().get("data", []):
        pr = m.get("pricing") or {}
        try:
            pin, pout = float(pr.get("prompt", "nan")) * 1e6, float(pr.get("completion", "nan")) * 1e6
        except ValueError:
            pin = pout = float("nan")
        free = m["id"].endswith(":free") or (pin == 0 and pout == 0)
        out.append(ModelSpec(m["id"], m.get("name", m["id"]),
                             None if pin != pin else pin, None if pout != pout else pout, free=free))
    return out


def connect(spec: ProviderSpec | str, model: ModelSpec | str, session: Session | None = None,
            prefer_gpu: bool | None = None) -> Connection:
    spec = get_spec(spec) if isinstance(spec, str) else spec
    if spec.id == "local":
        path = Path(model.id if isinstance(model, ModelSpec) else model)
        if not path.is_absolute():
            path = localserver.paths.models_dir() / path
        server = localserver.LocalServer(path, server_args_for(path), prefer_gpu=prefer_gpu)
        server.start()
        return Connection(providers.make(spec, local_model_spec(path), base_url=server.base_url), server)
    if isinstance(model, str):
        model = next((m for m in spec.models if m.id == model), ModelSpec(model, model, free=spec.group != "paid"))
    key = session.get(spec.id) if session else None
    return Connection(providers.make(spec, model, api_key=key))
