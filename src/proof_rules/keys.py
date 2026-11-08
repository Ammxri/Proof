"""Keys of cases and variants, always computed by the rule set (PR-K04), never by a language model (PR-N04)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from proof_rules.ablation import critical_fields, required_questions
from proof_rules.engine import Key, VariantKey, outcome
from proof_rules.model import Domain


class FactError(ValueError):
    """Facts contain unknown codes or invalid values for the domain."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(problems))


def _checked(domain: Domain, facts: Mapping[str, Any]) -> None:
    problems = domain.fact_problems(facts)
    if problems:
        raise FactError(problems)


def compute_key(domain: Domain, facts: Mapping[str, Any]) -> Key:
    _checked(domain, facts)
    result = outcome(domain, facts)
    return Key(
        determinability=result.determinability,
        red_flags=result.red_flags,
        critical_fields=critical_fields(domain, facts),
        ddx=result.ddx,
    )


def compute_variant_key(domain: Domain, variant_facts: Mapping[str, Any], base_facts: Mapping[str, Any]) -> VariantKey:
    _checked(domain, variant_facts)
    _checked(domain, base_facts)
    key = compute_key(domain, variant_facts)
    return VariantKey(**key.model_dump(), required_questions=required_questions(domain, variant_facts, base_facts))
