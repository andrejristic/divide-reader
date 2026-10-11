"""Build a Provider from the start-screen choice."""
from __future__ import annotations

from .base import ModelSpec, Provider, ProviderSpec


def make(spec: ProviderSpec, model: ModelSpec, api_key: str | None = None,
         base_url: str | None = None) -> Provider:
    if spec.kind == "anthropic":
        from .anthropic_provider import AnthropicProvider
        if not api_key:
            raise ValueError("Claude needs a key; log in first")
        return AnthropicProvider(spec, model, api_key)
    from .openai_compat import OpenAICompat
    if spec.login != "none" and not api_key:
        raise ValueError(f"{spec.label} needs a login first")
    return OpenAICompat(spec, model, api_key, base_url=base_url)
