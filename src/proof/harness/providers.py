"""Provider configuration (PR-F07, PR-C05, PR-N03, KONZEPT 4.9): one YAML file per model endpoint.

A provider names an OpenAI-compatible chat endpoint (API, Ollama or vLLM), the model, where the API key comes from
(the *name* of an environment variable, never the key), the origin of the model and the declared server region, the
request parameters and the prices. Rules that are checked when the file is loaded:

- **Temperature is fixed at 0** and cannot be set (PR-N05); neither JSON mode nor structured output can be switched on
  (A-38). Only the parameters listed in :class:`Params` are allowed.
- **Western models only via EU servers** (PR-N03): a provider of origin ``western`` must declare the region ``EU``.
  The region is a declaration; Proof cannot check it technically and records it in the run manifest (D-06).
- **TLS:** remote endpoints need ``https``; plain ``http`` is accepted only for this computer (localhost).
- **Placeholders** ``<PLATZHALTER: …>`` mark details the project lead still has to fill in; a provider that contains
  one is refused.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    ValidationError,
    model_validator,
)

from proof.core import yamlio
from proof_rules.model import Number

PLACEHOLDER = re.compile(r"<PLATZHALTER[^>]*>")
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
TEMPERATURE = 0
PRICE_NOT_GIVEN = "Preis nicht angegeben"


class ProviderError(Exception):
    """A provider file is invalid or cannot be used; ``problems`` lists every finding."""

    def __init__(self, problems: list[str] | tuple[str, ...]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Thinking(_Model):
    """Thinking switch of the DeepSeek API: ``{"type": "enabled" | "disabled"}``."""

    type: Literal["enabled", "disabled"]


class Params(_Model):
    """Request parameters a provider may set; temperature, JSON mode and streaming are not among them."""

    max_tokens: Annotated[StrictInt, Field(ge=1)] | None = None
    seed: StrictInt | None = None
    top_p: Number | None = None
    # Ollama's switch for thinking models; recorded in the manifest (RK-08).
    think: StrictBool | None = None
    # DeepSeek's switch for thinking models.
    thinking: Thinking | None = None
    reasoning_effort: Literal["low", "medium", "high"] | None = None

    def request_fields(self) -> dict[str, Any]:
        """The parameters as they go into the request body, without the ones left unset."""
        return self.model_dump(mode="json", exclude_none=True)


class Pricing(_Model):
    """Prices per million tokens (A-20); entered by the project lead, never invented."""

    input_per_mtok: Annotated[Number, Field(ge=0)]
    output_per_mtok: Annotated[Number, Field(ge=0)]
    currency: Annotated[StrictStr, StringConstraints(pattern=r"^[A-Z]{3}$")]


class Provider(_Model):
    """``providers/<name>.yaml``."""

    name: Annotated[StrictStr, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_.-]*$")]
    api: Literal["openai_chat"]
    base_url: StrictStr
    model: Annotated[StrictStr, StringConstraints(min_length=1)]
    api_key_env: Annotated[StrictStr, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]*$")] | None = None
    origin: Literal["cn", "western", "other"]
    region: Annotated[StrictStr, StringConstraints(pattern=r"^[A-Za-z]{2,10}$")]
    ollama_digest: StrictBool = False
    params: Params = Field(default_factory=Params)
    pricing: Pricing | None = None
    timeout_seconds: Annotated[Number, Field(gt=0, le=3600)] = 300

    @model_validator(mode="after")
    def _rules(self) -> Provider:
        if self.origin == "western" and self.region != "EU":
            raise ValueError(f"a western model runs only via EU servers (PR-N03); region is {self.region!r}, not 'EU'")
        parts = urlsplit(self.base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.query or parts.fragment:
            raise ValueError(f"base_url must be an http(s) URL without query, got {self.base_url!r}")
        if parts.scheme == "http" and parts.hostname not in LOCAL_HOSTS:
            raise ValueError("plain http is allowed only for this computer; remote endpoints need https")
        if self.ollama_digest and parts.hostname not in LOCAL_HOSTS:
            raise ValueError("an Ollama provider runs on this computer (localhost)")
        return self

    @property
    def local(self) -> bool:
        return urlsplit(self.base_url).hostname in LOCAL_HOSTS

    @property
    def endpoint(self) -> str:
        """URL of the chat completions endpoint."""
        return self.base_url.rstrip("/") + "/chat/completions"

    @property
    def host_root(self) -> str:
        """Scheme, host and port of the endpoint, e.g. for Ollama's own API (``/api/tags``)."""
        parts = urlsplit(self.base_url)
        return f"{parts.scheme}://{parts.netloc}"

    def public(self) -> dict[str, Any]:
        """The configuration as stored in a manifest: everything but secrets (there are none in the model)."""
        return self.model_dump(mode="json")


def placeholders(data: Any, path: str = "") -> list[str]:
    found = []
    if isinstance(data, str):
        found.extend(f"{path or '<root>'}: {match}" for match in PLACEHOLDER.findall(data))
    elif isinstance(data, Mapping):
        for key, value in data.items():
            found.extend(placeholders(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(data, list | tuple):
        for index, value in enumerate(data):
            found.extend(placeholders(value, f"{path}[{index}]"))
    return found


def parse_provider(data: Any, where: str) -> Provider:
    found = placeholders(data)
    if found:
        raise ProviderError([f"{where}: placeholder not filled in: {item}" for item in found])
    try:
        return Provider.model_validate(data)
    except ValidationError as exc:
        problems = []
        for error in exc.errors(include_url=False):
            location = ".".join(str(part) for part in error["loc"])
            message = error["msg"].removeprefix("Value error, ")
            problems.append(f"{where}: {location}: {message}" if location else f"{where}: {message}")
        raise ProviderError(problems) from exc


def load_provider(path: Path) -> Provider:
    """Read and check a provider file."""
    if not path.is_file():
        raise ProviderError([f"{path}: file is missing"])
    try:
        data = yamlio.load_file(path)
    except yamlio.YamlError as exc:
        raise ProviderError([str(exc)]) from exc
    return parse_provider(data, str(path))


def api_key(provider: Provider, environ: Mapping[str, str] | None = None) -> str | None:
    """The API key from the provider's environment variable; ``None`` for providers without key."""
    if provider.api_key_env is None:
        return None
    value = (os.environ if environ is None else environ).get(provider.api_key_env, "").strip()
    if not value:
        raise ProviderError([f"environment variable {provider.api_key_env} is not set (see .env.example)"])
    return value
