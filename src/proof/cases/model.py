"""Case schema (PR-F01, PR-K02): exactly the fields of the PRD example (A-34), validated with Pydantic.

A case is a set of coded facts; it holds no free text (PR-K01). Its key is computed by the rule set (PR-K04). The JSON
Schema in ``schema/case.schema.json`` is generated from :class:`Case` (:func:`case_json_schema`).
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, StringConstraints, model_validator

from proof_rules.engine import Key
from proof_rules.model import VALUE_CODE_PATTERN, FieldCode, Scalar

CASE_ID_PATTERN = r"^[A-Z]{3}-[0-9]{6}$"
MAX_SEED = 999_999
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

Sex = Literal["f", "m"]


def case_id(prefix: str, seed: int) -> str:
    """The id of a case: domain prefix and six-digit seed, e.g. ``FEV-000123`` for seed 123 (A-06)."""
    if not 0 <= seed <= MAX_SEED:
        raise ValueError(f"seed {seed} is outside 0..{MAX_SEED}")
    return f"{prefix}-{seed:06d}"


class Patient(BaseModel):
    """Age in years and sex of the synthetic patient."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    age: Annotated[StrictInt, Field(ge=0)]
    sex: Sex


class Case(BaseModel):
    """One base case: id, seed, patient, complaint, facts and the key computed from them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: Annotated[StrictStr, StringConstraints(pattern=CASE_ID_PATTERN)]
    seed: Annotated[StrictInt, Field(ge=0, le=MAX_SEED)]
    patient: Patient
    complaint: Annotated[StrictStr, StringConstraints(pattern=VALUE_CODE_PATTERN)]
    # Keys are fact codes; the schema rejects any other key, as the model does.
    facts: Annotated[dict[FieldCode, Scalar], Field(min_length=1, json_schema_extra={"additionalProperties": False})]
    key: Key

    @model_validator(mode="after")
    def _id_matches_seed(self) -> Case:
        if int(self.case_id[-6:]) != self.seed:
            raise ValueError(f"case_id {self.case_id} does not end with the seed {self.seed:06d}")
        return self

    def to_json(self) -> dict[str, Any]:
        """The case as plain JSON data with lists as in the key (sorted)."""
        return self.model_dump(mode="json")


def case_json_schema() -> dict[str, Any]:
    """JSON Schema (draft 2020-12) of a case, generated from :class:`Case`."""
    schema = Case.model_json_schema()
    schema["$schema"] = JSON_SCHEMA_DIALECT
    schema["title"] = "Proof case"
    schema["description"] = (
        "A synthetic base case of Proof: coded facts and the key computed by the rule set. Evaluation tool and open "
        "dataset, not a medical device."
    )
    return schema


def schema_text(schema: dict[str, Any]) -> str:
    """Stable text form of a JSON Schema file: sorted keys, two-space indent, final newline."""
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
