"""Ablation (PR-K05) and required questions (PR-K09).

- A field is critical if removing it alone changes the engine's outcome.
- A required question of a variant is a fact of the base case that the variant lacks and whose return alone would
  change the variant's outcome (A-54). For a variant that lacks exactly one critical field, that is this field.

Both iterate over the field codes in sorted order and compare outcomes, so the result does not depend on the order of
the facts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from proof_rules.engine import outcome
from proof_rules.model import Domain


def critical_fields(domain: Domain, facts: Mapping[str, Any]) -> tuple[str, ...]:
    base = outcome(domain, facts)
    critical = []
    for code in sorted(facts):
        reduced = {key: value for key, value in facts.items() if key != code}
        if outcome(domain, reduced) != base:
            critical.append(code)
    return tuple(critical)


def ablation_table(domain: Domain, facts: Mapping[str, Any]) -> list[tuple[str, Any]]:
    """Outcome without each field, in sorted field order (for explanations)."""
    return [(code, outcome(domain, {k: v for k, v in facts.items() if k != code})) for code in sorted(facts)]


def required_questions(
    domain: Domain, variant_facts: Mapping[str, Any], base_facts: Mapping[str, Any]
) -> tuple[str, ...]:
    current = outcome(domain, variant_facts)
    missing = sorted(set(base_facts) - set(variant_facts))
    return tuple(code for code in missing if outcome(domain, {**variant_facts, code: base_facts[code]}) != current)
