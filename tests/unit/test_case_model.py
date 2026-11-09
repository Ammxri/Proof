"""Case schema (PR-F01, PR-K02, A-34): Pydantic model and the generated JSON Schema."""

from __future__ import annotations

import importlib.util
import json
import sys
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError

from proof.cases.model import Case, case_id, case_json_schema, schema_text

PRD_CASE: dict[str, Any] = {
    "case_id": "FEV-000123",
    "seed": 123,
    "patient": {"age": 67, "sex": "f"},
    "complaint": "fever",
    "facts": {"vital.temp_c": 39.2, "vital.resp_rate": 24, "vital.mental_status": "altered", "hx.cough": True},
    "key": {
        "determinability": "refer_urgent",
        "red_flags": ["rf.qsofa_ge2"],
        "critical_fields": ["vital.mental_status", "vital.resp_rate"],
        "ddx": ["ddx.pneumonia", "ddx.sepsis"],
    },
}


def _changed(path: str, value: Any) -> dict[str, Any]:
    data = json.loads(json.dumps(PRD_CASE))
    *parents, last = path.split("/")
    target = data
    for part in parents:
        target = target[part]
    if value is KeyError:
        del target[last]
    else:
        target[last] = value
    return data


@pytest.fixture(scope="module")
def validator():
    return jsonschema.Draft202012Validator(case_json_schema())


def test_case_id_is_prefix_and_six_digit_seed():
    assert case_id("FEV", 123) == "FEV-000123"
    assert case_id("FEV", 999999) == "FEV-999999"
    for seed in (-1, 1_000_000):
        with pytest.raises(ValueError, match="outside"):
            case_id("FEV", seed)


def test_the_prd_case_has_exactly_the_prd_fields(validator):
    case = Case.model_validate(PRD_CASE)
    assert case.to_json() == PRD_CASE
    assert set(Case.model_fields) == {"case_id", "seed", "patient", "complaint", "facts", "key"}
    assert set(case.key.model_dump()) == {"determinability", "red_flags", "critical_fields", "ddx"}
    validator.validate(PRD_CASE)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("case_id", "FEV-000124", "does not end with the seed"),
        ("case_id", "FEV-123", "String should match pattern"),
        ("seed", 1_000_000, "less than or equal to 999999"),
        ("seed", "123", "Input should be a valid integer"),
        ("patient/sex", "x", "Input should be 'f' or 'm'"),
        ("patient/age", -1, "greater than or equal to 0"),
        ("patient/name", "Anna", "Extra inputs are not permitted"),
        ("complaint", "Fever", "String should match pattern"),
        ("facts", {}, "at least 1 item"),
        ("facts/Temperatur", 39.2, "String should match pattern"),
        ("facts/vital.temp_c", None, "Input should be"),
        ("key/ddx", ["ddx.sepsis", "ddx.pneumonia"], "sorted and free of duplicates"),
        ("key/ddx", ["rf.qsofa_ge2"], "String should match pattern"),
        ("key/red_flags", ["ddx.sepsis"], "String should match pattern"),
        ("key/determinability", "maybe", "Input should be"),
        ("key", KeyError, "Field required"),
        ("text", "free text", "Extra inputs are not permitted"),
    ],
)
def test_the_model_rejects_invalid_cases(path, value, message):
    with pytest.raises(ValidationError, match=message):
        Case.model_validate(_changed(path, value))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("case_id", "FEV-123"),
        ("patient/sex", "x"),
        ("patient/name", "Anna"),
        ("facts/Temperatur", 39.2),
        ("facts/vital.temp_c", None),
        ("facts", {}),
        ("key/red_flags", ["ddx.sepsis"]),
        ("key", KeyError),
        ("text", "free text"),
    ],
)
def test_the_json_schema_rejects_invalid_cases(validator, path, value):
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(_changed(path, value))


def test_the_schema_is_draft_2020_12_and_closed():
    schema = case_json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["facts"]["additionalProperties"] is False
    for name in ("Key", "Patient"):
        assert schema["$defs"][name]["additionalProperties"] is False


def test_schema_text_is_stable():
    text = schema_text(case_json_schema())
    assert text.endswith("}\n")
    assert text == schema_text(json.loads(text))


@pytest.fixture(scope="module")
def export_schemas(request):
    path = request.config.rootpath / "tools" / "export_schemas.py"
    spec = importlib.util.spec_from_file_location("export_schemas", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_schemas"] = module
    spec.loader.exec_module(module)
    return module


def test_committed_schema_is_up_to_date(export_schemas, repo_root):
    assert repo_root / "schema" == export_schemas.OUTPUT
    assert export_schemas.main(["--check"]) == 0
    committed = (repo_root / "schema" / "case.schema.json").read_bytes().decode("utf-8")
    assert committed == schema_text(case_json_schema())


def test_export_tool_writes_and_detects_stale_files(export_schemas, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(export_schemas, "OUTPUT", tmp_path / "schema")
    assert export_schemas.main(["--check"]) == 1
    assert export_schemas.main([]) == 0
    assert export_schemas.main(["--check"]) == 0
    (tmp_path / "schema" / "case.schema.json").write_text("{}\n", encoding="utf-8")
    assert export_schemas.main(["--check"]) == 1
    assert "out of date" in capsys.readouterr().err
    assert export_schemas.main(["--bogus"]) == 2
