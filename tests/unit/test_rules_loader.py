"""Loader: the U2 DoD rejections (rule without source, unknown field, wrong requires) and all cross-file checks."""

from __future__ import annotations

import json
import shutil

import pytest

from proof_rules import loader
from proof_rules.loader import LoadError


def _first_rule(data):
    return data[0]


def _problems(root, name="demo"):
    with pytest.raises(LoadError) as info:
        loader.load_domain(name, root)
    return "\n".join(info.value.problems)


def test_fixture_domain_loads(demo):
    assert demo.name == "demo"
    assert demo.case_prefix == "DEM"
    assert [rule.id for rule in demo.rules] == [
        "DEM-DDX-001",
        "DEM-DDX-002",
        "DEM-DDX-003",
        "DEM-RF-001",
        "LABX-DDX-001",
    ]
    # The effective catalog holds the own fields plus the library fields the active rules use.
    assert demo.catalog.get("lab.crp_mg_l") is not None
    assert demo.catalog.get("lab.wbc_g_l") is not None
    assert demo.catalog.get("lab.ldl_mmol_l") is None
    assert {term.code for term in demo.vocabulary.ddx} == {"ddx.alpha", "ddx.beta", "ddx.gamma"}
    assert demo.sources.ids() == {"SRC-9001", "SRC-9002"}
    assert demo.references["lab.crp_mg_l"].upper == 5


def test_check_runs_every_test_vector(fixture_packs):
    result = loader.check(fixture_packs)
    assert result.ok, result.problems
    assert [(pack.name, pack.kind, pack.rules, pack.tests) for pack in result.packs] == [
        ("demo", "domain", 4, 11),
        ("labx", "library", 2, 4),
    ]
    assert [(d.name, d.active_rules, d.fields, d.references) for d in result.domains] == [("demo", 5, 9, 1)]
    assert loader.domains(fixture_packs) == ["demo"]
    assert loader.domain_for_complaint("fever", fixture_packs) == "demo"
    assert loader.domain_for_complaint("chest_pain", fixture_packs) is None


def test_rule_without_source_is_rejected(packs, edit_yaml):
    edit_yaml(packs / "demo/rules/red_flags.yaml", lambda data: _first_rule(data).update(sources=[]))
    assert "DEM-RF-001: sources: Tuple should have at least 1 item" in _problems(packs)


def test_rule_citing_an_unregistered_source_is_rejected(packs, edit_yaml):
    edit_yaml(
        packs / "demo/rules/red_flags.yaml",
        lambda data: _first_rule(data).update(sources=[{"ref": "SRC-0042", "locator": "p. 3"}]),
    )
    assert "DEM-RF-001: source SRC-0042 is not in the source register" in _problems(packs)


def test_rule_with_unknown_field_is_rejected(packs, edit_yaml):
    def change(data):
        rule = _first_rule(data)
        rule["when"]["of"][0]["field"] = "vital.breaths"
        rule["requires"] = ["vital.breaths", "vital.mental_status", "vital.sbp"]
        for test in rule["tests"]:
            test["facts"]["vital.breaths"] = test["facts"].pop("vital.resp_rate", 20)
        rule["tests"][2]["facts"].pop("vital.breaths")

    edit_yaml(packs / "demo/rules/red_flags.yaml", change)
    assert "DEM-RF-001: unknown field vital.breaths" in _problems(packs)


def test_rule_with_wrong_requires_is_rejected(packs, edit_yaml):
    edit_yaml(packs / "demo/rules/red_flags.yaml", lambda data: _first_rule(data).update(requires=["vital.sbp"]))
    problems = _problems(packs)
    assert "requires does not match the condition" in problems
    assert "vital.mental_status, vital.resp_rate" in problems


def test_target_must_be_in_the_vocabulary(packs, edit_yaml):
    edit_yaml(packs / "demo/rules/ddx.yaml", lambda data: _first_rule(data).update(target="ddx.omega"))
    assert "DEM-DDX-001: target ddx.omega is not in the vocabulary" in _problems(packs)


def test_comparison_must_fit_the_field_type(packs, edit_yaml):
    def change(data):
        rule = _first_rule(data)
        rule["when"]["all"][0] = {"field": "hx.cough", "op": "ge", "value": 1}

    edit_yaml(packs / "demo/rules/ddx.yaml", change)
    assert "op 'ge' needs a numeric field, hx.cough is bool" in _problems(packs)


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        ({"field": "hx.cough", "op": "eq", "value": 1}, "hx.cough is a bool field, compare with true or false"),
        ({"field": "vital.mental_status", "op": "eq", "value": "confused"}, "expected one of normal, altered"),
        ({"field": "vital.mental_status", "op": "in", "value": ["normal", "odd"]}, "expected one of normal, altered"),
        ({"field": "vital.temp_c", "op": "in", "value": [38.0, 39.0]}, "op 'in' needs an int or enum field"),
        ({"field": "hx.onset_days", "op": "in", "value": [2, True]}, "op 'in' needs integers"),
        ({"field": "hx.onset_days", "op": "ge", "value": 2.5}, "the threshold must be an integer"),
        ({"field": "hx.onset_days", "op": "eq", "value": 2.5}, "compare with an integer"),
        ({"field": "vital.temp_c", "op": "eq", "value": "hot"}, "expected a number"),
        ({"field": "vital.temp_c", "op": "ge", "value": "hot"}, "needs a number"),
        ({"field": "hx.cough", "op": "gt", "value": {"ref": "upper"}}, "reference thresholds need a numeric field"),
    ],
)
def test_comparison_type_errors(packs, edit_yaml, condition, message):
    def change(data):
        rule = _first_rule(data)
        rule["when"] = condition
        rule["requires"] = [condition["field"]]
        for test in rule["tests"]:
            test["facts"] = {}
        if isinstance(condition["value"], dict):
            for test in rule["tests"]:
                test["refs"] = {condition["field"]: {"upper": 1}}

    edit_yaml(packs / "demo/rules/ddx.yaml", change)
    assert message in "\n".join(loader.check(packs).problems)


@pytest.mark.parametrize(
    "condition",
    [
        {"field": "vital.mental_status", "op": "in", "value": ["altered"]},
        {"field": "hx.onset_days", "op": "in", "value": [1, 2, 3]},
        {"field": "vital.mental_status", "op": "ne", "value": "normal"},
        {"field": "hx.onset_days", "op": "eq", "value": 2},
        {"field": "vital.temp_c", "op": "eq", "value": 38},
        {"field": "hx.cough", "op": "ne", "value": False},
    ],
)
def test_valid_comparisons_of_every_type(packs, edit_yaml, condition):
    def change(data):
        rule = _first_rule(data)
        rule["when"] = condition
        rule["requires"] = [condition["field"]]
        rule["tests"] = [{"facts": {}, "expect": True}, {"facts": {}, "expect": False}]

    edit_yaml(packs / "demo/rules/ddx.yaml", change)
    assert loader.load_domain("demo", packs).rules


def test_test_vector_values_are_checked(packs, edit_yaml):
    edit_yaml(
        packs / "demo/rules/ddx.yaml", lambda data: _first_rule(data)["tests"][0]["facts"].update({"hx.cough": "yes"})
    )
    assert "DEM-DDX-001: tests[0] hx.cough: expected true or false" in _problems(packs)


def test_failing_test_vector_is_reported_by_check(packs, edit_yaml):
    edit_yaml(packs / "demo/rules/ddx.yaml", lambda data: _first_rule(data)["tests"][1].update(expect=True))
    result = loader.check(packs)
    assert not result.ok
    assert "demo DEM-DDX-001 tests[1]: expected true, got false" in result.problems


def test_duplicate_rule_ids(packs, edit_yaml):
    edit_yaml(packs / "demo/rules/ddx.yaml", lambda data: data[1].update(id="DEM-DDX-001"))
    assert "duplicate rule id (also in ddx.yaml)" in _problems(packs)
    edit_yaml(packs / "demo/rules/ddx.yaml", lambda data: data[1].update(id="DEM-DDX-002"))
    edit_yaml(packs / "labx/rules/labs.yaml", lambda data: data[1].update(id="DEM-DDX-001"))
    assert "rule id DEM-DDX-001 is used in packs demo and labx" in loader.check(packs).problems


def test_activated_rule_must_exist(packs, edit_yaml):
    edit_yaml(packs / "demo/pack.yaml", lambda data: data["domain"]["activate"].update(labx=["LABX-DDX-009"]))
    assert "activated rule LABX-DDX-009 does not exist in pack labx" in _problems(packs)


def test_activate_all_pulls_every_library_rule_and_its_needs(packs, edit_yaml):
    edit_yaml(packs / "demo/pack.yaml", lambda data: data["domain"]["activate"].update(labx="all"))
    problems = _problems(packs)
    assert "rule LABX-DDX-002 needs the upper reference limit of lab.ldl_mmol_l, no profile has it" in problems
    (packs / "demo/profiles/lab_ldl.json").write_text(
        json.dumps({"fact_code": "lab.ldl_mmol_l", "unit": "mmol/L", "reference": {"upper": 3.0}}), encoding="utf-8"
    )
    domain = loader.load_domain("demo", packs)
    assert "LABX-DDX-002" in {rule.id for rule in domain.rules}
    assert domain.catalog.get("lab.ldl_mmol_l") is not None
    assert "ddx.delta" in {term.code for term in domain.vocabulary.ddx}


def test_missing_reference_profile(packs):
    (packs / "demo/profiles/crp_mg_l.json").unlink()
    assert "rule LABX-DDX-001 needs the upper reference limit of lab.crp_mg_l, no profile has it" in _problems(packs)


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        ({"fact_code": "lab.crp_mg_l", "unit": "mg/dL", "reference": {"upper": 0.5}}, "differs from the catalog unit"),
        ({"fact_code": "hx.cough", "unit": "-", "reference": {"upper": 1}}, "profile for non-numeric field hx.cough"),
        ({"fact_code": "lab.ldl_mmol_l", "unit": "mmol/L", "reference": {"upper": 3}}, "which is not a field of"),
        ({"fact_code": "lab.crp_mg_l", "unit": "mg/L"}, "reference: Field required"),
    ],
)
def test_profile_problems(packs, profile, message):
    (packs / "demo/profiles/crp_mg_l.json").write_text(json.dumps(profile), encoding="utf-8")
    assert message in _problems(packs)


def test_profile_files_are_parsed_strictly(packs):
    (packs / "demo/profiles/crp_mg_l.json").write_text(
        '{"fact_code": "lab.crp_mg_l", "fact_code": "lab.crp_mg_l"}', encoding="utf-8"
    )
    assert "duplicate key 'fact_code'" in _problems(packs)
    (packs / "demo/profiles/crp_mg_l.json").write_text(
        json.dumps({"fact_code": "lab.crp_mg_l", "unit": "mg/L", "reference": {"upper": 5}}), encoding="utf-8"
    )
    (packs / "demo/profiles/lab_crp_copy.json").write_text(
        json.dumps({"fact_code": "lab.crp_mg_l", "unit": "mg/L", "reference": {"upper": 5}}), encoding="utf-8"
    )
    assert "second profile for lab.crp_mg_l" in _problems(packs)


def test_library_packs_have_no_profiles(packs):
    (packs / "labx/profiles").mkdir()
    shutil.copy(packs / "demo/profiles/crp_mg_l.json", packs / "labx/profiles/crp_mg_l.json")
    assert "only domain packs have lab profiles" in _problems(packs)


def test_field_defined_in_two_packs(packs, edit_yaml):
    edit_yaml(packs / "labx/catalog.yaml", lambda data: data["fields"].append(_temperature(packs)))
    assert "field vital.temp_c is also defined in pack" in _problems(packs)


def _temperature(packs):
    from proof.core import yamlio

    field = yamlio.load_file(packs / "demo/catalog.yaml")["fields"][0]
    field["bounds"]["source"]["ref"] = "SRC-9002"
    return field


def test_code_and_source_defined_in_two_packs(packs, edit_yaml):
    edit_yaml(packs / "labx/vocabulary.yaml", lambda data: data["ddx"].append({**data["ddx"][0], "code": "ddx.alpha"}))
    edit_yaml(
        packs / "labx/sources.yaml", lambda data: data["sources"].append({**data["sources"][0], "id": "SRC-9001"})
    )
    problems = _problems(packs)
    assert "code ddx.alpha is also defined in pack" in problems
    assert "source SRC-9001 is also defined in pack" in problems
    assert "source id SRC-9001 is used in packs demo and labx" in loader.check(packs).problems


def test_every_numeric_fact_of_a_domain_needs_bounds(packs, edit_yaml):
    def drop(data):
        del data["fields"][0]["bounds"]

    edit_yaml(packs / "demo/catalog.yaml", drop)
    assert "demo: numeric field vital.temp_c has no physiological bounds (A-65)" in _problems(packs)


def test_unused_library_field_may_lack_bounds(packs, edit_yaml):
    def drop(data):
        del next(field for field in data["fields"] if field["code"] == "lab.ldl_mmol_l")["bounds"]

    edit_yaml(packs / "labx/catalog.yaml", drop)
    assert loader.check(packs).ok


def test_bounds_must_cite_a_registered_source(packs, edit_yaml):
    edit_yaml(packs / "demo/catalog.yaml", lambda data: data["fields"][0]["bounds"]["source"].update(ref="SRC-0007"))
    assert "bounds of vital.temp_c cite unknown source SRC-0007" in _problems(packs)


def test_red_flag_target_must_be_in_the_vocabulary(packs, edit_yaml):
    edit_yaml(
        packs / "demo/rules/ddx.yaml", lambda data: _first_rule(data).update(kind="red_flag", target="rf.qsofa_x")
    )
    assert "target rf.qsofa_x is not in the vocabulary" in _problems(packs)


def test_files_and_structure(packs):
    (packs / "demo/rules/notes.txt").write_text("not a rule file", encoding="utf-8")
    assert "only .yaml files belong in rules/" in _problems(packs)
    (packs / "demo/rules/notes.txt").unlink()
    (packs / "demo/rules/extra.yaml").write_text("id: DEM-X-1\n", encoding="utf-8")
    assert "expected a list of rules" in _problems(packs)
    (packs / "demo/rules/extra.yaml").write_text("- id: DEM-X-1\n  kind: ddx\n  kind: ddx\n", encoding="utf-8")
    assert "duplicate key 'kind'" in _problems(packs)
    (packs / "demo/rules/extra.yaml").write_text("", encoding="utf-8")
    loader.load_domain("demo", packs)
    (packs / "demo/rules/extra.yaml").unlink()
    (packs / "demo/vocabulary.yaml").write_text("", encoding="utf-8")
    assert "vocabulary.yaml: file is empty" in _problems(packs)
    (packs / "demo/vocabulary.yaml").write_text("- a\n", encoding="utf-8")
    assert "expected a mapping at the top level" in _problems(packs)
    (packs / "demo/vocabulary.yaml").unlink()
    assert "vocabulary.yaml: file is missing" in _problems(packs)


def test_missing_rules_directory_and_name_mismatch(packs, edit_yaml):
    shutil.rmtree(packs / "labx/rules")
    assert "rules: directory is missing" in "\n".join(loader.check(packs).problems)
    (packs / "labx/rules").mkdir()
    edit_yaml(packs / "labx/pack.yaml", lambda data: data.update(pack="labs"))
    assert "pack name 'labs' differs from the directory name" in _problems(packs)


def test_used_pack_must_exist_and_be_a_library(packs, edit_yaml):
    edit_yaml(packs / "demo/pack.yaml", lambda data: data["domain"].update(uses=["other"], activate={"other": "all"}))
    assert "used pack 'other' does not exist" in _problems(packs)
    shutil.copytree(packs / "demo", packs / "other")
    edit_yaml(packs / "other/pack.yaml", lambda data: data.update(pack="other"))
    assert "used pack 'other' is not a library pack" in _problems(packs)


def test_broken_used_pack_is_reported(packs):
    (packs / "labx/catalog.yaml").write_text("fields: [1]\n", encoding="utf-8")
    assert "labx" in _problems(packs)


def test_unknown_domain_and_library_as_domain(fixture_packs, tmp_path):
    with pytest.raises(LoadError, match=r"no pack 'fever' .*available: demo, labx"):
        loader.load_domain("fever", fixture_packs)
    with pytest.raises(LoadError, match="is a library pack, not a domain"):
        loader.load_domain("labx", fixture_packs)
    assert loader.domains(tmp_path / "missing") == []
    result = loader.check(tmp_path / "missing")
    assert not result.ok
    assert result.problems == (f"no rule packs in {tmp_path / 'missing'}",)


def test_check_reports_directories_without_pack_file(packs):
    (packs / "stray").mkdir()
    (packs / "_ignored").mkdir()
    assert "not a pack (pack.yaml is missing)" in "\n".join(loader.check(packs).problems)
    assert "_ignored" not in "\n".join(loader.check(packs).problems)
    assert loader.domains(packs) == ["demo"]


def test_broken_domain_is_reported_by_check(packs):
    (packs / "demo/catalog.yaml").write_text("fields: 3\n", encoding="utf-8")
    result = loader.check(packs)
    assert not result.ok
    assert any("catalog.yaml" in problem for problem in result.problems)
    assert result.domains == ()


def _check_problems(root):
    return "\n".join(loader.check(root).problems)


def test_migration_table_and_rules_agree(packs, edit_yaml):
    def wrong_rule(data):
        data["entries"][0]["items"][0]["rules"] = ["LABX-DDX-404"]

    edit_yaml(packs / "labx/migration.yaml", wrong_rule)
    problems = _check_problems(packs)
    assert "CRP_HOCH names rule LABX-DDX-404, which is not in the pack" in problems
    assert "rule LABX-DDX-001 (from CRP_HOCH) is missing in the table" in problems


def test_migration_table_key_must_match_migrated_from(packs, edit_yaml):
    def other_key(data):
        data["entries"][1]["items"] = [{"text": "x", "rules": ["LABX-DDX-001"]}]
        del data["entries"][1]["reason"]

    edit_yaml(packs / "labx/migration.yaml", other_key)
    problems = _check_problems(packs)
    assert "CRP_NIEDRIG names rule LABX-DDX-001, migrated from CRP_HOCH" in problems
    assert "rule LABX-DDX-001 is listed under CRP_HOCH and CRP_NIEDRIG" in problems


def test_migrated_rule_needs_a_migration_table(packs):
    (packs / "labx/migration.yaml").unlink()
    assert "labx: rule LABX-DDX-001 is migrated from CRP_HOCH, no migration.yaml" in _check_problems(packs)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda data: data["entries"].append(data["entries"][0]), "duplicate keys: CRP_HOCH"),
        (lambda data: data["entries"][0]["items"][1].pop("reason") and None, "either the rules it became"),
        (lambda data: data["entries"][0].update(reason="x"), "a migrated entry has none"),
        (lambda data: data["entries"][1].pop("reason") and None, "an entry without any migrated item needs a reason"),
        (lambda data: data["entries"][0]["items"].append(data["entries"][0]["items"][0]), "lists an item twice"),
        (lambda data: data["entries"][0]["items"][0].update(rules=["LABX-DDX-001"] * 2), "lists a rule twice"),
        (lambda data: data["source"].update(sha256="abc"), "String should match pattern"),
        (lambda data: data["entries"][0].update(key="CRP-HOCH"), "String should match pattern"),
    ],
)
def test_migration_table_model(packs, edit_yaml, change, message):
    edit_yaml(packs / "labx/migration.yaml", change)
    assert message in _check_problems(packs)


def test_lowercase_legacy_keys_are_accepted(packs, edit_yaml):
    """Prototype keys such as eGFR_NIEDRIG start with a lowercase letter."""
    edit_yaml(packs / "labx/migration.yaml", lambda data: data["entries"][1].update(key="eGFR_NIEDRIG"))
    assert loader.check(packs).ok


# --- Lists of the variants (MR4, MR7; KONZEPT 4.1) -------------------------------------------------------------------


def test_the_domain_carries_its_variant_lists(demo):
    assert [fact.code for fact in demo.catalog.irrelevant] == [
        "hx.fixture_detail",
        "hx.fixture_detail_older",
        "exam.fixture_detail_female",
    ]
    assert [template.id for template in demo.catalog.contradictions] == ["DEM-MR7-001", "DEM-MR7-002"]
    assert demo.catalog.irrelevant_fact("hx.fixture_detail").section == "hx"
    assert demo.catalog.irrelevant_fact("hx.nothing") is None and demo.catalog.contradiction("X-1") is None


def test_only_domain_packs_list_irrelevant_facts_and_contradictions(packs, edit_yaml):
    demo = (packs / "demo/catalog.yaml").read_text(encoding="utf-8")
    lists = demo[demo.index("irrelevant:") :]
    with (packs / "labx/catalog.yaml").open("a", encoding="utf-8") as handle:
        handle.write("\n" + lists.replace("DEM-MR7", "LABX-MR7").replace("fixture_detail", "labx_detail"))
    assert "labx: only domain packs list irrelevant facts and contradictions" in _problems(packs)


def test_an_irrelevant_fact_must_not_be_a_field_rules_could_use(packs, edit_yaml):
    edit_yaml(packs / "demo/catalog.yaml", lambda data: data["irrelevant"][0].update(code="lab.ldl_mmol_l"))
    assert "irrelevant fact lab.ldl_mmol_l is a field of pack labx" in _problems(packs)


def test_contradiction_templates_are_checked(packs, edit_yaml):
    def change(data):
        first, second = data["contradictions"]
        first["sources"] = [{"ref": "SRC-0000", "locator": "x"}]
        second["when"] = {"field": "hx.cough", "op": "ge", "value": 1}
        data["contradictions"].append({**second, "id": "DEM-MR7-003", "field": "hx.unknown"})
        data["contradictions"][-1]["when"] = {"field": "hx.unknown", "op": "eq", "value": True}

    edit_yaml(packs / "demo/catalog.yaml", change)
    text = _problems(packs)
    assert "DEM-MR7-001: source SRC-0000 is not in the source register" in text
    assert "DEM-MR7-002: op 'ge' needs a numeric field, hx.cough is bool" in text
    assert "DEM-MR7-003: unknown field hx.unknown" in text


def test_a_contradiction_needs_a_field_of_the_domain_and_its_reference(packs, edit_yaml):
    def change(data):
        data["contradictions"][0].update(
            field="lab.ldl_mmol_l", when={"field": "lab.ldl_mmol_l", "op": "gt", "value": {"ref": "upper"}}
        )

    edit_yaml(packs / "demo/catalog.yaml", change)
    text = _problems(packs)
    assert "DEM-MR7-001: lab.ldl_mmol_l is not a field of the domain" in text
    assert "DEM-MR7-001: needs the upper reference limit of lab.ldl_mmol_l, no profile has it" in text
