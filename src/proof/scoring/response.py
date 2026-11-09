"""Answer protocol (PR-P01) and the strict validity check behind S7 (A-13).

A model answers with one JSON object with exactly six keys: ``decision``, ``ddx``, ``questions``, ``red_flags``,
``contradictions`` and ``rationale``. An answer is valid only if the whole text, without whitespace at its edges, is
such an object and every list holds only codes the domain allows. A Markdown code block, text around the object,
duplicate keys or an unknown code make the answer invalid; there is no repair and no second attempt (PR-N05).

The JSON Schema in ``schema/response.schema.json`` is generated from :class:`Response`. It checks the form; which codes
are allowed depends on the domain and is checked by :func:`parse_response`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError

from proof.core import canonical
from proof_rules.model import DdxCode, Domain, FieldCode, RedFlagCode

Decision = Literal["answer", "ask", "refer_urgent"]


class Response(BaseModel):
    """A model's answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Decision
    ddx: tuple[DdxCode, ...]
    questions: tuple[FieldCode, ...]
    red_flags: tuple[RedFlagCode, ...]
    contradictions: tuple[FieldCode, ...]
    rationale: StrictStr


@dataclass(frozen=True)
class AllowedCodes:
    """The codes an answer of one domain may use (KONZEPT 4.2)."""

    ddx: frozenset[str]
    red_flags: frozenset[str]
    fields: frozenset[str]

    @classmethod
    def of(cls, domain: Domain) -> AllowedCodes:
        return cls(
            ddx=frozenset(term.code for term in domain.vocabulary.ddx),
            red_flags=frozenset(term.code for term in domain.vocabulary.red_flags),
            fields=frozenset(domain.catalog.codes()),
        )


@dataclass(frozen=True)
class Parsed:
    """Result of :func:`parse_response`: the answer if valid, otherwise ``None`` and the reasons."""

    response: Response | None
    problems: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.response is not None


def _strict_types(data: Any) -> list[str]:
    """Pydantic would accept a tuple where JSON has a list; JSON only has lists, so only check what JSON can hold."""
    problems = []
    for key in ("ddx", "questions", "red_flags", "contradictions"):
        if key in data and not isinstance(data[key], list):
            problems.append(f"{key}: expected a list")
    return problems


def parse_response(text: str, allowed: AllowedCodes) -> Parsed:
    """Check an answer strictly (A-13); never repairs it."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        return Parsed(None, ("the answer is not a JSON object (text before it, Markdown or empty)",))
    try:
        data = canonical.loads(stripped)
    except (ValueError, UnicodeDecodeError) as exc:
        return Parsed(None, (f"not valid JSON: {exc}",))
    if not isinstance(data, dict):  # pragma: no cover - a text starting with "{" parses only to an object
        return Parsed(None, ("the answer is not a JSON object",))
    problems = _strict_types(data)
    try:
        response = Response.model_validate(data)
    except ValidationError as exc:
        for error in exc.errors(include_url=False):
            location = ".".join(str(part) for part in error["loc"])
            problems.append(f"{location}: {error['msg']}" if location else error["msg"])
        return Parsed(None, tuple(problems))
    if problems:
        return Parsed(None, tuple(problems))
    for key, codes in (
        ("ddx", allowed.ddx),
        ("red_flags", allowed.red_flags),
        ("questions", allowed.fields),
        ("contradictions", allowed.fields),
    ):
        unknown = sorted(set(getattr(response, key)) - codes)
        if unknown:
            problems.append(f"{key}: codes not allowed in this domain: {', '.join(unknown)}")
    if problems:
        return Parsed(None, tuple(problems))
    return Parsed(response, ())


def response_json_schema() -> dict[str, Any]:
    """JSON Schema (draft 2020-12) of an answer, generated from :class:`Response`."""
    schema = Response.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Proof answer"
    schema["description"] = (
        "The answer a model gives to a Proof case: decision, codes and a free-text rationale that is not scored. "
        "Which codes are allowed depends on the domain; the system prompt lists them."
    )
    return schema
