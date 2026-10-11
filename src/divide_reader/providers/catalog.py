"""Every model the start screen offers, plus the recommended local GGUF files.

Links and hashes for local models were checked on 2026-10-11. Prices are USD
per 1M tokens; paid prices can be edited in the GUI before a job, because
providers change them.
"""
from __future__ import annotations

from dataclasses import dataclass

from .base import ModelSpec, ProviderSpec

LLAMA_CPP_BUILD = "b11429"
LOCAL_PORT = 8765

PROVIDERS: list[ProviderSpec] = [
    ProviderSpec(
        id="local", label="Built-in (llama.cpp)", group="local", kind="openai",
        base_url=f"http://127.0.0.1:{LOCAL_PORT}/v1", login="none", json_mode="schema",
        models=[],  # filled from downloaded GGUF files
    ),
    ProviderSpec(
        id="ollama", label="Ollama", group="ollama", kind="openai",
        base_url="http://127.0.0.1:11434/v1", login="none", json_mode="schema",
        models=[],  # filled from the Ollama model list
    ),
    ProviderSpec(
        id="openrouter", label="OpenRouter", group="free", kind="openai",
        base_url="https://openrouter.ai/api/v1", login="pkce",
        key_url="https://openrouter.ai/settings/keys", rpm=18,
        extra_headers={"X-Title": "Divide Reader"},
        models=[
            ModelSpec("openrouter/free", "Free router (any free model)", free=True),
            ModelSpec("google/gemma-4-31b-it:free", "Gemma 4 31B (free)", free=True),
            # Paid models (Claude, OpenAI, Grok, ...) are loaded live from OpenRouter's model list.
        ],
    ),
    ProviderSpec(
        id="gemini", label="Google Gemini", group="free", kind="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai", login="key",
        key_url="https://aistudio.google.com/apikey", rpm=10,
        models=[ModelSpec("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite (free tier)", free=True)],
    ),
    ProviderSpec(
        id="groq", label="Groq", group="free", kind="openai",
        base_url="https://api.groq.com/openai/v1", login="key",
        key_url="https://console.groq.com/keys", rpm=25, json_mode="object",
        models=[
            ModelSpec("openai/gpt-oss-20b", "GPT-OSS 20B (free tier)", free=True),
            ModelSpec("llama-3.1-8b-instant", "Llama 3.1 8B Instant (free tier)", free=True),
        ],
    ),
    ProviderSpec(
        id="mistral", label="Mistral", group="free", kind="openai",
        base_url="https://api.mistral.ai/v1", login="key",
        key_url="https://console.mistral.ai/api-keys", rpm=50,
        models=[ModelSpec("mistral-small-latest", "Mistral Small (free plan)", free=True)],
    ),
    ProviderSpec(
        id="claude", label="Claude (Anthropic)", group="paid", kind="anthropic",
        base_url="https://api.anthropic.com", login="key",
        key_url="https://platform.claude.com/settings/keys",
        models=[
            ModelSpec("claude-opus-5-5", "Claude Opus 5.5", 4.00, 20.00),
            ModelSpec("claude-sonnet-5-5", "Claude Sonnet 5.5", 2.00, 10.00),
            ModelSpec("claude-haiku-4-5", "Claude Haiku 4.5", 1.00, 5.00),
        ],
    ),
    ProviderSpec(
        id="openai", label="OpenAI", group="paid", kind="openai",
        base_url="https://api.openai.com/v1", login="key",
        key_url="https://platform.openai.com/api-keys",
        models=[ModelSpec("gpt-6-luna", "GPT-6 Luna", 0.10, 0.50)],
    ),
    ProviderSpec(
        id="xai", label="Grok (xAI)", group="paid", kind="openai",
        base_url="https://api.x.ai/v1", login="key",
        key_url="https://console.x.ai/team/default/api-keys",
        models=[ModelSpec("grok-4.3", "Grok 4.3", 1.25, 2.50)],
    ),
]

GROUP_LABELS = {
    "local": "Built-in local model",
    "ollama": "Ollama",
    "free": "Free online",
    "paid": "Paid online",
}


def provider(pid: str) -> ProviderSpec:
    for p in PROVIDERS:
        if p.id == pid:
            return p
    raise KeyError(pid)


@dataclass(frozen=True)
class LocalModel:
    id: str
    label: str
    page: str
    url: str
    size: int          # bytes
    sha256: str
    min_ram_gb: int    # recommended RAM
    licence: str
    server_args: tuple[str, ...] = ()

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[1]


LOCAL_MODELS: list[LocalModel] = [
    LocalModel(
        "gemma-4-e2b", "Gemma 4 E2B (small, ~4 GB RAM)",
        "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF",
        "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf",
        3106738272, "740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8", 4, "Apache-2.0"),
    LocalModel(
        "gemma-4-e4b", "Gemma 4 E4B (medium, ~8 GB RAM)",
        "https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF",
        "https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/resolve/main/gemma-4-E4B-it-Q4_K_M.gguf",
        4977171584, "85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87", 8, "Apache-2.0"),
    LocalModel(
        "gemma-4-12b", "Gemma 4 12B (large, ~16 GB RAM)",
        "https://huggingface.co/unsloth/gemma-4-12b-it-GGUF",
        "https://huggingface.co/unsloth/gemma-4-12b-it-GGUF/resolve/main/gemma-4-12b-it-Q4_K_M.gguf",
        7121861440, "0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42", 16, "Apache-2.0"),
    LocalModel(
        "qwen3.5-4b", "Qwen3.5 4B (small, ~4 GB RAM)",
        "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF",
        "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf",
        2740937888, "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4", 4, "Apache-2.0",
        ("--reasoning", "off")),
    LocalModel(
        "qwen3.5-9b", "Qwen3.5 9B (medium-large, ~10 GB RAM)",
        "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF",
        "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf",
        5680522464, "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8", 10, "Apache-2.0",
        ("--reasoning", "off")),
]


def recommend_local(ram_gb: float) -> LocalModel:
    """Largest Gemma that fits comfortably in this machine's RAM."""
    fits = [m for m in LOCAL_MODELS if m.id.startswith("gemma") and m.min_ram_gb <= ram_gb]
    return fits[-1] if fits else LOCAL_MODELS[0]


def local_model(mid: str) -> LocalModel:
    for m in LOCAL_MODELS:
        if m.id == mid:
            return m
    raise KeyError(mid)
