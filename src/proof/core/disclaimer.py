"""The fixed notices required in CLI help, reports, leaderboard and dataset card (PR-D03, PR-A01, A-24)."""

from __future__ import annotations

from proof.core import i18n

KEYS: tuple[str, ...] = ("disclaimer.category", "disclaimer.reference")


def lines(lang: str) -> list[str]:
    """Both notices in one language."""
    return [i18n.text(key, lang) for key in KEYS]


def block() -> str:
    """Both notices in all three languages, one language per line, prefixed with the language code."""
    return "\n".join(f"{lang}: {' '.join(lines(lang))}" for lang in i18n.LANGUAGES)
