"""Language tables for user-facing texts in zh, en and de (A-28).

Each language has a YAML file in ``proof/core/locales``. Nested keys are addressed with dots, e.g.
``disclaimer.category``. A missing key is an error, never a silent fallback to another language.
"""

from __future__ import annotations

import unicodedata
from functools import cache
from importlib import resources
from typing import Any

from proof.core import yamlio

LANGUAGES: tuple[str, ...] = ("zh", "en", "de")


class TranslationError(KeyError):
    """A text key is missing or a language is unknown."""


def _flatten(prefix: str, node: Any, out: dict[str, str], source: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _flatten(f"{prefix}.{key}" if prefix else key, value, out, source)
        return
    if not isinstance(node, str):
        raise TranslationError(f"{source}: value of {prefix!r} must be a string")
    if unicodedata.normalize("NFC", node) != node:
        raise TranslationError(f"{source}: value of {prefix!r} is not NFC-normalised")
    out[prefix] = node


@cache
def table(lang: str) -> dict[str, str]:
    """All texts of one language as a flat mapping from dotted key to text."""
    if lang not in LANGUAGES:
        raise TranslationError(f"unknown language {lang!r}; expected one of {', '.join(LANGUAGES)}")
    resource = resources.files("proof.core").joinpath("locales", f"{lang}.yaml")
    data = yamlio.load_text(resource.read_text(encoding="utf-8"), source=f"locales/{lang}.yaml")
    if not isinstance(data, dict):
        raise TranslationError(f"locales/{lang}.yaml: top level must be a mapping")
    flat: dict[str, str] = {}
    _flatten("", data, flat, f"locales/{lang}.yaml")
    return flat


def text(key: str, lang: str) -> str:
    """The text for ``key`` in ``lang``."""
    texts = table(lang)
    if key not in texts:
        raise TranslationError(f"missing text {key!r} for language {lang!r}")
    return texts[key]


def missing_keys() -> dict[str, set[str]]:
    """For each language, the keys that another language has but this one lacks."""
    all_keys = set().union(*(table(lang).keys() for lang in LANGUAGES))
    return {lang: all_keys - table(lang).keys() for lang in LANGUAGES}
