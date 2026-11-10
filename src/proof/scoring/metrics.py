"""Metrics S1–S7 (PR-F08, PR-S1 to PR-S7, A-13, A-14, A-37): pure functions over answered units.

Every metric is a micro average over units with its numerator and denominator; an empty denominator gives ``"n/a"``,
never 0. The result is a profile of separate metrics; no value combines them (PR-P02, NZ-03).

- An answer is valid only under the strict check of :func:`proof.scoring.response.parse_response` (S7). An invalid
  answer counts in S1–S4 as an empty answer: no decision, all lists empty (A-13).
- A unit with a transmission error has no answer and counts nowhere (A-36); profiles report how many there were.
- **S1** decision equals the key's determinability, over all units.
- **S2** recall of the required questions over units that have any, precision over all questions named.
- **S3** recall of the key's red flags, over units with at least one, separately for complete units (all facts of
  the base case) and incomplete ones (MR1, MR2: a fact missing). Never averaged together.
- **S4** hit if at least one key diagnosis is named, over units with at least one.
- **S5** violation rate per relation (A-14): MR1 and MR7 against their absolute expectation; MR2, MR3, MR4 and MR6
  against the answer to the base case in the same language (MR2 in decision and diagnoses only); MR5 the answers to
  the base case in two languages (A-37). Pairs with an invalid answer are left out of the denominator and counted;
  so are pairs whose partner has no answer.
- **S6** range (max - min) over the languages of S1 and of both S3 values.
- **S7** share of valid answers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from proof.scoring.response import AllowedCodes, Response, parse_response

NA = "n/a"
DECIMALS = 4
LANGUAGE_PAIRS: tuple[tuple[str, str], ...] = (("zh", "en"), ("zh", "de"), ("en", "de"))
UNCHANGED: tuple[str, ...] = ("decision", "ddx", "red_flags", "questions")


# --- Inputs ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Truth:
    """What the key of a unit says, and whether the unit shows all facts of its base case."""

    determinability: str
    red_flags: frozenset[str]
    ddx: frozenset[str]
    required_questions: frozenset[str]
    complete: bool


@dataclass(frozen=True)
class Expected:
    """The machine-readable expectation of a variant unit (absolute for MR1 and MR7, invariant for the others).

    An absolute expectation checks only the targets it sets: the decision, if given, and the codes that must be among
    the questions and among the contradictions.
    """

    kind: Literal["absolute", "invariant"]
    decision: str | None = None
    questions_include: frozenset[str] = frozenset()
    contradictions_include: frozenset[str] = frozenset()
    compare: tuple[str, ...] = UNCHANGED

    def met_by(self, item: Evaluated) -> bool:
        """Whether a valid answer meets this absolute expectation."""
        return (
            (self.decision is None or item.decision == self.decision)
            and self.questions_include <= item.questions
            and self.contradictions_include <= item.contradictions
        )


@dataclass(frozen=True)
class UnitInput:
    """One answered (or failed) unit with what it is scored against."""

    unit_id: str
    item_id: str
    case_id: str
    mr: str | None
    lang: str
    status: Literal["ok", "error"]
    text: str | None
    truth: Truth
    expected: Expected | None = None


@dataclass(frozen=True)
class Evaluated:
    """A unit with its answer read strictly; an invalid answer becomes the empty answer."""

    unit: UnitInput
    valid: bool
    problems: tuple[str, ...]
    decision: str | None
    ddx: frozenset[str]
    red_flags: frozenset[str]
    questions: frozenset[str]
    contradictions: frozenset[str]

    def field_set(self, name: str) -> Any:
        return self.decision if name == "decision" else getattr(self, name)


def evaluate(unit: UnitInput, allowed: AllowedCodes) -> Evaluated:
    """Read a unit's answer strictly (A-13)."""
    parsed = parse_response(unit.text or "", allowed) if unit.status == "ok" else None
    response: Response | None = parsed.response if parsed is not None else None
    if response is None:
        problems = parsed.problems if parsed is not None else ("no answer (transmission error)",)
        empty: frozenset[str] = frozenset()
        return Evaluated(unit, False, tuple(problems), None, empty, empty, empty, empty)
    return Evaluated(
        unit=unit,
        valid=True,
        problems=(),
        decision=response.decision,
        ddx=frozenset(response.ddx),
        red_flags=frozenset(response.red_flags),
        questions=frozenset(response.questions),
        contradictions=frozenset(response.contradictions),
    )


# --- Ratios ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Ratio:
    numerator: int
    denominator: int

    @property
    def value(self) -> float | str:
        return round(self.numerator / self.denominator, DECIMALS) if self.denominator else NA

    def to_json(self) -> dict[str, Any]:
        return {"numerator": self.numerator, "denominator": self.denominator, "value": self.value}


def _sum(ratios: Iterable[tuple[int, int]]) -> Ratio:
    numerator = denominator = 0
    for part, whole in ratios:
        numerator += part
        denominator += whole
    return Ratio(numerator, denominator)


# --- Single metrics --------------------------------------------------------------------------------------------------


def s1(units: Sequence[Evaluated]) -> Ratio:
    return _sum((int(item.decision == item.unit.truth.determinability), 1) for item in units)


def s2_recall(units: Sequence[Evaluated]) -> Ratio:
    return _sum(
        (len(item.questions & item.unit.truth.required_questions), len(item.unit.truth.required_questions))
        for item in units
        if item.unit.truth.required_questions
    )


def s2_precision(units: Sequence[Evaluated]) -> Ratio:
    return _sum((len(item.questions & item.unit.truth.required_questions), len(item.questions)) for item in units)


def s3(units: Sequence[Evaluated], complete: bool) -> Ratio:
    return _sum(
        (len(item.red_flags & item.unit.truth.red_flags), len(item.unit.truth.red_flags))
        for item in units
        if item.unit.truth.red_flags and item.unit.truth.complete == complete
    )


def s4(units: Sequence[Evaluated]) -> Ratio:
    return _sum((int(bool(item.ddx & item.unit.truth.ddx)), 1) for item in units if item.unit.truth.ddx)


def s7(units: Sequence[Evaluated]) -> Ratio:
    return _sum((int(item.valid), 1) for item in units)


@dataclass
class Invariance:
    """S5 of one relation: violations among comparable pairs, and the pairs left out."""

    violations: int = 0
    pairs: int = 0
    invalid_excluded: int = 0
    missing_excluded: int = 0
    violated: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "violation_rate": Ratio(self.violations, self.pairs).to_json(),
            "invalid_excluded": self.invalid_excluded,
            "missing_excluded": self.missing_excluded,
        }


def _differs(first: Evaluated, second: Evaluated, compare: Sequence[str]) -> bool:
    return any(first.field_set(name) != second.field_set(name) for name in compare)


def s5(
    units: Sequence[Evaluated],
    answered_base: Mapping[tuple[str, str], Evaluated],
    langs: Sequence[str] = (),
    cases: Sequence[str] = (),
) -> dict[str, Invariance]:
    """Violation rates per relation (MR1 to MR7).

    ``answered_base`` maps (case id, language) to the base unit's answer; ``langs`` and ``cases`` are the run's
    languages and base cases, so a pair whose partner failed counts as left out.
    """
    result: dict[str, Invariance] = {}
    for item in units:
        unit = item.unit
        if unit.mr is None or unit.expected is None:
            continue
        invariance = result.setdefault(unit.mr, Invariance())
        if unit.expected.kind == "absolute":
            if not item.valid:
                invariance.invalid_excluded += 1
                continue
            invariance.pairs += 1
            if not unit.expected.met_by(item):
                invariance.violations += 1
                invariance.violated.append(unit.unit_id)
            continue
        base = answered_base.get((unit.case_id, unit.lang))
        if base is None:
            invariance.missing_excluded += 1
            continue
        if not (item.valid and base.valid):
            invariance.invalid_excluded += 1
            continue
        invariance.pairs += 1
        if _differs(item, base, unit.expected.compare):
            invariance.violations += 1
            invariance.violated.append(unit.unit_id)
    if len(langs) > 1:
        mr5 = result.setdefault("MR5", Invariance())
        for case in sorted(cases):
            for first, second in LANGUAGE_PAIRS:
                if first not in langs or second not in langs:
                    continue
                a, b = answered_base.get((case, first)), answered_base.get((case, second))
                if a is None or b is None:
                    mr5.missing_excluded += 1
                elif not (a.valid and b.valid):
                    mr5.invalid_excluded += 1
                else:
                    mr5.pairs += 1
                    if _differs(a, b, UNCHANGED):
                        mr5.violations += 1
                        mr5.violated.append(f"{case}@{first}-{second}")
    return dict(sorted(result.items()))


def spread(values: Mapping[str, Ratio]) -> dict[str, Any]:
    """S6: max - min of the languages' values; n/a unless at least two languages have a value."""
    numbers = {lang: ratio.value for lang, ratio in values.items() if ratio.value != NA}
    by_lang = {lang: ratio.value for lang, ratio in values.items()}
    if len(numbers) < 2:
        return {"value": NA, "by_lang": by_lang}
    return {"value": round(max(numbers.values()) - min(numbers.values()), DECIMALS), "by_lang": by_lang}


# --- Profile ---------------------------------------------------------------------------------------------------------


def _split(units: Sequence[Evaluated], langs: Sequence[str], metric) -> dict[str, Any]:
    return {
        "all": metric(units).to_json(),
        "by_lang": {lang: metric([item for item in units if item.unit.lang == lang]).to_json() for lang in langs},
    }


def metrics(inputs: Sequence[UnitInput], allowed: AllowedCodes, langs: Sequence[str]) -> dict[str, Any]:
    """The metric part of a profile; units with a transmission error are counted but not scored (A-36)."""
    answered = [evaluate(unit, allowed) for unit in inputs if unit.status == "ok"]
    errors = sum(1 for unit in inputs if unit.status != "ok")
    base = {(item.unit.case_id, item.unit.lang): item for item in answered if item.unit.mr is None}
    by_lang_s1 = {lang: s1([item for item in answered if item.unit.lang == lang]) for lang in langs}
    by_lang_s3 = {
        complete: {lang: s3([item for item in answered if item.unit.lang == lang], complete) for lang in langs}
        for complete in (True, False)
    }
    cases = sorted({unit.case_id for unit in inputs if unit.mr is None})
    invariance = s5(answered, base, langs, cases)
    return {
        "units": {
            "total": len(inputs),
            "answered": len(answered),
            "errors": errors,
            "valid": sum(item.valid for item in answered),
            "invalid": sum(not item.valid for item in answered),
        },
        "S1_decision": _split(answered, langs, s1),
        "S2_questions": {
            "recall": _split(answered, langs, s2_recall),
            "precision": _split(answered, langs, s2_precision),
        },
        "S3_red_flags": {
            "complete": _split(answered, langs, lambda items: s3(items, True)),
            "incomplete": _split(answered, langs, lambda items: s3(items, False)),
        },
        "S4_diagnoses": _split(answered, langs, s4),
        "S5_invariance": {mr: item.to_json() for mr, item in invariance.items()},
        "S6_language_spread": {
            "S1_decision": spread(by_lang_s1),
            "S3_red_flags_complete": spread(by_lang_s3[True]),
            "S3_red_flags_incomplete": spread(by_lang_s3[False]),
        },
        "S7_format": _split(answered, langs, s7),
    }
