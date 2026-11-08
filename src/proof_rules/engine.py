"""Inference engine: evaluates the active rules of a domain on a set of facts.

Rules with the same target are combined with Kleene ``or``. The output of the engine is the triple
(determinability, red flags, differential diagnoses), which is also what ablation compares (D-05):
- ``refer_urgent`` if at least one red flag is true;
- otherwise ``ask`` if a red flag or a diagnosis is unknown, i.e. a missing fact would decide it (A-33, A-53);
- otherwise ``answer``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from proof_rules.logic import Truth, evaluate, t_or
from proof_rules.model import Domain, FieldCode, Rule, TermCode

Determinability = Literal["answer", "ask", "refer_urgent"]


@dataclass(frozen=True)
class Outcome:
    """What the engine concludes; two outcomes are equal exactly when all three parts are equal."""

    determinability: Determinability
    red_flags: tuple[str, ...]
    ddx: tuple[str, ...]


@dataclass(frozen=True)
class Inference:
    rules: Mapping[str, Truth]
    targets: Mapping[str, Truth]
    outcome: Outcome


def infer(domain: Domain, facts: Mapping[str, Any]) -> Inference:
    """Evaluate every active rule; facts are not validated here (see :func:`proof_rules.keys.compute_key`)."""
    return infer_rules(domain.rules, domain.references, facts)


def infer_rules(rules: tuple[Rule, ...], references: Mapping[str, Any], facts: Mapping[str, Any]) -> Inference:
    rule_truths: dict[str, Truth] = {}
    by_target: dict[str, list[Truth]] = {}
    kinds: dict[str, str] = {}
    for rule in rules:
        truth = evaluate(rule.when, facts, references)
        rule_truths[rule.id] = truth
        by_target.setdefault(rule.target, []).append(truth)
        kinds[rule.target] = rule.kind
    targets = {target: t_or(by_target[target]) for target in sorted(by_target)}
    red_flags = tuple(t for t, v in targets.items() if kinds[t] == "red_flag" and v is Truth.TRUE)
    ddx = tuple(t for t, v in targets.items() if kinds[t] == "ddx" and v is Truth.TRUE)
    if red_flags:
        determinability: Determinability = "refer_urgent"
    elif any(value is Truth.UNKNOWN for value in targets.values()):
        determinability = "ask"
    else:
        determinability = "answer"
    return Inference(
        rules=MappingProxyType(dict(sorted(rule_truths.items()))),
        targets=MappingProxyType(targets),
        outcome=Outcome(determinability, red_flags, ddx),
    )


def outcome(domain: Domain, facts: Mapping[str, Any]) -> Outcome:
    return infer(domain, facts).outcome


def _sorted_unique(values: tuple[str, ...], name: str) -> None:
    if list(values) != sorted(set(values)):
        raise ValueError(f"{name} must be sorted and free of duplicates")


class Key(BaseModel):
    """Key of a case as in the PRD (§5): determinability, red flags, critical fields, differential diagnoses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    determinability: Determinability
    red_flags: tuple[TermCode, ...]
    critical_fields: tuple[FieldCode, ...]
    ddx: tuple[TermCode, ...]

    @model_validator(mode="after")
    def _canonical_lists(self) -> Key:
        for name in ("red_flags", "critical_fields", "ddx"):
            _sorted_unique(getattr(self, name), name)
        return self


class VariantKey(Key):
    """Key of a variant: the recomputed key plus the required questions (PR-K09)."""

    required_questions: Annotated[tuple[FieldCode, ...], Field()]

    @model_validator(mode="after")
    def _canonical_questions(self) -> VariantKey:
        _sorted_unique(self.required_questions, "required_questions")
        return self
