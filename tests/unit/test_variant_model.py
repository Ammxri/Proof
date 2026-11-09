"""Variant model (PR-M00, KONZEPT 4.7, A-74)."""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError

from proof.variants.model import Variant, variant_json_schema

KEY = {
    "determinability": "ask",
    "red_flags": [],
    "critical_fields": [],
    "ddx": [],
    "required_questions": ["vital.sbp"],
}
MR1: dict[str, Any] = {
    "variant_id": "FEV-000001-MR1-1",
    "case_id": "FEV-000001",
    "mr": "MR1",
    "variant_seed": 1,
    "change": {"kind": "remove_field", "field": "vital.sbp"},
    "facts": {"vital.resp_rate": 27},
    "render": {"order": ["hx", "exam", "vital", "lab"]},
    "key": KEY,
    "expectation": {"kind": "absolute", "decision": "ask", "questions_include": ["vital.sbp"]},
}
MR3: dict[str, Any] = {
    **MR1,
    "variant_id": "FEV-000001-MR3-1",
    "mr": "MR3",
    "change": {"kind": "permute_sections", "order": ["lab", "hx", "exam", "vital"]},
    "facts": {"vital.resp_rate": 27, "vital.sbp": 90},
    "render": {"order": ["lab", "hx", "exam", "vital"]},
    "key": {**KEY, "required_questions": []},
    "expectation": {"kind": "invariant", "compare": ["decision", "ddx", "red_flags", "questions"]},
}
MR5: dict[str, Any] = {
    **MR3,
    "variant_id": "FEV-000001-MR5-zh-en",
    "mr": "MR5",
    "change": {"kind": "language_pair", "langs": ["zh", "en"]},
    "render": {"order": ["hx", "exam", "vital", "lab"]},
}


@pytest.mark.parametrize("data", [MR1, MR3, MR5])
def test_valid_variants(data):
    variant = Variant.model_validate(data)
    assert variant.to_json() == json.loads(json.dumps(data))
    jsonschema.Draft202012Validator(variant_json_schema()).validate(data)


@pytest.mark.parametrize(
    ("base", "changes", "message"),
    [
        (MR1, {"variant_id": "FEV-000002-MR1-1"}, "variant_id must start with FEV-000001-MR1-"),
        (MR1, {"mr": "MR2", "variant_id": "FEV-000001-MR2-1"}, "MR2 is not built yet"),
        (MR1, {"change": {"kind": "permute_sections", "order": ["lab", "hx", "exam", "vital"]}}, "remove_field"),
        (MR1, {"facts": {"vital.sbp": 90}}, "removed field must not remain"),
        (MR1, {"expectation": {"kind": "invariant", "compare": ["decision"]}}, "MR1 has an absolute expectation"),
        (MR1, {"render": {"order": ["lab", "hx", "exam", "vital"]}}, "only MR3 changes the order"),
        (MR3, {"change": {"kind": "permute_sections", "order": ["hx", "exam", "vital", "lab"]}}, "other than"),
        (MR3, {"change": {"kind": "permute_sections", "order": ["hx", "hx", "vital", "lab"]}}, "permutation"),
        (MR3, {"render": {"order": ["vital", "hx", "exam", "lab"]}}, "render order must be the permuted order"),
        (MR3, {"render": {"order": ["vital", "vital", "exam", "lab"]}}, "permutation"),
        (MR3, {"expectation": {"kind": "absolute", "decision": "ask"}}, "MR1 has an absolute expectation"),
        (MR3, {"expectation": {"kind": "invariant", "compare": []}}, "at least 1 item"),
        (MR5, {"change": {"kind": "language_pair", "langs": ["zh", "zh"]}}, "two different languages"),
        (MR5, {"change": {"kind": "language_pair", "langs": ["zh", "fr"]}}, "Input should be"),
        (MR5, {"extra": 1}, "Extra inputs are not permitted"),
        (MR5, {"variant_seed": -1}, "greater than or equal to 0"),
    ],
)
def test_invalid_variants_are_rejected(base, changes, message):
    with pytest.raises(ValidationError, match=message):
        Variant.model_validate({**base, **changes})


def test_the_schema_is_closed():
    schema = variant_json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["facts"]["additionalProperties"] is False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate({**MR1, "extra": 1})
