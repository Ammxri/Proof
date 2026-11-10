"""Language templates of Proof (A-11, A-12): case text, system prompt and language table per language.

Each language has a folder ``proof/render/templates/<lang>/`` with three files:

- ``case.j2``: the case text, structured like the prototype's long form (four sections);
- ``system_prompt.j2``: the system prompt with the answer format and every allowed code;
- ``strings.yaml``: section headings, yes/no, sex, decimal separator and the display of every unit.

Templates are rendered in Jinja2's immutable sandbox with ``StrictUndefined``: a missing value is an error, never an
empty string (KONZEPT §7). The physician review covers these files and the labels of each domain in that language;
:func:`template_hashes` gives the hashes a review record names (A-23, PR-A06).
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import cache
from importlib import resources
from typing import Annotated, Any, Literal

from jinja2 import DictLoader, StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from proof.core import canonical, yamlio
from proof.core.hashing import sha256_bytes, sha256_json
from proof.core.i18n import LANGUAGES
from proof_rules.model import Domain, Text

CASE_TEMPLATE = "case.j2"
PROMPT_TEMPLATE = "system_prompt.j2"
STRINGS_FILE = "strings.yaml"
TEMPLATE_FILES = (CASE_TEMPLATE, PROMPT_TEMPLATE, STRINGS_FILE)
SECTIONS = ("hx", "exam", "vital", "lab")


class TemplateError(ValueError):
    """A template or language table is missing or invalid, or a language is unknown."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SectionHeadings(_Model):
    hx: Text
    exam: Text
    vital: Text
    lab: Text


class SexLabels(_Model):
    f: Text
    m: Text


class Strings(_Model):
    """``strings.yaml``: the texts of a language that are not part of the template's layout."""

    decimal_separator: Literal[",", "."]
    bool_true: Text
    bool_false: Text
    sections: SectionHeadings
    empty_section: Text
    sex: SexLabels
    # Display of each catalog unit, including a leading space where the language puts one; may be empty.
    units: dict[Text, Annotated[str, StringConstraints(max_length=40)]]


def check_language(lang: str) -> None:
    if lang not in LANGUAGES:
        raise TemplateError(f"unknown language {lang!r}; expected one of {', '.join(LANGUAGES)}")


def _resource(lang: str, name: str):
    return resources.files("proof.render").joinpath("templates", lang, name)


@cache
def template_bytes(lang: str, name: str) -> bytes:
    """The bytes of one template file."""
    check_language(lang)
    if name not in TEMPLATE_FILES:
        raise TemplateError(f"unknown template {name!r}")
    resource = _resource(lang, name)
    if not resource.is_file():
        raise TemplateError(f"templates/{lang}/{name}: file is missing")
    data = resource.read_bytes()
    if b"\r" in data:
        raise TemplateError(f"templates/{lang}/{name}: line endings must be LF")
    return data


@cache
def strings(lang: str) -> Strings:
    """The language table of ``lang``."""
    source = f"templates/{lang}/{STRINGS_FILE}"
    try:
        data = yamlio.load_text(template_bytes(lang, STRINGS_FILE).decode("utf-8"), source=source)
        return Strings.model_validate(data)
    except (yamlio.YamlError, ValidationError) as exc:
        raise TemplateError(f"{source}: {exc}") from exc


@cache
def environment(lang: str) -> ImmutableSandboxedEnvironment:
    """The sandboxed Jinja2 environment with the two templates of ``lang``."""
    sources = {name: template_bytes(lang, name).decode("utf-8") for name in (CASE_TEMPLATE, PROMPT_TEMPLATE)}
    return ImmutableSandboxedEnvironment(
        loader=DictLoader(sources),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_template(lang: str, name: str, context: dict[str, Any]) -> str:
    """Render one template; lines lose trailing spaces and the text ends with exactly one newline."""
    raw = environment(lang).get_template(name).render(**context)
    lines = [line.rstrip() for line in raw.split("\n")]
    return "\n".join(lines).strip("\n") + "\n"


def labels(domain: Domain, lang: str) -> dict[str, Any]:
    """Every label of a domain in one language: complaint, facts with abbreviations and values, codes, and the lines
    variants add (irrelevant facts for MR4, contradicting statements for MR7)."""
    check_language(lang)
    fields = {}
    for field in domain.catalog.fields:
        label = getattr(field.labels, lang)
        fields[field.code] = {
            "name": label.name,
            "abbr": label.abbr,
            "values": {value: getattr(item, lang) for value, item in field.value_labels.items()},
        }
    return {
        "complaint": getattr(domain.complaint_labels, lang),
        "fields": fields,
        "ddx": {term.code: getattr(term.labels, lang) for term in domain.vocabulary.ddx},
        "red_flags": {term.code: getattr(term.labels, lang) for term in domain.vocabulary.red_flags},
        "irrelevant": {
            fact.code: getattr(fact.labels, lang).model_dump(mode="json") for fact in domain.catalog.irrelevant
        },
        "contradictions": {
            template.id: getattr(template.labels, lang).model_dump(mode="json")
            for template in domain.catalog.contradictions
        },
    }


def template_hashes(lang: str, domains: Iterable[Domain]) -> dict[str, str]:
    """SHA-256 of everything the physician review of ``lang`` covers, keyed by a stable name.

    ``templates/<lang>/<file>`` for the three template files and ``labels/<domain>/<lang>`` for the labels of each
    domain in that language.
    """
    hashes = {f"templates/{lang}/{name}": sha256_bytes(template_bytes(lang, name)) for name in TEMPLATE_FILES}
    for domain in domains:
        hashes[f"labels/{domain.name}/{lang}"] = sha256_json(labels(domain, lang))
    return dict(sorted(hashes.items()))


def canonical_labels(domain: Domain, lang: str) -> bytes:
    """The labels of :func:`labels` as canonical JSON, e.g. for a review packet."""
    return canonical.dumps_bytes(labels(domain, lang))
