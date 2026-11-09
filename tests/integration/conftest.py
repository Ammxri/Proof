"""A local stub of an OpenAI-compatible chat endpoint with Ollama's version and model list (KONZEPT §9).

The stub records every request (path, headers, body) and answers according to ``mode``:

- ``valid``: a valid answer JSON as text;
- ``invalid``: plain text that is no JSON;
- ``error``: HTTP 500 with a body that echoes the Authorization header (to check redaction);
- ``redirect``: HTTP 302 to another host;
- ``empty``: a reply without choices.

``fail_first`` makes the first n chat requests answer with HTTP 500, whatever the mode.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

ANSWER = {
    "decision": "answer",
    "ddx": ["ddx.alpha"],
    "questions": [],
    "red_flags": [],
    "contradictions": [],
    "rationale": "stub",
}
DIGEST = "d" * 64


@dataclass
class StubState:
    mode: str = "valid"
    fail_first: int = 0
    requests: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def chat_requests(self) -> list[dict[str, Any]]:
        return [request for request in self.requests if request["path"].endswith("/chat/completions")]


class _Handler(BaseHTTPRequestHandler):
    state: StubState

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        with self.state.lock:
            self.state.requests.append({"path": self.path, "headers": dict(self.headers), "body": None})
        if self.path == "/api/version":
            self._send(200, {"version": "0.0.0-stub"})
        elif self.path == "/api/tags":
            details = {"parameter_size": "1B", "quantization_level": "Q4_K_M"}
            self._send(200, {"models": [{"name": "stub-model:latest", "digest": DIGEST, "details": details}]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        with self.state.lock:
            self.state.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
            number = len(self.state.chat_requests())
        if not self.path.endswith("/chat/completions"):
            self._send(404, {"error": "not found"})
            return
        mode = "error" if number <= self.state.fail_first else self.state.mode
        if mode == "error":
            self._send(500, {"error": f"stub failure, header was {self.headers.get('Authorization')}"})
        elif mode == "redirect":
            self._send(302, {"error": "moved"}, {"Location": "https://example.org/v1/chat/completions"})
        elif mode == "empty":
            self._send(200, {"choices": []})
        else:
            text = json.dumps(ANSWER) if mode == "valid" else "Here is my answer: pneumonia."
            prompt_tokens = sum(len(message["content"]) for message in body["messages"]) // 4
            self._send(
                200,
                {
                    "model": "stub-model",
                    "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 20},
                },
            )


@pytest.fixture
def stub():
    """A running stub server: yields (base URL with /v1, state)."""
    state = StubState()
    handler = type("Handler", (_Handler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
