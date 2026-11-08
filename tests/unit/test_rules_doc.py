"""Generated rule documentation (PR-A03) and the one-line condition text."""

from __future__ import annotations

import importlib.util
import sys

import pytest

from proof_rules import loader
from proof_rules.logic import condition_text
from proof_rules.model import Rule


@pytest.fixture(scope="module")
def rules_doc(request):
    path = request.config.rootpath / "tools" / "rules_doc.py"
    spec = importlib.util.spec_from_file_location("rules_doc", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rules_doc"] = module
    spec.loader.exec_module(module)
    return module


def _when(when: dict) -> object:
    rule = {
        "id": "T-1",
        "kind": "ddx",
        "target": "ddx.x",
        "requires": sorted(_fields(when)),
        "when": when,
        "sources": [{"ref": "SRC-0001", "locator": "x"}],
        "status": "draft_unreviewed",
        "tests": [{"facts": {}, "expect": True}, {"facts": {}, "expect": False}],
    }
    if any(isinstance(item, dict) and "ref" in item for item in _values(when)):
        rule["tests"] = [{"facts": {}, "refs": {"lab.a": {"lower": 1, "upper": 2}}, "expect": e} for e in (True, False)]
    return Rule.model_validate(rule).when


def _fields(node: dict) -> set[str]:
    if "field" in node:
        return {node["field"]}
    parts = node.get("all") or node.get("any") or node.get("of") or [node.get("not")]
    return set().union(*(_fields(part) for part in parts))


def _values(node: dict) -> list:
    if "field" in node:
        return [node["value"]]
    parts = node.get("all") or node.get("any") or node.get("of") or [node.get("not")]
    return [value for part in parts for value in _values(part)]


def test_condition_text_of_every_construct():
    qsofa = _when(
        {
            "at_least": 2,
            "of": [
                {"field": "vital.resp_rate", "op": "ge", "value": 22},
                {"field": "vital.mental_status", "op": "eq", "value": "altered"},
                {"field": "vital.sbp", "op": "le", "value": 100},
            ],
        }
    )
    assert condition_text(qsofa) == (
        "at least 2 of (vital.resp_rate ≥ 22, vital.mental_status = altered, vital.sbp ≤ 100)"
    )
    nested = _when(
        {
            "all": [
                {"field": "hx.cough", "op": "eq", "value": True},
                {
                    "any": [
                        {"field": "lab.a", "op": "gt", "value": {"ref": "upper"}},
                        {"field": "hx.n", "op": "in", "value": [1, 2]},
                    ]
                },
                {"not": {"field": "hx.m", "op": "ne", "value": 3.5}},
                {"field": "hx.k", "op": "lt", "value": 1},
            ]
        }
    )
    assert condition_text(nested) == (
        "hx.cough = true and (lab.a > upper reference limit or hx.n in {1, 2}) and not (hx.m ≠ 3.5) and hx.k < 1"
    )


def test_render_lists_every_rule_source_and_migration(rules_doc, fixture_packs):
    text = rules_doc.render(fixture_packs)
    assert text.startswith("# Proof rules\n")
    for line in ("zh: ", "en: ", "de: "):
        assert f"> {line}" in text
    for pack in ("demo", "labx"):
        for rule in loader.read_pack(fixture_packs / pack).rules:
            assert f"`{rule.id}`" in text
    assert "SRC-9001" in text and "SRC-9002" in text
    assert "## Domain `demo`" in text
    assert "### Migration table of `labx`" in text
    assert "1 of 2 keys are migrated" in text
    assert "fixture reason" in text and "empty entry in the fixture table" in text
    assert "draft, not reviewed by a physician" in text
    assert "lab.crp_mg_l > upper reference limit" in text
    assert "\r" not in text and text.endswith("\n")
    assert rules_doc.render(fixture_packs) == text


def test_render_refuses_broken_packs(rules_doc, packs):
    (packs / "demo" / "sources.yaml").unlink()
    with pytest.raises(loader.LoadError):
        rules_doc.render(packs)


def test_committed_document_is_current(rules_doc):
    assert rules_doc.main(["--check"]) == 0, "docs/regeln.md is out of date: uv run python tools/rules_doc.py"


def test_main_rejects_unknown_arguments(rules_doc):
    assert rules_doc.main(["--nope"]) == 2
