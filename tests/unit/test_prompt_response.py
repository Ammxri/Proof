"""System prompt (A-12) and answer protocol (PR-P01, A-13)."""

from __future__ import annotations

import json

import jsonschema
import pytest

from proof.core.i18n import LANGUAGES
from proof.render.prompt import messages, system_prompt
from proof.scoring.response import AllowedCodes, Response, parse_response, response_json_schema
from proof_rules import loader

KEYS = ("decision", "ddx", "questions", "red_flags", "contradictions", "rationale")
VALID = {
    "decision": "refer_urgent",
    "ddx": ["ddx.pneumonia", "ddx.sepsis"],
    "questions": ["vital.sbp"],
    "red_flags": ["rf.qsofa_ge2"],
    "contradictions": [],
    "rationale": "qSOFA 3.",
}


@pytest.fixture(scope="module")
def fever():
    return loader.load_domain("fever")


@pytest.fixture(scope="module")
def allowed(fever) -> AllowedCodes:
    return AllowedCodes.of(fever)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_prompt_names_every_allowed_code_and_the_format(fever, lang):
    """PR-P01: the prompt names the allowed codes; A-12: one fixed prompt per language."""
    prompt = system_prompt(fever, lang)
    for term in (*fever.vocabulary.ddx, *fever.vocabulary.red_flags):
        assert f"- {term.code}" in prompt and getattr(term.labels, lang) in prompt
    for code in fever.catalog.codes():
        assert f"- {code}" in prompt
    for key in KEYS:
        assert f'"{key}"' in prompt
    for decision in ("answer", "ask", "refer_urgent"):
        assert f'"{decision}"' in prompt
    assert prompt == system_prompt(fever, lang)
    assert "\r" not in prompt and prompt.endswith("\n")


def test_the_prompt_does_not_reveal_thresholds(fever):
    """The prompt lists codes only; criteria and thresholds stay in the rules."""
    for lang in LANGUAGES:
        prompt = system_prompt(fever, lang)
        for threshold in ("38.0", "38,0", "≥ 22", "≤ 100", "100 mmHg"):
            assert threshold not in prompt


def test_messages_are_system_then_user():
    assert messages("S", "C") == [{"role": "system", "content": "S"}, {"role": "user", "content": "C"}]


def test_a_valid_answer_is_accepted(allowed):
    parsed = parse_response(json.dumps(VALID, ensure_ascii=False), allowed)
    assert parsed.valid and parsed.problems == ()
    assert parsed.response == Response(**{key: tuple(v) if isinstance(v, list) else v for key, v in VALID.items()})
    # Whitespace at the edges is not part of the answer (A-13); repeated codes are still allowed codes.
    spaced = "\n  " + json.dumps({**VALID, "ddx": ["ddx.sepsis", "ddx.sepsis"]}) + "\n"
    assert parse_response(spaced, allowed).valid


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("```json\n" + json.dumps(VALID) + "\n```", "not a JSON object"),
        ("Answer: " + json.dumps(VALID), "not a JSON object"),
        ("", "not a JSON object"),
        ("[" + json.dumps(VALID) + "]", "not a JSON object"),
        (json.dumps(VALID) + " Thanks", "not valid JSON"),
        ('{"decision": "ask", "decision": "answer"}', "duplicate key"),
        ('{"decision": NaN}', "not valid JSON"),
        (json.dumps({key: value for key, value in VALID.items() if key != "rationale"}), "rationale: Field required"),
        (json.dumps({**VALID, "confidence": 0.9}), "Extra inputs are not permitted"),
        (json.dumps({**VALID, "decision": "refer"}), "decision: Input should be"),
        (json.dumps({**VALID, "ddx": "ddx.sepsis"}), "ddx: expected a list"),
        (json.dumps({**VALID, "rationale": 3}), "rationale: Input should be a valid string"),
        (json.dumps({**VALID, "ddx": ["Pneumonie"]}), "String should match pattern"),
        (json.dumps({**VALID, "ddx": ["ddx.influenza"]}), "ddx: codes not allowed in this domain: ddx.influenza"),
        (json.dumps({**VALID, "red_flags": ["rf.shock"]}), "red_flags: codes not allowed"),
        (json.dumps({**VALID, "questions": ["vital.spo2"]}), "questions: codes not allowed"),
        (json.dumps({**VALID, "contradictions": ["lab.ldl_mmol_l"]}), "contradictions: codes not allowed"),
    ],
)
def test_invalid_answers_are_rejected_without_repair(allowed, text, message):
    parsed = parse_response(text, allowed)
    assert not parsed.valid and parsed.response is None
    assert message in "\n".join(parsed.problems)


def test_allowed_codes_come_from_the_domain(fever, allowed):
    assert "ddx.pneumonia" in allowed.ddx and "ddx.gilbert_syndrome" in allowed.ddx
    assert allowed.red_flags == {"rf.qsofa_ge2"}
    assert allowed.fields == set(fever.catalog.codes())


def test_the_response_schema_matches_the_model(repo_root):
    schema = response_json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    assert set(schema["required"]) == set(KEYS) and schema["additionalProperties"] is False
    committed = json.loads((repo_root / "schema" / "response.schema.json").read_text(encoding="utf-8"))
    assert committed == schema
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(VALID)
    for bad in ({**VALID, "extra": 1}, {**VALID, "decision": "maybe"}, {**VALID, "red_flags": ["ddx.sepsis"]}):
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(bad)
