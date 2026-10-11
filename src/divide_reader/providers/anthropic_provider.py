"""Claude through the official Anthropic SDK, with structured JSON output."""
from __future__ import annotations

import json
import time

import anthropic

from .base import LLMError, ModelSpec, Provider, ProviderSpec, RateLimited, Result, Usage, price_cost

# Models that accept the server-side refusal fallback ("default" routing).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}


class AnthropicProvider(Provider):
    def __init__(self, spec: ProviderSpec, model: ModelSpec, api_key: str):
        self.spec = spec
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=4)

    def _call(self, system: str, user: str, schema: dict, name: str, max_tokens: int) -> Result:
        schema = _strict(schema)
        kwargs = dict(
            model=self.model.id,
            max_tokens=max(max_tokens, 16000),
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        try:
            if self.model.id in FALLBACK_MODELS:
                resp = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"],
                    extra_body={"fallbacks": "default"},
                    **kwargs,
                )
            else:
                resp = self.client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise LLMError("Claude: login rejected. Log in again.") from e
        except anthropic.RateLimitError as e:
            raise RateLimited(time.time() + 60, "Claude: rate limited") from e
        except anthropic.BadRequestError as e:
            raise LLMError(f"Claude: {e}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"Claude: cannot connect: {e}") from e
        if resp.stop_reason == "refusal":
            raise LLMError("Claude declined this request")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        usage = Usage(in_tokens=resp.usage.input_tokens, out_tokens=resp.usage.output_tokens)
        usage.cost_usd = price_cost(self.model, usage)
        return Result(data=json.loads(text), usage=usage, model=f"{self.spec.id}:{resp.model}", raw=text)


def _strict(schema: dict) -> dict:
    """Structured outputs need additionalProperties: false on every object; size bounds are dropped."""
    s = {k: v for k, v in schema.items() if k not in ("maxItems", "maxLength", "minimum", "maximum")}
    if s.get("type") == "object":
        s["additionalProperties"] = False
        s["properties"] = {k: _strict(v) for k, v in s.get("properties", {}).items()}
    if "items" in s:
        s["items"] = _strict(s["items"])
    return s
