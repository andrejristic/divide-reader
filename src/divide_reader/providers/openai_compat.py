"""OpenAI-compatible chat API: llama-server, Ollama, Gemini, Groq, Mistral, OpenAI, xAI, OpenRouter."""
from __future__ import annotations

import json
import random
import time

import httpx

from .base import (LLMError, ModelSpec, Provider, ProviderSpec, RateLimited, Result, Throttle,
                   Truncated, Usage, parse_json, price_cost)

MAX_BLOCKING_WAIT = 120.0  # seconds; longer waits pause the job instead


class OpenAICompat(Provider):
    def __init__(self, spec: ProviderSpec, model: ModelSpec, api_key: str | None,
                 base_url: str | None = None, timeout: float | None = None):
        self.spec = spec
        self.model = model
        self.api_key = api_key
        self.base_url = (base_url or spec.base_url).rstrip("/")
        self.throttle = Throttle(spec.rpm)
        if timeout is None:
            # Local models on a CPU can need many minutes for one long answer.
            timeout = 3600.0 if spec.group in ("local", "ollama") else 600.0
        self.timeout = timeout
        self.client = httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0))

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", **self.spec.extra_headers}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _body(self, system: str, user: str, schema: dict, name: str, max_tokens: int) -> dict:
        body: dict = {
            "model": self.model.id,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        if self.spec.json_mode == "schema":
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": name, "schema": schema, "strict": False}}
        else:
            body["response_format"] = {"type": "json_object"}
            body["messages"][0]["content"] += ("\n\nReply with one JSON object only, matching this JSON schema:\n"
                                               + json.dumps(schema, ensure_ascii=False))
        if self.spec.id == "openrouter":
            body["usage"] = {"include": True}
        return body

    def _call(self, system: str, user: str, schema: dict, name: str, max_tokens: int) -> Result:
        body = self._body(system, user, schema, name, max_tokens)
        attempt = 0
        while True:
            self.throttle.wait()
            try:
                r = self.client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body)
            except httpx.ReadTimeout as e:
                raise LLMError(f"{self.spec.label}: no answer within {self.timeout / 60:.0f} min "
                               "(model too slow for this unit)") from e
            except httpx.TransportError as e:
                attempt += 1
                if attempt > 4:
                    raise LLMError(f"cannot reach {self.base_url}: {e}") from e
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                attempt += 1
                wait = _retry_after(r) or min(60.0, 2 ** attempt + random.random())
                if wait > MAX_BLOCKING_WAIT or attempt > 6:
                    raise RateLimited(time.time() + max(wait, 60.0), f"{self.spec.label}: HTTP {r.status_code}")
                time.sleep(wait)
                continue
            if r.status_code in (401, 403):
                raise LLMError(f"{self.spec.label}: login rejected (HTTP {r.status_code}). Log in again.")
            if r.status_code >= 400:
                raise LLMError(f"{self.spec.label}: HTTP {r.status_code}: {r.text[:500]}")
            break
        payload = r.json()
        try:
            choice = payload["choices"][0]
            text = choice["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise LLMError(f"unexpected response: {str(payload)[:500]}") from e
        if choice.get("finish_reason") == "length":
            raise Truncated(f"answer cut off at {max_tokens} tokens")
        u = payload.get("usage") or {}
        usage = Usage(in_tokens=u.get("prompt_tokens", 0), out_tokens=u.get("completion_tokens", 0),
                      cost_usd=u.get("cost"))
        usage.cost_usd = price_cost(self.model, usage)
        return Result(data=parse_json(text), usage=usage, model=self.label, raw=text)

    def list_models(self) -> list[str]:
        r = self.client.get(f"{self.base_url}/models", headers=self._headers())
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]


def _retry_after(r: httpx.Response) -> float | None:
    v = r.headers.get("retry-after")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None
