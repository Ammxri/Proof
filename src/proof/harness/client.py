"""Chat client (PR-F07, PR-N05, KONZEPT 5.2, D-12) and the request hash for the cache (A-19).

- Two protocols: OpenAI-compatible chat completions, and Ollama's own ``/api/chat`` on this computer (D-12).
- Every request carries temperature 0 and the provider's allowed parameters; no JSON mode, no streaming (A-38).
- There is no second attempt: a network error, a status other than 200 or a reply without text is recorded as an
  error of that unit (A-36). Redirects are not followed, TLS verification stays on, and requests go only to the
  provider's endpoint (and, for Ollama, its version and model list on the same host).
- The API key is sent in the ``Authorization`` header and nowhere else; any text that is stored has the key removed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

import proof
from proof.core import canonical
from proof.core.hashing import sha256_bytes
from proof.harness.providers import TEMPERATURE, Provider

Message = dict[str, str]
ERROR_TEXT_LIMIT = 500


def request_body(provider: Provider, messages: Sequence[Message]) -> dict[str, Any]:
    """The JSON body of a chat request: model, messages, temperature 0, the provider's parameters, no streaming.

    Ollama's own API takes sampling settings under ``options`` (``num_predict`` is its token limit) and the thinking
    switch ``think`` at the top level.
    """
    fields = provider.params.request_fields()
    base = {"model": provider.model, "messages": [dict(message) for message in messages], "stream": False}
    if provider.api == "ollama_chat":
        options = {"temperature": TEMPERATURE}
        names = {"max_tokens": "num_predict", "seed": "seed", "top_p": "top_p"}
        options.update({names[key]: value for key, value in fields.items() if key in names})
        think = {"think": fields["think"]} if "think" in fields else {}
        return {**base, **think, "options": options}
    return {**base, "temperature": TEMPERATURE, **fields}


def request_hash(provider: Provider, messages: Sequence[Message]) -> str:
    """Cache key of a request (A-19): SHA-256 of base URL, model, parameters and messages; never the API key."""
    return sha256_bytes(
        canonical.dumps_bytes({"base_url": provider.base_url, "body": request_body(provider, messages)})
    )


@dataclass(frozen=True)
class Reply:
    """What came back for one request."""

    status: Literal["ok", "error"]
    text: str | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "text": self.text,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "finish_reason": self.finish_reason,
            "error": self.error,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Reply:
        return cls(**{name: data.get(name) for name in cls.__dataclass_fields__})


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def parse_ollama_reply(data: Any) -> Reply:
    """Read Ollama's ``/api/chat`` reply: the answer is ``message.content``; thinking, if any, is not part of it."""
    message = data.get("message") if isinstance(data, dict) else None
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str):
        return Reply(status="error", error="the reply has no message.content")
    model = data.get("model")
    finish = data.get("done_reason")
    return Reply(
        status="ok",
        text=text,
        model=model if isinstance(model, str) else None,
        prompt_tokens=_count(data.get("prompt_eval_count")),
        completion_tokens=_count(data.get("eval_count")),
        finish_reason=finish if isinstance(finish, str) else None,
    )


def parse_reply(data: Any) -> Reply:
    """Read the text, model, token counts and finish reason of a chat completion; anything else is an error."""
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return Reply(status="error", error="the reply has no choices[0].message.content")
    if not isinstance(text, str):
        return Reply(status="error", error="the reply's content is not text")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    model = data.get("model")
    finish = choice.get("finish_reason") if isinstance(choice, dict) else None
    return Reply(
        status="ok",
        text=text,
        model=model if isinstance(model, str) else None,
        prompt_tokens=_count(usage.get("prompt_tokens")),
        completion_tokens=_count(usage.get("completion_tokens")),
        finish_reason=finish if isinstance(finish, str) else None,
    )


@dataclass
class Client:
    """One provider's endpoint; use as a context manager."""

    provider: Provider
    api_key: str | None = None
    transport: httpx.BaseTransport | None = None
    requests_sent: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        headers = {"Content-Type": "application/json", "User-Agent": f"proof/{proof.__version__}"}
        if self.api_key is not None:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self._http = httpx.Client(
            headers=headers,
            timeout=httpx.Timeout(float(self.provider.timeout_seconds)),
            follow_redirects=False,
            verify=True,
            trust_env=not self.provider.local,
            transport=self.transport,
        )

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _redact(self, text: str) -> str:
        return text.replace(self.api_key, "***") if self.api_key else text

    def chat(self, messages: Sequence[Message]) -> Reply:
        """Send one request; never retries."""
        body = canonical.dumps_bytes(request_body(self.provider, messages))
        self.requests_sent += 1
        try:
            response = self._http.post(self.provider.endpoint, content=body)
        except httpx.HTTPError as exc:
            return Reply(status="error", error=self._redact(f"{type(exc).__name__}: {exc}")[:ERROR_TEXT_LIMIT])
        if response.status_code != 200:
            detail = self._redact(response.text)[:ERROR_TEXT_LIMIT]
            return Reply(status="error", error=f"HTTP {response.status_code}: {detail}")
        try:
            data = json.loads(response.text)
        except ValueError:
            return Reply(status="error", error="the reply is not JSON")
        reply = parse_ollama_reply(data) if self.provider.api == "ollama_chat" else parse_reply(data)
        return reply if reply.text is None else Reply(**{**reply.to_json(), "text": self._redact(reply.text)})

    def ollama_info(self) -> dict[str, Any]:
        """Ollama version, the model's digest and details from ``/api/version`` and ``/api/tags`` (A-21)."""
        root = self.provider.host_root
        try:
            version = self._http.get(f"{root}/api/version").json().get("version")
            models = self._http.get(f"{root}/api/tags").json().get("models", [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            return {"error": f"{type(exc).__name__}: {exc}"[:ERROR_TEXT_LIMIT]}
        wanted = {self.provider.model, f"{self.provider.model}:latest"}
        for entry in models if isinstance(models, list) else []:
            if isinstance(entry, dict) and entry.get("name") in wanted:
                return {"version": version, "digest": entry.get("digest"), "details": entry.get("details")}
        return {"version": version, "error": f"model {self.provider.model} is not in Ollama's model list"}
