"""Provider configuration and client parts that need no server (PR-F07, PR-N03, PR-N05, A-19, A-38)."""

from __future__ import annotations

from pathlib import Path

import pytest

from proof.harness.cache import Cache
from proof.harness.client import Reply, parse_ollama_reply, parse_reply, request_body, request_hash
from proof.harness.providers import Provider, ProviderError, api_key, load_provider, parse_provider

BASE = {
    "name": "p",
    "api": "openai_chat",
    "base_url": "https://api.example.org/v1",
    "model": "m",
    "api_key_env": "EXAMPLE_KEY",
    "origin": "cn",
    "region": "CN",
}
MESSAGES = ({"role": "system", "content": "S"}, {"role": "user", "content": "C"})


def _problems(data) -> str:
    with pytest.raises(ProviderError) as caught:
        parse_provider(data, "p.yaml")
    return "\n".join(caught.value.problems)


def test_the_shipped_providers(repo_root):
    qwen = load_provider(repo_root / "providers/qwen-local.yaml")
    assert (qwen.local, qwen.ollama_digest, qwen.api_key_env, qwen.origin) == (True, True, None, "cn")
    assert (qwen.api, qwen.endpoint) == ("ollama_chat", "http://127.0.0.1:11434/api/chat")
    assert qwen.host_root == "http://127.0.0.1:11434"
    assert qwen.params.think is False
    deepseek = load_provider(repo_root / "providers/deepseek.yaml")
    assert deepseek.endpoint == "https://api.deepseek.com/chat/completions"
    assert deepseek.pricing is None and deepseek.api_key_env == "DEEPSEEK_API_KEY"
    assert deepseek.params.request_fields() == {"max_tokens": 1024, "thinking": {"type": "disabled"}}
    assert "placeholder not filled in: base_url" in _problems_file(repo_root / "providers/western-eu.yaml")


def _problems_file(path: Path) -> str:
    with pytest.raises(ProviderError) as caught:
        load_provider(path)
    return "\n".join(caught.value.problems)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"origin": "western"}, "only via EU servers (PR-N03)"),
        ({"base_url": "http://api.example.org/v1"}, "plain http is allowed only for this computer"),
        ({"base_url": "ftp://api.example.org"}, "must be an http(s) URL"),
        ({"base_url": "https://api.example.org/v1?x=1"}, "must be an http(s) URL"),
        ({"ollama_digest": True}, "an Ollama provider runs on this computer"),
        ({"params": {"temperature": 0.7}}, "Extra inputs are not permitted"),
        ({"params": {"response_format": {"type": "json_object"}}}, "Extra inputs are not permitted"),
        ({"params": {"stream": True}}, "Extra inputs are not permitted"),
        ({"params": {"max_tokens": 0}}, "greater than or equal to 1"),
        ({"api_key_env": "lower"}, "String should match pattern"),
        ({"api": "anthropic"}, "Input should be 'openai_chat' or 'ollama_chat'"),
        ({"pricing": {"input_per_mtok": -1, "output_per_mtok": 1, "currency": "EUR"}}, "greater than or equal to 0"),
        ({"model": "<PLATZHALTER: Modell>"}, "placeholder not filled in: model"),
        ({"extra": 1}, "Extra inputs are not permitted"),
        ({"params": {"think": False}}, "think is Ollama's switch and needs api ollama_chat"),
        ({"api": "ollama_chat"}, "an Ollama provider runs on this computer"),
        ({"api": "ollama_chat", "base_url": "http://127.0.0.1:11434/v1"}, "is the Ollama server itself"),
        (
            {"api": "ollama_chat", "base_url": "http://127.0.0.1:11434", "params": {"thinking": {"type": "disabled"}}},
            "thinking and reasoning_effort belong to other APIs",
        ),
    ],
)
def test_invalid_providers_are_refused(changes, message):
    assert message in _problems({**BASE, **changes})


def test_western_with_eu_and_local_http_are_accepted():
    western = Provider.model_validate({**BASE, "origin": "western", "region": "EU"})
    assert western.region == "EU" and not western.local
    local = Provider.model_validate({**BASE, "base_url": "http://localhost:8000/v1", "api_key_env": None})
    assert local.local and local.public()["base_url"] == "http://localhost:8000/v1"


def test_provider_files(tmp_path):
    assert "file is missing" in _problems_file(tmp_path / "none.yaml")
    path = tmp_path / "p.yaml"
    path.write_text("name: [", encoding="utf-8")
    assert "p.yaml" in _problems_file(path)


def test_api_keys_come_from_the_environment():
    provider = Provider.model_validate(BASE)
    assert api_key(provider, {"EXAMPLE_KEY": " secret "}) == "secret"
    with pytest.raises(ProviderError, match="EXAMPLE_KEY is not set"):
        api_key(provider, {"EXAMPLE_KEY": ""})
    assert api_key(Provider.model_validate({**BASE, "api_key_env": None}), {}) is None


def test_requests_have_temperature_zero_and_a_hash_without_key():
    """PR-N05, A-38, A-19."""
    provider = Provider.model_validate({**BASE, "params": {"max_tokens": 10, "seed": 3}})
    body = request_body(provider, MESSAGES)
    assert body == {
        "model": "m",
        "messages": [dict(message) for message in MESSAGES],
        "temperature": 0,
        "stream": False,
        "max_tokens": 10,
        "seed": 3,
    }
    digest = request_hash(provider, MESSAGES)
    assert digest == request_hash(provider, list(MESSAGES))
    other_key = Provider.model_validate({**BASE, "api_key_env": "OTHER_KEY", "params": provider.params.model_dump()})
    assert request_hash(other_key, MESSAGES) == digest, "the key's variable is not part of the hash"
    assert request_hash(Provider.model_validate({**BASE, "model": "n"}), MESSAGES) != digest
    assert request_hash(provider, (MESSAGES[0], {"role": "user", "content": "D"})) != digest


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (
            {"model": "m", "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
            Reply(status="ok", text="{}", model="m", prompt_tokens=5, completion_tokens=2, finish_reason="stop"),
        ),
        (
            {"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": -1, "completion_tokens": True}},
            Reply(status="ok", text="x"),
        ),
        ({"choices": [{"message": {"content": None}}]}, Reply(status="error", error="the reply's content is not text")),
        ({"choices": []}, Reply(status="error", error="the reply has no choices[0].message.content")),
        ([], Reply(status="error", error="the reply has no choices[0].message.content")),
    ],
)  # fmt: skip
def test_replies_are_read_strictly(data, expected):
    assert parse_reply(data) == expected


def test_the_cache_keeps_only_answers(tmp_path):
    cache = Cache(tmp_path)
    digest = "a" * 64
    assert cache.get(digest) is None
    cache.put(digest, Reply(status="error", error="x"))
    assert cache.get(digest) is None
    reply = Reply(status="ok", text="t", model="m", prompt_tokens=1, completion_tokens=2, finish_reason="stop")
    cache.put(digest, reply)
    assert cache.get(digest) == reply
    assert cache.path(digest) == tmp_path / "aa" / f"{digest}.json"
    cache.path(digest).write_text('{"request_hash": "other"}', encoding="utf-8")
    assert cache.get(digest) is None
    cache.path(digest).write_text("{", encoding="utf-8")
    assert cache.get(digest) is None
    with pytest.raises(ValueError, match="not a request hash"):
        cache.path("../x")


def test_ollama_requests_put_sampling_settings_into_options():
    """D-12: Ollama's own API; temperature 0 under options, thinking switched off at the top level."""
    provider = Provider.model_validate(
        {
            **BASE,
            "api": "ollama_chat",
            "base_url": "http://127.0.0.1:11434",
            "api_key_env": None,
            "params": {"max_tokens": 10, "seed": 3, "top_p": 0.5, "think": False},
        }
    )
    assert provider.endpoint == "http://127.0.0.1:11434/api/chat"
    assert request_body(provider, MESSAGES) == {
        "model": "m",
        "messages": [dict(message) for message in MESSAGES],
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 10, "seed": 3, "top_p": 0.5},
    }
    plain = Provider.model_validate({**BASE, "api": "ollama_chat", "base_url": "http://localhost:11434/"})
    assert request_body(plain, MESSAGES)["options"] == {"temperature": 0}
    assert "think" not in request_body(plain, MESSAGES)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (
            {"model": "q", "message": {"content": "{}", "thinking": "hm"}, "done_reason": "stop",
             "prompt_eval_count": 7, "eval_count": 3},
            Reply(status="ok", text="{}", model="q", prompt_tokens=7, completion_tokens=3, finish_reason="stop"),
        ),
        ({"message": {"content": 1}}, Reply(status="error", error="the reply has no message.content")),
        ([], Reply(status="error", error="the reply has no message.content")),
    ],
)  # fmt: skip
def test_ollama_replies_keep_only_the_answer(data, expected):
    assert parse_ollama_reply(data) == expected
