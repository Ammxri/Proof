"""Data model of rule packs: fact catalog, vocabulary, source register, rules, pack configuration and domain.

All models are frozen and reject unknown keys. Conditions are plain data: comparisons and connectives, no expression
strings and no ``eval``. Their three-valued semantics live in :mod:`proof_rules.logic`.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    PrivateAttr,
    Strict,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    Tag,
    model_validator,
)

FIELD_CODE_PATTERN = r"^(hx|exam|vital|lab)\.[a-z][a-z0-9_]*$"
TERM_CODE_PATTERN = r"^(ddx|rf)\.[a-z][a-z0-9_]*$"
VALUE_CODE_PATTERN = r"^[a-z][a-z0-9_]*$"
SOURCE_ID_PATTERN = r"^SRC-[0-9]{4}$"
RULE_ID_PATTERN = r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$"
PACK_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"
LEGACY_KEY_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"
SYNTHEHR_CODE_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"

ORDERED_OPS = frozenset({"lt", "le", "gt", "ge"})
RULE_KINDS = ("red_flag", "ddx")
TARGET_PREFIX = {"red_flag": "rf.", "ddx": "ddx."}


def _text(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be empty")
    if value != value.strip():
        raise ValueError("must not start or end with whitespace")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("must be NFC-normalised")
    return value


def _finite(value: float) -> float:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("must be a finite number")
    return value


Text = Annotated[StrictStr, AfterValidator(_text)]
FieldCode = Annotated[StrictStr, StringConstraints(pattern=FIELD_CODE_PATTERN)]
TermCode = Annotated[StrictStr, StringConstraints(pattern=TERM_CODE_PATTERN)]
ValueCode = Annotated[StrictStr, StringConstraints(pattern=VALUE_CODE_PATTERN)]
SourceId = Annotated[StrictStr, StringConstraints(pattern=SOURCE_ID_PATTERN)]
RuleId = Annotated[StrictStr, StringConstraints(pattern=RULE_ID_PATTERN)]
PackName = Annotated[StrictStr, StringConstraints(pattern=PACK_NAME_PATTERN)]
LegacyKey = Annotated[StrictStr, StringConstraints(pattern=LEGACY_KEY_PATTERN)]
SynthehrCode = Annotated[StrictStr, StringConstraints(pattern=SYNTHEHR_CODE_PATTERN)]
Number = Annotated[StrictInt | StrictFloat, AfterValidator(_finite)]
Scalar = StrictBool | StrictInt | Annotated[StrictFloat, AfterValidator(_finite)] | StrictStr
Decimals = Annotated[StrictInt, Field(ge=0, le=6)]

Section = Literal["hx", "exam", "vital", "lab"]
FieldType = Literal["number", "int", "bool", "enum"]
Op = Literal["eq", "ne", "lt", "le", "gt", "ge", "in"]
RuleKind = Literal["red_flag", "ddx"]
SourceKind = Literal["original_publication", "guideline", "dataset", "reference_work"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _duplicates(items: Any) -> list[Any]:
    seen: set[Any] = set()
    duplicates: list[Any] = []
    for item in items:
        if item in seen and item not in duplicates:
            duplicates.append(item)
        seen.add(item)
    return duplicates


# --- Sources ---------------------------------------------------------------------------------------------------------


class SourceRef(_Model):
    """Pointer from a rule or a bound to an entry of the source register, with the exact location in the source."""

    ref: SourceId
    locator: Text


_NICE_HOST = re.compile(r"(^|\.)nice\.org\.uk$")
_NICE_NAME = re.compile(r"\bNICE\b|national institute for health and care excellence", re.IGNORECASE)


class Source(_Model):
    """Entry of the source register (D-04): citation, terms of use checked before use, permitted use."""

    id: SourceId
    citation: Text
    url: Annotated[StrictStr, StringConstraints(pattern=r"^https://[^\s/?#]+(?:[/?#]\S*)?$")]
    kind: SourceKind
    terms: Text
    terms_checked_on: Annotated[date, Strict()]
    permitted_use: Text

    @model_validator(mode="after")
    def _no_nice(self) -> Source:
        host = re.split(r"[/?#]", self.url[len("https://") :], maxsplit=1)[0].split(":")[0].lower()
        if _NICE_HOST.search(host) or _NICE_NAME.search(self.citation):
            raise ValueError("NICE material is excluded as a basis for rules (D-04)")
        return self


class SourceRegister(_Model):
    sources: tuple[Source, ...] = ()

    @model_validator(mode="after")
    def _unique(self) -> SourceRegister:
        duplicates = _duplicates(source.id for source in self.sources)
        if duplicates:
            raise ValueError(f"duplicate source ids: {', '.join(duplicates)}")
        return self

    def ids(self) -> frozenset[str]:
        return frozenset(source.id for source in self.sources)


# --- Catalog ---------------------------------------------------------------------------------------------------------


class Bounds(_Model):
    """Physiological bounds of a numeric fact, both inclusive, with their source.

    ``upper`` stays open when the source sets no upper limit (A-65).
    """

    lower: Number
    upper: Number | None = None
    source: SourceRef

    @model_validator(mode="after")
    def _order(self) -> Bounds:
        if self.upper is not None and not self.lower < self.upper:
            raise ValueError("lower must be below upper")
        return self

    def contains(self, value: int | float) -> bool:
        return self.lower <= value and (self.upper is None or value <= self.upper)


class AltUnit(_Model):
    """Alternative unit for display (MR6): ``shown = canonical * factor + offset``, rounded to ``decimals``."""

    unit: Text
    factor: Number
    offset: Number = 0
    decimals: Decimals

    @model_validator(mode="after")
    def _factor(self) -> AltUnit:
        if self.factor == 0:
            raise ValueError("factor must not be zero")
        return self


class FieldLabel(_Model):
    name: Text
    abbr: Text | None = None


class FieldLabels(_Model):
    zh: FieldLabel
    en: FieldLabel
    de: FieldLabel


class TermLabels(_Model):
    zh: Text
    en: Text
    de: Text


class SynthehrSource(_Model):
    """Where the lab profile of a field comes from (D-03): SynthEHR test codes and the unit they are reported in.

    Several codes name the same test in different laboratories (e.g. ``CRE`` and ``CR`` for creatinine). The unit is
    the spelling in the CSV, compared without regard to case.
    """

    codes: Annotated[tuple[SynthehrCode, ...], Field(min_length=1)]
    unit: Text

    @model_validator(mode="after")
    def _unique(self) -> SynthehrSource:
        if _duplicates(self.codes):
            raise ValueError("SynthEHR codes must be unique")
        return self


class FieldDef(_Model):
    """One fact of the catalog. The code prefix is its section; numeric facts carry a canonical unit.

    Numeric fields of a domain also need physiological bounds with a source; the loader checks that. A library field
    that no domain uses may lack bounds while no source gives them (A-65).
    """

    code: FieldCode
    section: Section
    type: FieldType
    unit: Text | None = None
    decimals: Decimals | None = None
    bounds: Bounds | None = None
    values: tuple[ValueCode, ...] = ()
    value_labels: dict[ValueCode, TermLabels] = Field(default_factory=dict)
    labels: FieldLabels
    alt_units: tuple[AltUnit, ...] = ()
    synthehr: SynthehrSource | None = None

    @model_validator(mode="after")
    def _shape(self) -> FieldDef:
        if self.code.split(".", 1)[0] != self.section:
            raise ValueError(f"code {self.code} does not start with its section {self.section!r}")
        numeric = self.type in ("number", "int")
        if self.synthehr is not None and not (numeric and self.section == "lab"):
            raise ValueError("only numeric lab fields have a SynthEHR source")
        if numeric:
            if self.unit is None:
                raise ValueError(f"{self.type} fields need a unit")
            if self.type == "number" and self.decimals is None:
                raise ValueError("number fields need decimals")
            if self.type == "int" and self.decimals is not None:
                raise ValueError("int fields have no decimals")
            if self.values or self.value_labels:
                raise ValueError("only enum fields have values")
            if self.unit in {alt.unit for alt in self.alt_units} or _duplicates(alt.unit for alt in self.alt_units):
                raise ValueError("alternative units must be distinct from each other and from the unit")
        else:
            if self.unit is not None or self.decimals is not None or self.bounds is not None or self.alt_units:
                raise ValueError(f"{self.type} fields have no unit, decimals, bounds or alternative units")
        if self.type == "enum":
            if len(self.values) < 2 or _duplicates(self.values):
                raise ValueError("enum fields need at least two distinct values")
            if set(self.value_labels) != set(self.values):
                raise ValueError("every enum value needs labels, and only enum values have labels")
        elif self.type == "bool" and (self.values or self.value_labels):
            raise ValueError("bool fields have no values")
        return self

    def check_value(self, value: Any) -> str | None:
        """Return why ``value`` is not a valid value of this fact, or ``None`` if it is valid."""
        if self.type == "bool":
            return None if isinstance(value, bool) else "expected true or false"
        if self.type == "enum":
            if isinstance(value, str) and value in self.values:
                return None
            return f"expected one of {', '.join(self.values)}"
        if isinstance(value, bool) or not isinstance(value, int | float):
            return "expected a number"
        if self.type == "int" and not isinstance(value, int):
            return "expected an integer"
        if isinstance(value, float):
            if not math.isfinite(value):
                return "expected a finite number"
            if value == 0 and math.copysign(1.0, value) < 0:
                return "negative zero is not allowed"
            if round(value, self.decimals) != value:
                return f"has more than {self.decimals} decimal places"
        bounds = self.bounds
        if bounds is not None and not bounds.contains(value):
            upper = "open" if bounds.upper is None else bounds.upper
            return f"outside the physiological bounds [{bounds.lower}, {upper}]"
        return None


class Catalog(_Model):
    fields: tuple[FieldDef, ...] = ()
    _index: dict[str, FieldDef] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _unique(self) -> Catalog:
        duplicates = _duplicates(field.code for field in self.fields)
        if duplicates:
            raise ValueError(f"duplicate field codes: {', '.join(duplicates)}")
        return self

    def model_post_init(self, context: Any, /) -> None:
        self._index = {field.code: field for field in self.fields}

    def get(self, code: str) -> FieldDef | None:
        return self._index.get(code)

    def codes(self) -> tuple[str, ...]:
        return tuple(field.code for field in self.fields)


# --- Vocabulary ------------------------------------------------------------------------------------------------------


class Term(_Model):
    code: TermCode
    labels: TermLabels


class Vocabulary(_Model):
    """Allowed answer codes: differential diagnoses (``ddx.*``) and red flags (``rf.*``)."""

    ddx: tuple[Term, ...] = ()
    red_flags: tuple[Term, ...] = ()

    @model_validator(mode="after")
    def _prefixes(self) -> Vocabulary:
        for term in self.ddx:
            if not term.code.startswith("ddx."):
                raise ValueError(f"{term.code} is listed under ddx but is not a ddx code")
        for term in self.red_flags:
            if not term.code.startswith("rf."):
                raise ValueError(f"{term.code} is listed under red_flags but is not an rf code")
        duplicates = _duplicates(term.code for term in (*self.ddx, *self.red_flags))
        if duplicates:
            raise ValueError(f"duplicate codes: {', '.join(duplicates)}")
        return self

    def codes(self, kind: RuleKind) -> frozenset[str]:
        terms = self.red_flags if kind == "red_flag" else self.ddx
        return frozenset(term.code for term in terms)


# --- Conditions ------------------------------------------------------------------------------------------------------


class RefBound(_Model):
    """Threshold taken from the reference range of the fact's lab profile."""

    ref: Literal["lower", "upper"]


class Compare(_Model):
    field: FieldCode
    op: Op
    value: Scalar | tuple[Scalar, ...] | RefBound

    @model_validator(mode="after")
    def _value_matches_op(self) -> Compare:
        if self.op == "in":
            if not isinstance(self.value, tuple) or not self.value:
                raise ValueError("op 'in' needs a non-empty list of values")
            if _duplicates(self.value):
                raise ValueError("op 'in' needs distinct values")
        elif isinstance(self.value, tuple):
            raise ValueError(f"op {self.op!r} needs a single value")
        if isinstance(self.value, RefBound) and self.op not in ORDERED_OPS:
            raise ValueError("reference thresholds are only allowed with lt, le, gt and ge")
        return self


class AllOf(_Model):
    all: Annotated[tuple[Condition, ...], Field(min_length=1)]


class AnyOf(_Model):
    any: Annotated[tuple[Condition, ...], Field(min_length=1)]


class Not(_Model):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    negated: Condition = Field(alias="not")


class AtLeast(_Model):
    at_least: Annotated[StrictInt, Field(ge=1)]
    of: Annotated[tuple[Condition, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _count(self) -> AtLeast:
        if self.at_least > len(self.of):
            raise ValueError(f"at_least {self.at_least} exceeds the {len(self.of)} listed conditions")
        return self


_CONDITION_MARKERS = (("compare", "field"), ("all", "all"), ("any", "any"), ("not", "not"), ("at_least", "at_least"))
_CONDITION_TYPES = {Compare: "compare", AllOf: "all", AnyOf: "any", Not: "not", AtLeast: "at_least"}


def _condition_tag(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for tag, marker in _CONDITION_MARKERS:
            if marker in value:
                return tag
        return None
    return _CONDITION_TYPES.get(type(value))


Condition = Annotated[
    Annotated[Compare, Tag("compare")]
    | Annotated[AllOf, Tag("all")]
    | Annotated[AnyOf, Tag("any")]
    | Annotated[Not, Tag("not")]
    | Annotated[AtLeast, Tag("at_least")],
    Discriminator(
        _condition_tag,
        custom_error_type="condition",
        custom_error_message="expected a comparison (field, op, value) or one of all, any, not, at_least",
    ),
]

for _model in (AllOf, AnyOf, Not, AtLeast):
    _model.model_rebuild()


def children(condition: Condition) -> tuple[Condition, ...]:
    """Direct sub-conditions of a connective; a comparison has none."""
    if isinstance(condition, AllOf):
        return condition.all
    if isinstance(condition, AnyOf):
        return condition.any
    if isinstance(condition, Not):
        return (condition.negated,)
    if isinstance(condition, AtLeast):
        return condition.of
    return ()


def comparisons(condition: Condition) -> Iterator[Compare]:
    """All comparisons of a condition, depth first in document order."""
    if isinstance(condition, Compare):
        yield condition
        return
    for child in children(condition):
        yield from comparisons(child)


def fields_of(condition: Condition) -> frozenset[str]:
    return frozenset(compare.field for compare in comparisons(condition))


def reference_bounds_of(condition: Condition) -> frozenset[tuple[str, str]]:
    """Pairs (field, ``lower``/``upper``) whose reference value the condition compares against."""
    return frozenset(
        (compare.field, compare.value.ref) for compare in comparisons(condition) if isinstance(compare.value, RefBound)
    )


# --- Rules -----------------------------------------------------------------------------------------------------------


class RefRange(_Model):
    """Reference range of a lab test; one side may be open."""

    lower: Number | None = None
    upper: Number | None = None

    @model_validator(mode="after")
    def _order(self) -> RefRange:
        if self.lower is None and self.upper is None:
            raise ValueError("a reference range needs a lower or an upper limit")
        if self.lower is not None and self.upper is not None and not self.lower < self.upper:
            raise ValueError("lower must be below upper")
        return self


class RuleTest(_Model):
    """Test vector of a rule: facts (a subset of ``requires``), reference ranges if the rule uses them, expectation."""

    facts: dict[FieldCode, Scalar]
    refs: dict[FieldCode, RefRange] = Field(default_factory=dict)
    expect: StrictBool | Literal["unknown"]


class Rule(_Model):
    """One rule with exactly one target (A-32), its required fields, a source and at least two test vectors."""

    id: RuleId
    kind: RuleKind
    target: TermCode
    requires: Annotated[tuple[FieldCode, ...], Field(min_length=1)]
    when: Condition
    sources: Annotated[tuple[SourceRef, ...], Field(min_length=1)]
    status: Literal["draft_unreviewed"]
    migrated_from: LegacyKey | None = None
    tests: Annotated[tuple[RuleTest, ...], Field(min_length=2)]

    @model_validator(mode="after")
    def _consistent(self) -> Rule:
        if not self.target.startswith(TARGET_PREFIX[self.kind]):
            raise ValueError(f"a {self.kind} rule needs a target starting with {TARGET_PREFIX[self.kind]!r}")
        if _duplicates(self.requires):
            raise ValueError(f"requires lists fields twice: {', '.join(_duplicates(self.requires))}")
        used = fields_of(self.when)
        missing = sorted(used - set(self.requires))
        extra = sorted(set(self.requires) - used)
        if missing or extra:
            parts = []
            if missing:
                parts.append(f"used in when but not in requires: {', '.join(missing)}")
            if extra:
                parts.append(f"in requires but not used in when: {', '.join(extra)}")
            raise ValueError("requires does not match the condition (" + "; ".join(parts) + ")")
        if _duplicates((source.ref, source.locator) for source in self.sources):
            raise ValueError("sources lists the same reference twice")
        expectations = {test.expect for test in self.tests}
        if True not in expectations or False not in expectations:
            raise ValueError("tests need at least one vector expecting true and one expecting false")
        bounds = reference_bounds_of(self.when)
        ref_fields = {field for field, _ in bounds}
        for index, test in enumerate(self.tests):
            unknown = sorted(set(test.facts) - set(self.requires))
            if unknown:
                raise ValueError(f"tests[{index}] sets fields outside requires: {', '.join(unknown)}")
            if set(test.refs) != ref_fields:
                raise ValueError(
                    f"tests[{index}] must give reference ranges for exactly: {', '.join(sorted(ref_fields)) or '-'}"
                )
            for field, side in bounds:
                if getattr(test.refs[field], side) is None:
                    raise ValueError(f"tests[{index}] needs the {side} reference limit of {field}")
        return self


# --- Migration table -------------------------------------------------------------------------------------------------


class MigrationSource(_Model):
    """The prototype table the rules were migrated from: file, its SHA-256 and the table's name."""

    file: Text
    sha256: Annotated[StrictStr, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    table: Text


class MigrationItem(_Model):
    """One diagnosis text of a legacy entry: the rules it became, or why it became none.

    ``note`` explains a partial migration, e.g. a text naming two conditions of which the source supports one.
    """

    text: Text
    rules: tuple[RuleId, ...] = ()
    reason: Text | None = None
    note: Text | None = None

    @model_validator(mode="after")
    def _outcome(self) -> MigrationItem:
        if bool(self.rules) == (self.reason is not None):
            raise ValueError("an item names either the rules it became or the reason it became none")
        if _duplicates(self.rules):
            raise ValueError("an item lists a rule twice")
        return self


class MigrationEntry(_Model):
    """One key of the prototype table, what its condition means here, and what became of its items."""

    key: LegacyKey
    condition: Text
    items: tuple[MigrationItem, ...] = ()
    reason: Text | None = None
    note: Text | None = None

    @property
    def migrated(self) -> bool:
        return any(item.rules for item in self.items)

    @property
    def rules(self) -> tuple[str, ...]:
        return tuple(rule for item in self.items for rule in item.rules)

    @model_validator(mode="after")
    def _outcome(self) -> MigrationEntry:
        if self.migrated == (self.reason is not None):
            raise ValueError("an entry without any migrated item needs a reason, a migrated entry has none")
        if _duplicates(item.text for item in self.items):
            raise ValueError("an entry lists an item twice")
        return self


class MigrationTable(_Model):
    """``migration.yaml``: every key of the prototype table and the rules it became (A-32, PR-W03)."""

    source: MigrationSource
    entries: Annotated[tuple[MigrationEntry, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _unique(self) -> MigrationTable:
        duplicates = _duplicates(entry.key for entry in self.entries)
        if duplicates:
            raise ValueError(f"duplicate keys: {', '.join(duplicates)}")
        return self


# --- Pack configuration and lab profile references -------------------------------------------------------------------


class DomainSettings(_Model):
    """Settings of a domain pack: case id prefix, complaint and the rules it activates from library packs (A-08)."""

    case_prefix: Annotated[StrictStr, StringConstraints(pattern=r"^[A-Z]{3}$")]
    complaint: ValueCode
    uses: tuple[PackName, ...] = ()
    activate: dict[PackName, Literal["all"] | Annotated[tuple[RuleId, ...], Field(min_length=1)]] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def _activation(self) -> DomainSettings:
        if _duplicates(self.uses):
            raise ValueError("uses lists a pack twice")
        if set(self.activate) != set(self.uses):
            raise ValueError("activate needs exactly one entry per used pack")
        for pack, ids in self.activate.items():
            if isinstance(ids, tuple) and _duplicates(ids):
                raise ValueError(f"activate.{pack} lists a rule twice")
        return self


class PackConfig(_Model):
    """``pack.yaml``: a domain pack produces cases; a library pack only provides rules for domains."""

    pack: PackName
    kind: Literal["domain", "library"]
    domain: DomainSettings | None = None

    @model_validator(mode="after")
    def _settings(self) -> PackConfig:
        if (self.kind == "domain") != (self.domain is not None):
            raise ValueError("domain packs need domain settings, library packs must not have them")
        return self


class ProfileReference(BaseModel):
    """The part of a lab profile that rules need: fact code, unit and reference range. Other keys are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    fact_code: FieldCode
    unit: Text
    reference: RefRange


# --- Loaded domain ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Domain:
    """A domain ready for inference: effective catalog and vocabulary, active rules and reference ranges."""

    name: str
    case_prefix: str
    complaint: str
    catalog: Catalog
    vocabulary: Vocabulary
    sources: SourceRegister
    rules: tuple[Rule, ...]
    references: Mapping[str, RefRange]

    def fact_problems(self, facts: Mapping[str, Any]) -> list[str]:
        """Why the given facts are not valid for this domain; empty if they are."""
        problems = []
        for code in sorted(facts):
            field = self.catalog.get(code)
            if field is None:
                problems.append(f"{code}: unknown fact code")
                continue
            problem = field.check_value(facts[code])
            if problem:
                problems.append(f"{code}: {problem}")
        return problems
