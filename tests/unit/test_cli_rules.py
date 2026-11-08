"""``proof rules check | list | explain`` on the test packs."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from proof import cli

runner = CliRunner()


def _run(*args):
    return runner.invoke(cli.app, ["rules", *args])


def test_check_passes_on_the_test_packs(fixture_packs):
    result = _run("check", "--packs", str(fixture_packs))
    assert result.exit_code == 0, result.output
    assert "pack demo (domain): 4 rules, 11 test vectors" in result.output
    assert "pack labx (library): 2 rules, 4 test vectors" in result.output
    assert "domain demo: 5 active rules, 9 fields, 1 reference ranges" in result.output
    assert result.output.rstrip().endswith("ok")


def test_check_fails_with_findings(packs):
    (packs / "demo/rules/ddx.yaml").write_text("- id: broken\n", encoding="utf-8")
    result = _run("check", "--packs", str(packs))
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "problem(s)" in result.output


def test_check_without_packs_fails(tmp_path):
    result = _run("check", "--packs", str(tmp_path))
    assert result.exit_code == 1
    assert "no rule packs in" in result.output


def test_list_shows_active_rules(fixture_packs):
    result = _run("list", "--domain", "demo", "--packs", str(fixture_packs))
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "id\tkind\ttarget\trequires\tsources\tstatus\tmigrated_from"
    assert lines[1:] == [
        "DEM-DDX-001\tddx\tddx.alpha\thx.cough,vital.temp_c\tSRC-9001\tdraft_unreviewed\t-",
        "DEM-DDX-002\tddx\tddx.beta\thx.onset_days,vital.temp_c\tSRC-9001\tdraft_unreviewed\t-",
        "DEM-DDX-003\tddx\tddx.beta\tlab.wbc_g_l\tSRC-9002\tdraft_unreviewed\t-",
        "DEM-RF-001\tred_flag\trf.qsofa_ge2\tvital.mental_status,vital.resp_rate,vital.sbp\tSRC-9001\tdraft_unreviewed\t-",
        "LABX-DDX-001\tddx\tddx.gamma\tlab.crp_mg_l\tSRC-9002\tdraft_unreviewed\tCRP_HOCH",
    ]


def test_list_unknown_domain(fixture_packs):
    result = _run("list", "--domain", "fever", "--packs", str(fixture_packs))
    assert result.exit_code == 1
    assert "error: no pack 'fever'" in result.output


def test_explain_the_prd_example(fixture_packs, fixture_cases):
    result = _run("explain", str(fixture_cases / "prd_example.json"), "--packs", str(fixture_packs))
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "case: FEV-000123"
    assert "domain: demo (case prefix DEM, complaint fever)" in lines
    assert "  DEM-RF-001 red_flag -> rf.qsofa_ge2: true" in lines
    assert "      vital.sbp le 100 (value 96): true" in lines
    assert "    lab.crp_mg_l gt ref.upper (value 180, limit 5): true" in lines
    assert "  determinability: refer_urgent" in lines
    assert "  critical_fields: hx.cough, lab.crp_mg_l, lab.wbc_g_l, vital.temp_c" in lines
    assert (
        "  vital.sbp: refer_urgent | red_flags: rf.qsofa_ge2 | ddx: ddx.alpha, ddx.beta, ddx.gamma (unchanged)" in lines
    )
    assert "  hx.cough: refer_urgent | red_flags: rf.qsofa_ge2 | ddx: ddx.beta, ddx.gamma (changed, critical)" in lines
    # The PRD key is an illustration (D-05); the test domain's rules differ from it.
    assert lines[-1] == "stored key: differs in critical_fields, ddx"


def test_explain_matching_key_and_explicit_domain(tmp_path, fixture_packs, prd_facts):
    key = {
        "determinability": "refer_urgent",
        "red_flags": ["rf.qsofa_ge2"],
        "critical_fields": ["hx.cough", "lab.crp_mg_l", "lab.wbc_g_l", "vital.temp_c"],
        "ddx": ["ddx.alpha", "ddx.beta", "ddx.gamma"],
    }
    case = tmp_path / "case.json"
    case.write_text(json.dumps({"facts": prd_facts, "key": key}), encoding="utf-8")
    result = _run("explain", str(case), "--domain", "demo", "--packs", str(fixture_packs))
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == "stored key: matches"
    case.write_text(json.dumps({"facts": prd_facts, "key": {**key, "extra": 1}}), encoding="utf-8")
    result = _run("explain", str(case), "--domain", "demo", "--packs", str(fixture_packs))
    assert result.output.splitlines()[-1] == "stored key: differs in unexpected entries extra"


def test_explain_without_facts_or_key(tmp_path, fixture_packs):
    case = tmp_path / "case.json"
    case.write_text(json.dumps({"facts": {}}), encoding="utf-8")
    result = _run("explain", str(case), "--domain", "demo", "--packs", str(fixture_packs))
    assert result.exit_code == 0, result.output
    assert "  determinability: ask" in result.output
    assert "stored key" not in result.output


def test_explain_errors(tmp_path, fixture_packs):
    case = tmp_path / "case.json"
    packs = ["--packs", str(fixture_packs)]
    case.write_text("{not json", encoding="utf-8")
    assert _run("explain", str(case), *packs).exit_code == 1
    case.write_text(json.dumps({"case_id": "x"}), encoding="utf-8")
    result = _run("explain", str(case), *packs)
    assert result.exit_code == 1
    assert "expected a JSON object with a 'facts' object" in result.output
    case.write_text(json.dumps({"facts": {}, "complaint": "cough"}), encoding="utf-8")
    result = _run("explain", str(case), *packs)
    assert result.exit_code == 1
    assert "no domain pack for complaint 'cough'; pass --domain" in result.output
    case.write_text(json.dumps({"facts": {}}), encoding="utf-8")
    assert "no domain pack for complaint None" in _run("explain", str(case), *packs).output
    case.write_text(json.dumps({"facts": {"lab.unknown": 1}, "complaint": "fever"}), encoding="utf-8")
    result = _run("explain", str(case), *packs)
    assert result.exit_code == 1
    assert "lab.unknown: unknown fact code" in result.output
    assert _run("explain", str(tmp_path / "missing.json"), *packs).exit_code == 2
