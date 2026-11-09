"""Variants MR1, MR3 and MR5 (PR-F06, PR-MR1, PR-MR3, PR-MR5, PR-D02).

- **MR1** leaves out one critical field of the base case. The key is recomputed by the rule set on the variant's
  facts; the expectation is the recomputed decision (``ask``, or ``refer_urgent`` if another red flag stays visible)
  and the removed field among the questions (PRD §6, A-54).
- **MR3** shows the four sections in an order other than the default. Facts and key stay the same; the answer must
  not change (A-14).
- **MR5** pairs the base case's renderings in two languages, for each of the three pairs. It needs no request of its
  own: the two answers to the base case are compared (A-37).

Which field and which order a variant gets is drawn from a stream of the domain, the case's seed, the variant seed
and the relation. The same variant seed gives the same variants; a new variant seed gives new ones (PR-D02, A-17).
Several variants of one relation per case draw without repetition.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import permutations
from types import MappingProxyType
from typing import Any

from proof.cases.model import Case
from proof.core.rng import Stream
from proof.variants.model import (
    DEFAULT_ORDER,
    UNCHANGED,
    AbsoluteExpectation,
    InvariantExpectation,
    LanguagePair,
    PermuteSections,
    RemoveField,
    RenderOptions,
    Variant,
)
from proof_rules.keys import compute_variant_key
from proof_rules.model import Domain

BUILT_MRS: tuple[str, ...] = ("MR1", "MR3", "MR5")
# Relations that need a request of their own; MR5 compares answers to base cases (A-37).
REQUESTED_MRS: frozenset[str] = frozenset({"MR1", "MR3"})
PERMUTED_ORDERS: tuple[tuple[str, ...], ...] = tuple(
    order for order in permutations(DEFAULT_ORDER) if order != DEFAULT_ORDER
)
LANGUAGE_PAIRS: tuple[tuple[str, str], ...] = (("zh", "en"), ("zh", "de"), ("en", "de"))


class VariantError(ValueError):
    """Variants cannot be built with these options."""


@dataclass(frozen=True)
class Generated:
    """Variants of a set of cases and, per relation, how many fewer were possible than asked for."""

    variants: tuple[Variant, ...]
    missing: MappingProxyType[str, int]


def _stream(domain: Domain, case: Case, variant_seed: int, mr: str) -> Stream:
    return Stream("variant", domain.name, case.seed, variant_seed, mr)


def _variant(case: Case, mr: str, suffix: str, variant_seed: int, **fields: Any) -> Variant:
    return Variant(
        variant_id=f"{case.case_id}-{mr}-{suffix}",
        case_id=case.case_id,
        mr=mr,
        variant_seed=variant_seed,
        **fields,
    )


def mr1(case: Case, domain: Domain, variant_seed: int, per_case: int) -> list[Variant]:
    """Leave out a critical field; the expectation follows the engine on the variant's facts."""
    chosen = _stream(domain, case, variant_seed, "MR1").shuffled(list(case.key.critical_fields))[:per_case]
    variants = []
    for index, field in enumerate(chosen, start=1):
        facts = {code: value for code, value in case.facts.items() if code != field}
        key = compute_variant_key(domain, facts, case.facts)
        if field not in key.required_questions:  # pragma: no cover - a critical field is always a required question
            raise VariantError(f"{case.case_id}: {field} is critical but not a required question")
        expectation = AbsoluteExpectation(kind="absolute", decision=key.determinability, questions_include=(field,))
        variants.append(
            _variant(
                case,
                "MR1",
                str(index),
                variant_seed,
                change=RemoveField(kind="remove_field", field=field),
                facts=facts,
                render=RenderOptions(),
                key=key,
                expectation=expectation,
            )
        )
    return variants


def mr3(case: Case, domain: Domain, variant_seed: int, per_case: int) -> list[Variant]:
    """Show the sections in another order; nothing else changes."""
    orders = _stream(domain, case, variant_seed, "MR3").shuffled(list(PERMUTED_ORDERS))[:per_case]
    key = compute_variant_key(domain, case.facts, case.facts)
    return [
        _variant(
            case,
            "MR3",
            str(index),
            variant_seed,
            change=PermuteSections(kind="permute_sections", order=order),
            facts=dict(case.facts),
            render=RenderOptions(order=order),
            key=key,
            expectation=InvariantExpectation(kind="invariant", compare=UNCHANGED),
        )
        for index, order in enumerate(orders, start=1)
    ]


def mr5(case: Case, domain: Domain, variant_seed: int) -> list[Variant]:
    """The three language pairs of the base case."""
    key = compute_variant_key(domain, case.facts, case.facts)
    return [
        _variant(
            case,
            "MR5",
            f"{first}-{second}",
            variant_seed,
            change=LanguagePair(kind="language_pair", langs=(first, second)),
            facts=dict(case.facts),
            render=RenderOptions(),
            key=key,
            expectation=InvariantExpectation(kind="invariant", compare=UNCHANGED),
        )
        for first, second in LANGUAGE_PAIRS
    ]


def check_options(variant_seed: int, per_case: int, mrs: Sequence[str]) -> tuple[str, ...]:
    """The relations in canonical order; rejects unknown or unbuilt relations and bad counts."""
    problems = []
    if variant_seed < 0:
        problems.append(f"variant seed must not be negative, got {variant_seed}")
    if per_case < 1:
        problems.append(f"per_case must be at least 1, got {per_case}")
    unknown = sorted(set(mrs) - set(BUILT_MRS))
    if unknown:
        problems.append(f"relations not available: {', '.join(unknown)} (built: {', '.join(BUILT_MRS)})")
    if not mrs:
        problems.append("choose at least one relation")
    if problems:
        raise VariantError("; ".join(problems))
    return tuple(mr for mr in BUILT_MRS if mr in mrs)


def generate(
    cases: Iterable[Case],
    domain: Domain,
    variant_seed: int,
    *,
    per_case: int = 1,
    mrs: Sequence[str] = BUILT_MRS,
) -> Generated:
    """Variants of every case, ordered by case, relation and number."""
    chosen = check_options(variant_seed, per_case, mrs)
    variants: list[Variant] = []
    missing: Counter[str] = Counter()
    for case in cases:
        if "MR1" in chosen:
            made = mr1(case, domain, variant_seed, per_case)
            missing["MR1"] += per_case - len(made)
            variants.extend(made)
        if "MR3" in chosen:
            made = mr3(case, domain, variant_seed, per_case)
            missing["MR3"] += per_case - len(made)
            variants.extend(made)
        if "MR5" in chosen:
            variants.extend(mr5(case, domain, variant_seed))
    return Generated(
        variants=tuple(variants), missing=MappingProxyType({mr: missing[mr] for mr in chosen if mr != "MR5"})
    )
