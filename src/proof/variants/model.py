"""Variant model (PR-M00, PR-F06, KONZEPT 4.7): a changed copy of a base case with its machine-readable expectation.

A variant has exactly the fields of KONZEPT 4.7: ``variant_id``, ``case_id``, ``mr``, ``variant_seed``, ``change``,
``facts``, ``render``, ``key`` and ``expectation``. Its content does not depend on the language: every variant is
rendered in zh, en and de with the same facts and options, so the three languages see identical items (A-74).

The change says what differs from the base case (KONZEPT 4.7):

- ``remove_field`` (MR1, MR2): one fact left out; MR1 takes a critical one, MR2 one whose ablation changes nothing;
- ``permute_sections`` (MR3): the sections in another order;
- ``language_pair`` (MR5): two languages of the base case;
- ``add_facts`` (MR4): irrelevant facts of the catalog shown as extra lines;
- ``change_notation`` (MR6): facts shown in alternative units, names shown as abbreviations;
- ``insert_contradiction`` (MR7): a statement from the catalog that contradicts a fact.

``facts`` are the coded facts the key is computed from; MR4, MR6 and MR7 keep those of the base case and change only
the text. ``render`` holds the order of the sections.

Expectations come in two kinds (A-14):

- ``absolute``: target values; only the targets a relation sets are present, e.g. ``decision: ask`` and
  ``questions_include: [vital.resp_rate]`` (MR1) or ``contradictions_include: [vital.temp_c]`` (MR7);
- ``invariant``: the answer must equal the reference answer in the listed fields. For MR2, MR3, MR4 and MR6 the
  reference is the answer to the base case in the same language (MR2 compares decision and diagnoses only); for MR5
  it is the answer to the base case in the other language of the pair.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_serializer,
    model_validator,
)

from proof.cases.model import CASE_ID_PATTERN
from proof_rules.engine import Determinability, VariantKey
from proof_rules.model import FieldCode, RuleId, Scalar, Text

MR = Literal["MR1", "MR2", "MR3", "MR4", "MR5", "MR6", "MR7", "MR8"]
Section = Literal["hx", "exam", "vital", "lab"]
Language = Literal["zh", "en", "de"]
Compared = Literal["decision", "ddx", "red_flags", "questions"]
VARIANT_ID_PATTERN = r"^[A-Z]{3}-[0-9]{6}-MR[1-8]-[0-9a-z-]+$"
DEFAULT_ORDER: tuple[Section, ...] = ("hx", "exam", "vital", "lab")
# A-14: "unchanged" means equal decision and equal sets of diagnoses, red flags and questions. MR2 keeps decision and
# diagnoses only; a missing fact may change the questions and, through the key, the red flags a model can see.
UNCHANGED: tuple[Compared, ...] = ("decision", "ddx", "red_flags", "questions")
DECISION_AND_DDX: tuple[Compared, ...] = ("decision", "ddx")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Changes ---------------------------------------------------------------------------------------------------------


class RemoveField(_Model):
    """MR1 and MR2: one fact of the base case is left out (critical for MR1, not critical for MR2)."""

    kind: Literal["remove_field"]
    field: FieldCode


class PermuteSections(_Model):
    """MR3: the four sections appear in another order; the facts stay the same."""

    kind: Literal["permute_sections"]
    order: tuple[Section, Section, Section, Section]

    @model_validator(mode="after")
    def _permutation(self) -> PermuteSections:
        if sorted(self.order) != sorted(DEFAULT_ORDER):
            raise ValueError("order must be a permutation of hx, exam, vital, lab")
        if self.order == DEFAULT_ORDER:
            raise ValueError("MR3 needs an order other than the default")
        return self


class LanguagePair(_Model):
    """MR5: the base case in two languages; no new request, the two base answers are compared (A-37)."""

    kind: Literal["language_pair"]
    langs: tuple[Language, Language]

    @model_validator(mode="after")
    def _distinct(self) -> LanguagePair:
        if self.langs[0] == self.langs[1]:
            raise ValueError("a language pair needs two different languages")
        return self


class AddFacts(_Model):
    """MR4: irrelevant facts of the catalog are added as lines of their sections; the coded facts stay the same."""

    kind: Literal["add_facts"]
    facts: Annotated[tuple[FieldCode, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _distinct(self) -> AddFacts:
        if len(set(self.facts)) != len(self.facts):
            raise ValueError("irrelevant facts must be distinct")
        return self


class ChangeNotation(_Model):
    """MR6: facts shown in alternative units of the catalog and, if set, names shown as their abbreviations."""

    kind: Literal["change_notation"]
    units: Annotated[dict[FieldCode, Text], Field(json_schema_extra={"additionalProperties": False})]
    abbreviations: StrictBool

    @model_validator(mode="after")
    def _changes_something(self) -> ChangeNotation:
        if not self.units and not self.abbreviations:
            raise ValueError("MR6 needs an alternative unit or abbreviations")
        return self


class InsertContradiction(_Model):
    """MR7: the statement of a contradiction template is added; it contradicts the fact ``field``."""

    kind: Literal["insert_contradiction"]
    template: RuleId
    field: FieldCode


Change = Annotated[
    RemoveField | PermuteSections | LanguagePair | AddFacts | ChangeNotation | InsertContradiction,
    Field(discriminator="kind"),
]

# Which change each relation uses.
CHANGE_OF_MR: dict[str, str] = {
    "MR1": "remove_field",
    "MR2": "remove_field",
    "MR3": "permute_sections",
    "MR4": "add_facts",
    "MR5": "language_pair",
    "MR6": "change_notation",
    "MR7": "insert_contradiction",
}
# Relations checked against an absolute expectation (A-14); the others are invariant, comparing these fields.
ABSOLUTE_MRS: frozenset[str] = frozenset({"MR1", "MR7"})
COMPARED_OF_MR: dict[str, tuple[Compared, ...]] = {
    "MR2": DECISION_AND_DDX,
    "MR3": UNCHANGED,
    "MR4": UNCHANGED,
    "MR5": UNCHANGED,
    "MR6": UNCHANGED,
}


# --- Rendering options and expectations ------------------------------------------------------------------------------


class RenderOptions(_Model):
    """How the variant is rendered in every language: the order of the sections."""

    order: tuple[Section, Section, Section, Section] = DEFAULT_ORDER

    @model_validator(mode="after")
    def _permutation(self) -> RenderOptions:
        if sorted(self.order) != sorted(DEFAULT_ORDER):
            raise ValueError("order must be a permutation of hx, exam, vital, lab")
        return self


class AbsoluteExpectation(_Model):
    """Target values the answer must meet; a target that is not set is left out of the JSON."""

    kind: Literal["absolute"]
    decision: Determinability | None = None
    questions_include: tuple[FieldCode, ...] = ()
    contradictions_include: tuple[FieldCode, ...] = ()

    @model_validator(mode="after")
    def _has_target(self) -> AbsoluteExpectation:
        if self.decision is None and not self.questions_include and not self.contradictions_include:
            raise ValueError("an absolute expectation needs at least one target")
        return self

    @model_serializer(mode="wrap")
    def _set_targets_only(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        return {key: value for key, value in data.items() if value is not None and value != [] and value != ()}


class InvariantExpectation(_Model):
    """The answer must equal the reference answer in these fields (sets for the lists)."""

    kind: Literal["invariant"]
    compare: Annotated[tuple[Compared, ...], Field(min_length=1)]


Expectation = Annotated[AbsoluteExpectation | InvariantExpectation, Field(discriminator="kind")]


# --- Variant ---------------------------------------------------------------------------------------------------------


class Variant(_Model):
    """One variant of a base case (KONZEPT 4.7)."""

    variant_id: Annotated[str, StringConstraints(pattern=VARIANT_ID_PATTERN)]
    case_id: Annotated[str, StringConstraints(pattern=CASE_ID_PATTERN)]
    mr: MR
    variant_seed: Annotated[StrictInt, Field(ge=0)]
    change: Change
    facts: Annotated[dict[FieldCode, Scalar], Field(min_length=1, json_schema_extra={"additionalProperties": False})]
    render: RenderOptions
    key: VariantKey
    expectation: Expectation

    @model_validator(mode="after")
    def _consistent(self) -> Variant:
        if not self.variant_id.startswith(f"{self.case_id}-{self.mr}-"):
            raise ValueError(f"variant_id must start with {self.case_id}-{self.mr}-")
        expected_change = CHANGE_OF_MR.get(self.mr)
        if expected_change is None:
            raise ValueError(f"{self.mr} is not built yet")
        if self.change.kind != expected_change:
            raise ValueError(f"{self.mr} needs a change of kind {expected_change}")
        if isinstance(self.change, RemoveField) and self.change.field in self.facts:
            raise ValueError("the removed field must not remain in the facts")
        if isinstance(self.change, PermuteSections) and self.render.order != self.change.order:
            raise ValueError("the render order must be the permuted order")
        if not isinstance(self.change, PermuteSections) and self.render.order != DEFAULT_ORDER:
            raise ValueError("only MR3 changes the order of the sections")
        if isinstance(self.change, ChangeNotation) and not set(self.change.units) <= set(self.facts):
            raise ValueError("MR6 converts only facts of the variant")
        if isinstance(self.change, InsertContradiction) and self.change.field not in self.facts:
            raise ValueError("MR7 contradicts a fact of the variant")
        expectation = self.expectation
        if isinstance(expectation, AbsoluteExpectation) != (self.mr in ABSOLUTE_MRS):
            raise ValueError("MR1 and MR7 have an absolute expectation, the other relations an invariant one")
        if isinstance(expectation, InvariantExpectation) and expectation.compare != COMPARED_OF_MR[self.mr]:
            raise ValueError(f"{self.mr} compares {', '.join(COMPARED_OF_MR[self.mr])} (A-14)")
        if self.mr == "MR1" and (expectation.decision is None or expectation.contradictions_include):
            raise ValueError("MR1 expects a decision and questions, no contradictions")
        if isinstance(self.change, InsertContradiction) and expectation != AbsoluteExpectation(
            kind="absolute", contradictions_include=(self.change.field,)
        ):
            raise ValueError("MR7 expects the contradicted field among the contradictions and nothing else")
        return self

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def variant_json_schema() -> dict[str, Any]:
    """JSON Schema (draft 2020-12) of a variant, generated from :class:`Variant`."""
    schema = Variant.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Proof variant"
    schema["description"] = (
        "A variant of a Proof base case (metamorphic relation) with its recomputed key and machine-readable "
        "expectation. Evaluation tool and open dataset, not a medical device."
    )
    return schema
