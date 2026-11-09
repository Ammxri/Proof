"""``proof render``: a case as a model receives it (PR-F05)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from proof.cases import review
from proof.cli import app

FEVER_100 = Path(__file__).resolve().parents[2] / "data" / "collections" / "fever-100"
runner = CliRunner()


def test_render_a_case_file(fixture_cases):
    result = runner.invoke(app, ["render", str(fixture_cases / "prd_example.json"), "--lang", "de"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("Patientin, 67 Jahre\nVorstellungsgrund: Fieber\n")
    assert "  • Atemfrequenz (AF): 24/min\n" in result.output
    assert "### 2. Befund\n  • keine Angaben\n" in result.output


def test_render_from_a_collection_with_the_system_prompt():
    args = ["render", str(FEVER_100), "--lang", "zh", "--case-id", "FEV-000007", "--system-prompt"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    prompt, _, case = result.output.partition("-" * 40 + "\n")
    assert "rf.qsofa_ge2" in prompt
    assert case.splitlines()[1] == "主诉：发热"
    jsonl = runner.invoke(app, ["render", str(FEVER_100 / "cases.jsonl"), "--lang", "en", "--case-id", "FEV-000007"])
    assert jsonl.exit_code == 0 and "Presenting complaint: Fever" in jsonl.output


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([str(FEVER_100), "--lang", "en"], "holds 100 cases; choose one with --case-id"),
        ([str(FEVER_100), "--lang", "en", "--case-id", "FEV-999999"], "no case FEV-999999"),
        ([str(FEVER_100), "--lang", "fr", "--case-id", "FEV-000001"], "--lang: expected one of zh, en, de"),
    ],
)
def test_render_errors(args, message):
    result = runner.invoke(app, ["render", *args])
    assert result.exit_code == 1
    assert message in result.output


def test_render_rejects_broken_or_foreign_cases(tmp_path, fixture_cases):
    case = json.loads((fixture_cases / "prd_example.json").read_text(encoding="utf-8"))
    path = tmp_path / "case.json"
    path.write_text("{", encoding="utf-8")
    assert runner.invoke(app, ["render", str(path), "--lang", "de"]).exit_code == 1
    path.write_text(json.dumps({**case, "complaint": "cough"}), encoding="utf-8")
    result = runner.invoke(app, ["render", str(path), "--lang", "de"])
    assert result.exit_code == 1 and "no domain pack for complaint 'cough'" in result.output
    path.write_text(json.dumps({**case, "facts": {**case["facts"], "vital.temp_c": 99.0}}), encoding="utf-8")
    result = runner.invoke(app, ["render", str(path), "--lang", "de"])
    assert result.exit_code == 1 and "outside the physiological bounds" in result.output
    result = runner.invoke(app, ["render", str(fixture_cases / "prd_example.json"), "--lang", "de", "--case-id", "X"])
    assert result.exit_code == 1 and "holds FEV-000123, not X" in result.output
    empty = tmp_path / "empty.jsonl"
    empty.write_bytes(b"")
    result = runner.invoke(app, ["render", str(empty), "--lang", "de"])
    assert result.exit_code == 1 and "no cases" in result.output


def test_unknown_domains_in_a_manifest_are_reported():
    with pytest.raises(review.ReviewError, match="no domain pack 'nope'"):
        review.domain_named("nope")
