"""Variant model (PR-M00, PR-F06, KONZEPT 4.7): a changed copy of a base case with its machine-readable expectation.

A variant has exactly the fields of KONZEPT 4.7: ``variant_id``, ``case_id``, ``mr``, ``variant_seed``, ``change``,
``facts``, ``render``, ``key`` and ``expectation``. Its content does not depend on the language: every variant is
rendered in zh, en and de with the same facts and options, so the three languages see identical items (A-74).

Expectations come in two kinds (A-14):

- ``absolute``: target values, e.g. ``decision: ask`` and ``questions_include: [vital.resp_rate]`` (MR1);
- ``invariant``: the answer must equal the reference answer in the listed fields. For MR3 the reference is the answer
  to the base case in the same language; for MR5 it is the answer to the base case in the other language of the pair.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

from proof.cases.model import CASE_ID_PATTERN
from proof_rules.engine import Determinability, VariantKey
from proof_rules.model import FieldCode, Scalar

MR = Literal["MR1", "MR2", "MR3", "MR4", "MR5", "MR6", "MR7", "MR8"]
Section = Literal["hx", "exam", "vital", "lab"]
Language = Literal["zh", "en", "de"]
Compared = Literal["decision", "ddx", "red_flags", "questions"]
VARIANT_ID_PATTERN = r"^[A-Z]{3}-[0-9]{6}-MR[1-8]-[0-9a-z-]+$"
DEFAULT_ORDER: tuple[Section, ...] = ("hx", "exam", "vital", "lab")
# A-14: "unchanged" means equal decision and equal sets of diagnoses, red flags and questions.
UNCHANGED: tuple[Compared, ...] = ("decision", "ddx", "red_flags", "questions")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Changes ---------------------------------------------------------------------------------------------------------


class RemoveField(_Model):
    """MR1 and MR2: one fact of the base case is left out."""

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


Change = Annotated[RemoveField | PermuteSections | LanguagePair, Field(discriminator="kind")]

# Which change each relation uses.
CHANGE_OF_MR: dict[str, str] = {"MR1": "remove_field", "MR3": "permute_sections", "MR5": "language_pair"}


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
    """Target values the answer must meet."""

    kind: Literal["absolute"]
    decision: Determinability
    questions_include: tuple[FieldCode, ...] = ()


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
        absolute = isinstance(self.expectation, AbsoluteExpectation)
        if absolute != (self.mr == "MR1"):
            raise ValueError("MR1 has an absolute expectation, MR3 and MR5 an invariant one")
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
