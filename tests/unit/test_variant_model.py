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
MR2: dict[str, Any] = {
    **MR1,
    "variant_id": "FEV-000001-MR2-1",
    "mr": "MR2",
    "key": {**KEY, "required_questions": []},
    "expectation": {"kind": "invariant", "compare": ["decision", "ddx"]},
}
MR4: dict[str, Any] = {
    **MR5,
    "variant_id": "FEV-000001-MR4-1",
    "mr": "MR4",
    "change": {"kind": "add_facts", "facts": ["hx.visual_aid"]},
}
MR6: dict[str, Any] = {
    **MR5,
    "variant_id": "FEV-000001-MR6-1",
    "mr": "MR6",
    "change": {"kind": "change_notation", "units": {"vital.resp_rate": "/s"}, "abbreviations": True},
}
MR7: dict[str, Any] = {
    **MR5,
    "variant_id": "FEV-000001-MR7-1",
    "mr": "MR7",
    "change": {"kind": "insert_contradiction", "template": "FEV-MR7-001", "field": "vital.sbp"},
    "expectation": {"kind": "absolute", "contradictions_include": ["vital.sbp"]},
}


@pytest.mark.parametrize("data", [MR1, MR2, MR3, MR4, MR5, MR6, MR7])
def test_valid_variants(data):
    variant = Variant.model_validate(data)
    assert variant.to_json() == json.loads(json.dumps(data))
    jsonschema.Draft202012Validator(variant_json_schema()).validate(data)


@pytest.mark.parametrize(
    ("base", "changes", "message"),
    [
        (MR1, {"variant_id": "FEV-000002-MR1-1"}, "variant_id must start with FEV-000001-MR1-"),
        (MR1, {"mr": "MR8", "variant_id": "FEV-000001-MR8-1"}, "MR8 is not built yet"),
        (MR1, {"change": {"kind": "permute_sections", "order": ["lab", "hx", "exam", "vital"]}}, "remove_field"),
        (MR1, {"facts": {"vital.sbp": 90}}, "removed field must not remain"),
        (MR1, {"expectation": {"kind": "invariant", "compare": ["decision"]}}, "MR1 and MR7 have an absolute"),
        (MR1, {"expectation": {"kind": "absolute", "questions_include": ["vital.sbp"]}}, "MR1 expects a decision"),
        (MR1, {"expectation": {**MR1["expectation"], "contradictions_include": ["vital.sbp"]}}, "no contradictions"),
        (MR1, {"expectation": {"kind": "absolute"}}, "needs at least one target"),
        (MR1, {"render": {"order": ["lab", "hx", "exam", "vital"]}}, "only MR3 changes the order"),
        (MR3, {"change": {"kind": "permute_sections", "order": ["hx", "exam", "vital", "lab"]}}, "other than"),
        (MR3, {"change": {"kind": "permute_sections", "order": ["hx", "hx", "vital", "lab"]}}, "permutation"),
        (MR3, {"render": {"order": ["vital", "hx", "exam", "lab"]}}, "render order must be the permuted order"),
        (MR3, {"render": {"order": ["vital", "vital", "exam", "lab"]}}, "permutation"),
        (MR3, {"expectation": {"kind": "absolute", "decision": "ask"}}, "MR1 and MR7 have an absolute"),
        (
            MR3,
            {"expectation": {"kind": "invariant", "compare": ["decision", "ddx"]}},
            "MR3 compares decision, ddx, red",
        ),
        (MR2, {"expectation": MR3["expectation"]}, "MR2 compares decision, ddx"),
        (MR2, {"change": {"kind": "add_facts", "facts": ["hx.visual_aid"]}}, "MR2 needs a change of kind remove_field"),
        (MR4, {"change": {"kind": "add_facts", "facts": []}}, "at least 1 item"),
        (MR4, {"change": {"kind": "add_facts", "facts": ["hx.a", "hx.a"]}}, "must be distinct"),
        (MR4, {"change": {"kind": "add_facts", "facts": ["history.a"]}}, "String should match pattern"),
        (MR6, {"change": {**MR6["change"], "units": {}, "abbreviations": False}}, "alternative unit or abbreviations"),
        (MR6, {"change": {**MR6["change"], "units": {"lab.crp_mg_l": "mg/dL"}}}, "converts only facts of the variant"),
        (MR6, {"change": {**MR6["change"], "units": {"crp": "mg/dL"}}}, "String should match pattern"),
        (MR6, {"render": {"order": ["lab", "hx", "exam", "vital"]}}, "only MR3 changes the order"),
        (MR7, {"change": {**MR7["change"], "field": "hx.cough"}}, "contradicts a fact of the variant"),
        (MR7, {"expectation": {"kind": "absolute", "contradictions_include": ["vital.resp_rate"]}}, "MR7 expects"),
        (MR7, {"expectation": {**MR7["expectation"], "decision": "ask"}}, "MR7 expects"),
        (MR7, {"expectation": MR3["expectation"]}, "MR1 and MR7 have an absolute"),
        (MR7, {"change": {**MR7["change"], "template": "bad id"}}, "String should match pattern"),
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
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate({**MR6, "change": {**MR6["change"], "units": {"x": "°F"}}})


def test_absolute_expectations_keep_only_their_targets():
    """KONZEPT 4.7: only the targets a relation sets appear in the JSON, so MR1 variants of v0.1 keep their bytes."""
    assert Variant.model_validate(MR1).to_json()["expectation"] == MR1["expectation"]
    assert Variant.model_validate(MR7).to_json()["expectation"] == {
        "kind": "absolute",
        "contradictions_include": ["vital.sbp"],
    }
