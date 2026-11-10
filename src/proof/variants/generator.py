"""Variants MR1 to MR7 (PR-F06, PR-MR1 to PR-MR7, PR-D02).

- **MR1** leaves out one critical field of the base case. The key is recomputed by the rule set on the variant's
  facts; the expectation is the recomputed decision (``ask``, or ``refer_urgent`` if another red flag stays visible)
  and the removed field among the questions (PRD §6, A-54).
- **MR2** leaves out one field whose ablation changes nothing (not critical). Decision and diagnoses must stay as on
  the base case (A-14).
- **MR3** shows the four sections in an order other than the default. Facts and key stay the same; the answer must
  not change (A-14).
- **MR4** adds one irrelevant fact of the catalog that fits the patient. No rule uses it; the answer must not change.
- **MR5** pairs the base case's renderings in two languages, for each of the three pairs. It needs no request of its
  own: the two answers to the base case are compared (A-37).
- **MR6** shows facts in alternative units of the catalog and, or, names as abbreviations. A variant whose rounded
  numbers, read back, change the value of any rule is discarded and counted (A-39); otherwise the answer must not
  change.
- **MR7** adds the statement of a contradiction template whose condition holds on the facts. The answer must name
  the contradicted field among its contradictions (A-15).

Which field, order, fact, notation or statement a variant gets is drawn from a stream of the domain, the case's seed,
the variant seed and the relation. The same variant seed gives the same variants; a new variant seed gives new ones
(PR-D02, A-17). Several variants of one relation per case draw without repetition.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from itertools import permutations, product
from types import MappingProxyType
from typing import Any

from proof.cases.model import Case
from proof.core.i18n import LANGUAGES
from proof.core.rng import Stream
from proof.variants.model import (
    DECISION_AND_DDX,
    DEFAULT_ORDER,
    UNCHANGED,
    AbsoluteExpectation,
    AddFacts,
    ChangeNotation,
    InsertContradiction,
    InvariantExpectation,
    LanguagePair,
    PermuteSections,
    RemoveField,
    RenderOptions,
    Variant,
)
from proof.variants.notation import flipped_rules
from proof_rules.engine import VariantKey
from proof_rules.keys import compute_variant_key
from proof_rules.logic import Truth, evaluate
from proof_rules.model import Domain

BUILT_MRS: tuple[str, ...] = ("MR1", "MR2", "MR3", "MR4", "MR5", "MR6", "MR7")
# Relations that need a request of their own; MR5 compares answers to base cases (A-37).
REQUESTED_MRS: frozenset[str] = frozenset(BUILT_MRS) - {"MR5"}
PERMUTED_ORDERS: tuple[tuple[str, ...], ...] = tuple(
    order for order in permutations(DEFAULT_ORDER) if order != DEFAULT_ORDER
)
LANGUAGE_PAIRS: tuple[tuple[str, str], ...] = (("zh", "en"), ("zh", "de"), ("en", "de"))


class VariantError(ValueError):
    """Variants cannot be built with these options."""


@dataclass(frozen=True)
class Generated:
    """Variants of a set of cases and, per relation, how many fewer were possible than asked for and how many drawn
    variants were discarded (MR6, A-39)."""

    variants: tuple[Variant, ...]
    missing: MappingProxyType[str, int]
    discarded: MappingProxyType[str, int]


@dataclass(frozen=True)
class Made:
    """Variants of one case and relation, with the number of drawn variants that were discarded."""

    variants: list[Variant]
    discarded: int = 0


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


def _base_key(case: Case, domain: Domain) -> VariantKey:
    return compute_variant_key(domain, case.facts, case.facts)


def mr1(case: Case, domain: Domain, variant_seed: int, per_case: int) -> Made:
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
    return Made(variants)


def mr2(case: Case, domain: Domain, variant_seed: int, per_case: int) -> Made:
    """Leave out a field whose ablation changes nothing; decision and diagnoses stay."""
    candidates = sorted(set(case.facts) - set(case.key.critical_fields))
    chosen = _stream(domain, case, variant_seed, "MR2").shuffled(candidates)[:per_case]
    variants = []
    for index, field in enumerate(chosen, start=1):
        facts = {code: value for code, value in case.facts.items() if code != field}
        key = compute_variant_key(domain, facts, case.facts)
        unchanged = (key.determinability, key.red_flags, key.ddx) == (
            case.key.determinability,
            case.key.red_flags,
            case.key.ddx,
        )
        if not unchanged or key.required_questions:  # pragma: no cover - holds for every field that is not critical
            raise VariantError(f"{case.case_id}: leaving out {field} changes the output, but it is not critical")
        variants.append(
            _variant(
                case,
                "MR2",
                str(index),
                variant_seed,
                change=RemoveField(kind="remove_field", field=field),
                facts=facts,
                render=RenderOptions(),
                key=key,
                expectation=InvariantExpectation(kind="invariant", compare=DECISION_AND_DDX),
            )
        )
    return Made(variants)


def mr3(case: Case, domain: Domain, variant_seed: int, per_case: int) -> Made:
    """Show the sections in another order; nothing else changes."""
    orders = _stream(domain, case, variant_seed, "MR3").shuffled(list(PERMUTED_ORDERS))[:per_case]
    key = _base_key(case, domain)
    return Made(
        [
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
    )


def fitting_irrelevant(case: Case, domain: Domain) -> list[str]:
    """Codes of the irrelevant facts whose condition fits the case's patient, in catalog order."""
    return [fact.code for fact in domain.catalog.irrelevant if fact.when.fits(case.patient.sex, case.patient.age)]


def mr4(case: Case, domain: Domain, variant_seed: int, per_case: int) -> Made:
    """Add one irrelevant fact that fits the patient; the coded facts and the key stay."""
    chosen = _stream(domain, case, variant_seed, "MR4").shuffled(fitting_irrelevant(case, domain))[:per_case]
    key = _base_key(case, domain)
    return Made(
        [
            _variant(
                case,
                "MR4",
                str(index),
                variant_seed,
                change=AddFacts(kind="add_facts", facts=(code,)),
                facts=dict(case.facts),
                render=RenderOptions(),
                key=key,
                expectation=InvariantExpectation(kind="invariant", compare=UNCHANGED),
            )
            for index, code in enumerate(chosen, start=1)
        ]
    )


def mr5(case: Case, domain: Domain, variant_seed: int, per_case: int) -> Made:
    """The three language pairs of the base case; ``per_case`` does not apply."""
    key = _base_key(case, domain)
    return Made(
        [
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
    )


def notation_options(case: Case, domain: Domain) -> list[tuple[dict[str, str], bool]]:
    """Every notation MR6 can choose for a case: a unit per convertible fact (or none) and abbreviations on or off.

    The notation of the base case itself is left out. Abbreviations are an option only if a fact of the case has one.
    """
    convertible = [field for field in domain.catalog.fields if field.code in case.facts and field.alt_units]
    abbreviated = any(
        getattr(field.labels, lang).abbr is not None
        for field in domain.catalog.fields
        if field.code in case.facts
        for lang in LANGUAGES
    )
    choices = [[None, *(alt.unit for alt in field.alt_units)] for field in convertible]
    options = []
    for units in product(*choices):
        chosen = {field.code: unit for field, unit in zip(convertible, units, strict=True) if unit is not None}
        for abbreviations in (False, True) if abbreviated else (False,):
            if chosen or abbreviations:
                options.append((chosen, abbreviations))
    return options


def mr6(case: Case, domain: Domain, variant_seed: int, per_case: int) -> Made:
    """Show facts in alternative units and, or, as abbreviations; discard a draw that changes a rule value (A-39)."""
    drawn = _stream(domain, case, variant_seed, "MR6").shuffled(notation_options(case, domain))[:per_case]
    key = _base_key(case, domain)
    variants = []
    discarded = 0
    for units, abbreviations in drawn:
        if flipped_rules(domain, case.facts, units):
            discarded += 1
            continue
        variants.append(
            _variant(
                case,
                "MR6",
                str(len(variants) + 1),
                variant_seed,
                change=ChangeNotation(kind="change_notation", units=units, abbreviations=abbreviations),
                facts=dict(case.facts),
                render=RenderOptions(),
                key=key,
                expectation=InvariantExpectation(kind="invariant", compare=UNCHANGED),
            )
        )
    return Made(variants, discarded)


def fitting_contradictions(case: Case, domain: Domain) -> list[str]:
    """Ids of the contradiction templates whose condition is true on the case's facts, in catalog order."""
    return [
        template.id
        for template in domain.catalog.contradictions
        if evaluate(template.when, case.facts, domain.references) is Truth.TRUE
    ]


def mr7(case: Case, domain: Domain, variant_seed: int, per_case: int) -> Made:
    """Add a statement that contradicts a fact; the answer must name that fact among its contradictions."""
    chosen = _stream(domain, case, variant_seed, "MR7").shuffled(fitting_contradictions(case, domain))[:per_case]
    key = _base_key(case, domain)
    variants = []
    for index, template_id in enumerate(chosen, start=1):
        template = domain.catalog.contradiction(template_id)
        assert template is not None  # noqa: S101 - the id comes from the catalog
        variants.append(
            _variant(
                case,
                "MR7",
                str(index),
                variant_seed,
                change=InsertContradiction(kind="insert_contradiction", template=template.id, field=template.field),
                facts=dict(case.facts),
                render=RenderOptions(),
                key=key,
                expectation=AbsoluteExpectation(kind="absolute", contradictions_include=(template.field,)),
            )
        )
    return Made(variants)


BUILDERS: dict[str, Callable[[Case, Domain, int, int], Made]] = {
    "MR1": mr1,
    "MR2": mr2,
    "MR3": mr3,
    "MR4": mr4,
    "MR5": mr5,
    "MR6": mr6,
    "MR7": mr7,
}


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
    discarded: Counter[str] = Counter()
    for case in cases:
        for mr in chosen:
            made = BUILDERS[mr](case, domain, variant_seed, per_case)
            variants.extend(made.variants)
            if mr != "MR5":
                missing[mr] += per_case - len(made.variants) - made.discarded
                discarded[mr] += made.discarded
    counted = [mr for mr in chosen if mr != "MR5"]
    return Generated(
        variants=tuple(variants),
        missing=MappingProxyType({mr: missing[mr] for mr in counted}),
        discarded=MappingProxyType({mr: discarded[mr] for mr in counted}),
    )
