import json

import httpx
import pytest

from divide_reader.providers.base import LLMError, ModelSpec, RateLimited, validate
from divide_reader.providers.catalog import provider
from divide_reader.providers.openai_compat import OpenAICompat
from divide_reader.providers.anthropic_provider import _strict
from divide_reader import prompts

SCHEMA = prompts.FIGURES_SCHEMA


def make(handler, pid="local", key=None):
    p = OpenAICompat(provider(pid), ModelSpec("m", "m", 1.0, 2.0), key, base_url="http://x/v1")
    p.client = httpx.Client(transport=httpx.MockTransport(handler))
    return p


def ok(content, usage=None):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": usage or {"prompt_tokens": 1000, "completion_tokens": 500}})


def test_schema_request_and_cost():
    seen = {}

    def h(req):
        seen.update(json.loads(req.content))
        return ok('{"figures": ["a"]}')
    res = make(h).chat_json("sys", "user", SCHEMA, "figures")
    assert seen["response_format"]["type"] == "json_schema"
    assert seen["response_format"]["json_schema"]["schema"] == SCHEMA
    assert res.data == {"figures": ["a"]}
    assert res.usage.cost_usd == pytest.approx((1000 * 1 + 500 * 2) / 1e6)


def test_object_mode_puts_schema_in_prompt():
    seen = {}

    def h(req):
        seen.update(json.loads(req.content))
        return ok('```json\n{"figures": []}\n```')
    p = make(h, "groq", key="k")
    p.chat_json("sys", "user", SCHEMA, "figures")
    assert seen["response_format"] == {"type": "json_object"}
    assert "JSON schema" in seen["messages"][0]["content"]


def test_invalid_json_retries_then_fails():
    calls = []

    def h(req):
        calls.append(1)
        return ok('{"wrong": 1}')
    with pytest.raises(LLMError):
        make(h).chat_json("s", "u", SCHEMA, "figures", retries=2)
    assert len(calls) == 3


def test_auth_error_and_rate_limit():
    with pytest.raises(LLMError, match="login"):
        make(lambda r: httpx.Response(401), "groq", "k").chat_json("s", "u", SCHEMA, "f")
    with pytest.raises(RateLimited):
        make(lambda r: httpx.Response(429, headers={"retry-after": "3600"}), "groq", "k").chat_json("s", "u", SCHEMA, "f")


def test_validate():
    validate({"figures": ["a"]}, SCHEMA)
    with pytest.raises(ValueError):
        validate({"figures": [1]}, SCHEMA)
    validate({"judgements": [], "assumed_readings": [], "other_counts": [{"what": "t", "amount": None, "anchor": ""}]},
             prompts.ENUMERATE_SCHEMA)


def test_strict_schema_for_claude():
    s = _strict(prompts.ENUMERATE_SCHEMA)
    assert s["additionalProperties"] is False
    assert s["properties"]["judgements"]["items"]["additionalProperties"] is False
    assert "maxItems" not in json.dumps(s)


def test_claude_request_shape():
    import anthropic
    import httpx2
    from divide_reader.providers.anthropic_provider import AnthropicProvider
    seen = {}

    def h(req):
        seen["h"], seen["b"] = dict(req.headers), json.loads(req.content)
        return httpx2.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": '{"figures": ["a"]}'}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5}})
    spec = provider("claude")
    p = AnthropicProvider(spec, spec.models[0], "x")
    p.client = anthropic.Anthropic(api_key="x", http_client=httpx2.Client(transport=httpx2.MockTransport(h)))
    r = p.chat_json("s", "u", SCHEMA, "figures")
    assert r.data == {"figures": ["a"]}
    assert seen["b"]["output_config"]["format"]["type"] == "json_schema"
    assert seen["b"]["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in seen["h"]["anthropic-beta"]
    assert "temperature" not in seen["b"]
