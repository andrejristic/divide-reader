"""Common interface for every model: bundled llama.cpp, Ollama, and online providers."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field


class LLMError(Exception):
    """A call failed in a way retrying will not fix."""


class RateLimited(Exception):
    """The provider asked us to wait longer than we are willing to block."""

    def __init__(self, retry_at: float, message: str = ""):
        super().__init__(message or f"rate limited until {time.ctime(retry_at)}")
        self.retry_at = retry_at


class BudgetExceeded(Exception):
    """The job reached its cost cap."""


@dataclass
class ModelSpec:
    id: str
    label: str
    price_in: float | None = None    # USD per 1M input tokens; None = unknown
    price_out: float | None = None   # USD per 1M output tokens
    free: bool = False


@dataclass
class ProviderSpec:
    id: str
    label: str
    group: str                       # local | ollama | free | paid
    kind: str                        # openai | anthropic
    base_url: str
    login: str                       # none | key | pkce
    key_url: str | None = None       # page where a key is created (opened in browser)
    models: list[ModelSpec] = field(default_factory=list)
    json_mode: str = "schema"        # schema | object (what response_format the API accepts)
    rpm: int | None = None           # requests per minute we keep under
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Usage:
    in_tokens: int = 0
    out_tokens: int = 0
    cost_usd: float | None = None    # None when the provider did not report and the price is unknown


@dataclass
class Result:
    data: dict
    usage: Usage
    model: str
    raw: str


class Throttle:
    """Keeps a provider under its requests-per-minute limit."""

    def __init__(self, rpm: int | None):
        self.interval = 60.0 / rpm if rpm else 0.0
        self.next_at = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        if not self.interval:
            return
        with self.lock:
            now = time.monotonic()
            delay = self.next_at - now
            self.next_at = max(now, self.next_at) + self.interval
        if delay > 0:
            time.sleep(delay)


def price_cost(model: ModelSpec | None, usage: Usage) -> float | None:
    if usage.cost_usd is not None:
        return usage.cost_usd
    if model is None or model.free:
        return 0.0 if model is not None and model.free else None
    if model.price_in is None or model.price_out is None:
        return None
    return (usage.in_tokens * model.price_in + usage.out_tokens * model.price_out) / 1_000_000


def validate(data, schema: dict, path: str = "$") -> None:
    """Minimal JSON-schema check for the shapes this program uses.

    Supports type (object/array/string/integer/number/boolean/null and lists of
    types), properties, required, items, enum, minimum, maximum.
    """
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        ok = False
        for ty in types:
            if ty == "object" and isinstance(data, dict):
                ok = True
            elif ty == "array" and isinstance(data, list):
                ok = True
            elif ty == "string" and isinstance(data, str):
                ok = True
            elif ty == "integer" and isinstance(data, int) and not isinstance(data, bool):
                ok = True
            elif ty == "number" and isinstance(data, (int, float)) and not isinstance(data, bool):
                ok = True
            elif ty == "boolean" and isinstance(data, bool):
                ok = True
            elif ty == "null" and data is None:
                ok = True
        if not ok:
            raise ValueError(f"{path}: expected {t}, got {type(data).__name__}")
    if "enum" in schema and data not in schema["enum"]:
        raise ValueError(f"{path}: {data!r} not in {schema['enum']}")
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            raise ValueError(f"{path}: below minimum")
        if "maximum" in schema and data > schema["maximum"]:
            raise ValueError(f"{path}: above maximum")
    if isinstance(data, dict):
        for req in schema.get("required", []):
            if req not in data:
                raise ValueError(f"{path}: missing '{req}'")
        for k, sub in schema.get("properties", {}).items():
            if k in data:
                validate(data[k], sub, f"{path}.{k}")
    if isinstance(data, list) and "items" in schema:
        for i, item in enumerate(data):
            validate(item, schema["items"], f"{path}[{i}]")


def parse_json(text: str) -> dict:
    """Parse a JSON object, tolerating code fences and leading prose."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


class Provider:
    """One configured connection: a provider, a model, and an in-memory key."""

    spec: ProviderSpec
    model: ModelSpec

    def chat_json(self, system: str, user: str, schema: dict, name: str,
                  max_tokens: int = 4000, retries: int = 2) -> Result:
        last: Exception | None = None
        for _ in range(retries + 1):
            try:
                res = self._call(system, user, schema, name, max_tokens)
                validate(res.data, schema)
                return res
            except (ValueError, json.JSONDecodeError) as e:
                last = e
        raise LLMError(f"model did not return valid JSON after {retries + 1} tries: {last}")

    def _call(self, system: str, user: str, schema: dict, name: str, max_tokens: int) -> Result:
        raise NotImplementedError

    @property
    def label(self) -> str:
        return f"{self.spec.id}:{self.model.id}"
