"""Rule pack model: every rule has a source (PR-K08), exact requires, test vectors; catalog and source checks."""

from __future__ import annotations

import copy
import re
from datetime import date

import pytest
from pydantic import ValidationError

from proof_rules.model import (
    Catalog,
    Compare,
    ContradictionTemplate,
    DomainSettings,
    FieldDef,
    IrrelevantFact,
    PackConfig,
    PatientCondition,
    RefRange,
    Rule,
    Source,
    SourceRegister,
    Vocabulary,
    children,
    comparisons,
    fields_of,
    reference_bounds_of,
)

QSOFA = {
    "id": "FEV-RF-001",
    "kind": "red_flag",
    "target": "rf.qsofa_ge2",
    "requires": ["vital.mental_status", "vital.resp_rate", "vital.sbp"],
    "when": {
        "at_least": 2,
        "of": [
            {"field": "vital.resp_rate", "op": "ge", "value": 22},
            {"field": "vital.mental_status", "op": "eq", "value": "altered"},
            {"field": "vital.sbp", "op": "le", "value": 100},
        ],
    },
    "sources": [{"ref": "SRC-0001", "locator": "Table 1"}],
    "status": "draft_unreviewed",
    "tests": [
        {"facts": {"vital.resp_rate": 22, "vital.mental_status": "altered", "vital.sbp": 120}, "expect": True},
        {"facts": {"vital.resp_rate": 21, "vital.mental_status": "normal", "vital.sbp": 101}, "expect": False},
    ],
}

LABELS = {"zh": {"name": "体温"}, "en": {"name": "Temperature"}, "de": {"name": "Temperatur"}}
BOUNDS = {"lower": 30, "upper": 44, "source": {"ref": "SRC-0001", "locator": "x"}}
SOURCE = {
    "id": "SRC-0001",
    "citation": "Singer M, et al. JAMA 2016;315(8):801-810",
    "url": "https://jamanetwork.com/journals/jama/fullarticle/2492881",
    "kind": "original_publication",
    "terms": "Criteria and thresholds only, in own words",
    "terms_checked_on": date(2026, 11, 8),
    "permitted_use": "Criterion, threshold and locator",
}


def _rule(**changes):
    data = copy.deepcopy(QSOFA)
    data.update(changes)
    return Rule.model_validate(data)


def test_valid_rule_and_structure_helpers():
    rule = _rule()
    assert fields_of(rule.when) == frozenset(rule.requires)
    assert [compare.op for compare in comparisons(rule.when)] == ["ge", "eq", "le"]
    assert reference_bounds_of(rule.when) == frozenset()
    assert len(children(rule.when)) == 3
    assert children(children(rule.when)[0]) == (), "a comparison has no sub-conditions"


def test_rule_without_source_is_rejected():
    with pytest.raises(ValidationError, match="sources"):
        _rule(sources=[])
    data = copy.deepcopy(QSOFA)
    del data["sources"]
    with pytest.raises(ValidationError, match="sources"):
        Rule.model_validate(data)
    with pytest.raises(ValidationError, match="same reference twice"):
        _rule(sources=[QSOFA["sources"][0], QSOFA["sources"][0]])
    with pytest.raises(ValidationError, match="must not be empty"):
        _rule(sources=[{"ref": "SRC-0001", "locator": "   "}])


def test_requires_must_match_the_condition_exactly():
    with pytest.raises(ValidationError, match=re.escape("used in when but not in requires: vital.sbp")):
        _rule(requires=["vital.mental_status", "vital.resp_rate"])
    with pytest.raises(ValidationError, match=re.escape("in requires but not used in when: hx.cough")):
        _rule(requires=[*QSOFA["requires"], "hx.cough"])
    with pytest.raises(ValidationError, match="twice"):
        _rule(requires=[*QSOFA["requires"], "vital.sbp"])


def test_rule_needs_a_positive_and_a_negative_test():
    with pytest.raises(ValidationError, match="one vector expecting true and one expecting false"):
        _rule(tests=[QSOFA["tests"][0], QSOFA["tests"][0]])
    with pytest.raises(ValidationError, match="at least 2 items"):
        _rule(tests=[QSOFA["tests"][0]])
    with pytest.raises(ValidationError, match="outside requires"):
        _rule(tests=[*QSOFA["tests"], {"facts": {"hx.cough": True}, "expect": "unknown"}])


def test_target_must_fit_the_kind():
    with pytest.raises(ValidationError, match=re.escape("starting with 'ddx.'")):
        _rule(kind="ddx")
    with pytest.raises(ValidationError, match="kind"):
        _rule(kind="warning")


def test_status_is_always_draft_unreviewed():
    with pytest.raises(ValidationError, match="status"):
        _rule(status="reviewed")


def test_unknown_keys_and_unknown_condition_shapes_are_rejected():
    with pytest.raises(ValidationError, match="Extra inputs"):
        _rule(comment="free text")
    with pytest.raises(ValidationError, match="expected a comparison"):
        _rule(when={"xor": []})
    with pytest.raises(ValidationError, match="Extra inputs"):
        _rule(when={"field": "vital.sbp", "op": "le", "value": 100, "all": []}, requires=["vital.sbp"])


def test_conditions_contain_no_expression_strings():
    with pytest.raises(ValidationError):
        _rule(when="vital.sbp <= 100", requires=["vital.sbp"])


def test_comparison_operands():
    with pytest.raises(ValidationError, match="non-empty list"):
        Compare(field="vital.sbp", op="in", value=5)
    with pytest.raises(ValidationError, match="distinct"):
        Compare(field="vital.sbp", op="in", value=(1, 1))
    with pytest.raises(ValidationError, match="single value"):
        Compare(field="vital.sbp", op="eq", value=(1, 2))
    with pytest.raises(ValidationError, match="only allowed with lt, le, gt and ge"):
        Compare(field="lab.crp_mg_l", op="eq", value={"ref": "upper"})
    with pytest.raises(ValidationError, match="finite"):
        Compare(field="vital.sbp", op="le", value=float("nan"))
    with pytest.raises(ValidationError, match="op"):
        Compare(field="vital.sbp", op="between", value=1)
    with pytest.raises(ValidationError, match="field"):
        Compare(field="sbp", op="le", value=1)
    with pytest.raises(ValidationError, match="exceeds"):
        _rule(when={"at_least": 4, "of": QSOFA["when"]["of"]})


def test_reference_thresholds_need_reference_ranges_in_every_test():
    when = {"field": "lab.crp_mg_l", "op": "gt", "value": {"ref": "upper"}}
    tests = [
        {"facts": {"lab.crp_mg_l": 6}, "refs": {"lab.crp_mg_l": {"upper": 5}}, "expect": True},
        {"facts": {"lab.crp_mg_l": 5}, "refs": {"lab.crp_mg_l": {"upper": 5}}, "expect": False},
    ]
    rule = _rule(kind="ddx", target="ddx.x", requires=["lab.crp_mg_l"], when=when, tests=tests)
    assert reference_bounds_of(rule.when) == {("lab.crp_mg_l", "upper")}
    with pytest.raises(ValidationError, match=re.escape("reference ranges for exactly: lab.crp_mg_l")):
        _rule(
            kind="ddx", target="ddx.x", requires=["lab.crp_mg_l"], when=when, tests=[{**tests[0], "refs": {}}, tests[1]]
        )
    lower_only = [{**test, "refs": {"lab.crp_mg_l": {"lower": 0}}} for test in tests]
    with pytest.raises(ValidationError, match="needs the upper reference limit"):
        _rule(kind="ddx", target="ddx.x", requires=["lab.crp_mg_l"], when=when, tests=lower_only)


def test_reference_range_shape():
    assert RefRange(upper=5).lower is None
    with pytest.raises(ValidationError, match="lower or an upper"):
        RefRange()
    with pytest.raises(ValidationError, match="below"):
        RefRange(lower=5, upper=5)


def test_sources_need_checked_terms_and_exclude_nice():
    assert Source.model_validate(SOURCE).id == "SRC-0001"
    for key in ("terms", "terms_checked_on", "permitted_use", "url"):
        data = dict(SOURCE)
        del data[key]
        with pytest.raises(ValidationError, match=key):
            Source.model_validate(data)
    with pytest.raises(ValidationError, match="url"):
        Source.model_validate({**SOURCE, "url": "http://example.org/insecure"})
    with pytest.raises(ValidationError, match="terms_checked_on"):
        Source.model_validate({**SOURCE, "terms_checked_on": "2026-11-08"})
    for url in ("https://www.nice.org.uk/guidance/ng143", "https://NICE.org.uk/x", "https://nice.org.uk:443/a"):
        with pytest.raises(ValidationError, match="NICE"):
            Source.model_validate({**SOURCE, "url": url})
    for citation in ("NICE guideline NG51", "National Institute for Health and Care Excellence (2016)"):
        with pytest.raises(ValidationError, match="NICE"):
            Source.model_validate({**SOURCE, "citation": citation})
    assert Source.model_validate({**SOURCE, "url": "https://evil-nice.org.uk.example.com/x"})
    with pytest.raises(ValidationError, match="duplicate source ids"):
        SourceRegister.model_validate({"sources": [SOURCE, SOURCE]})


def _field(**changes):
    data = {"code": "vital.temp_c", "section": "vital", "type": "number", "unit": "°C", "decimals": 1}
    data.update({"bounds": BOUNDS, "labels": LABELS})
    data.update(changes)
    return FieldDef.model_validate(data)


def test_field_definitions_by_type():
    assert _field().check_value(39.2) is None
    with pytest.raises(ValidationError, match="does not start with its section"):
        _field(section="lab")
    with pytest.raises(ValidationError, match="need a unit"):
        _field(unit=None)
    # Bounds are optional on the model; the loader requires them for every numeric fact of a domain (A-65).
    assert _field(bounds=None).check_value(99.9) is None
    with pytest.raises(ValidationError, match="need decimals"):
        _field(decimals=None)
    with pytest.raises(ValidationError, match="no decimals"):
        _field(code="vital.sbp", type="int")
    with pytest.raises(ValidationError, match="distinct"):
        _field(alt_units=[{"unit": "°C", "factor": 1, "decimals": 1}])
    with pytest.raises(ValidationError, match="must not be zero"):
        _field(alt_units=[{"unit": "°F", "factor": 0, "decimals": 1}])
    with pytest.raises(ValidationError, match="have no unit"):
        _field(code="hx.cough", section="hx", type="bool", decimals=None, bounds=None)
    with pytest.raises(ValidationError, match="only enum fields have values"):
        _field(values=["a", "b"])
    enum = {"code": "vital.mental_status", "type": "enum", "unit": None, "decimals": None, "bounds": None}
    value_labels = {"normal": {"zh": "正常", "en": "normal", "de": "unauffällig"}}
    with pytest.raises(ValidationError, match="at least two distinct values"):
        _field(**enum, values=["normal"], value_labels=value_labels)
    with pytest.raises(ValidationError, match="every enum value needs labels"):
        _field(**enum, values=["normal", "altered"], value_labels=value_labels)
    with pytest.raises(ValidationError, match="bool fields have no values"):
        _field(code="hx.cough", section="hx", type="bool", unit=None, decimals=None, bounds=None, values=["a", "b"])
    with pytest.raises(ValidationError, match="zh"):
        _field(labels={"en": {"name": "T"}, "de": {"name": "T"}})
    with pytest.raises(ValidationError, match="NFC"):
        _field(labels={**LABELS, "de": {"name": "Temperatúr"}})
    with pytest.raises(ValidationError, match="whitespace"):
        _field(labels={**LABELS, "en": {"name": " Temperature"}})
    with pytest.raises(ValidationError, match="below"):
        _field(bounds={**BOUNDS, "lower": 44})


def test_check_value():
    number = _field()
    assert number.check_value(39) is None
    assert number.check_value(True) == "expected a number"
    assert number.check_value("39") == "expected a number"
    assert "decimal places" in number.check_value(39.25)
    assert "outside" in number.check_value(45.0)
    assert number.check_value(float("inf")) == "expected a finite number"
    integer = _field(code="vital.sbp", type="int", unit="mmHg", decimals=None, bounds={**BOUNDS, "upper": 260})
    assert integer.check_value(120) is None
    assert integer.check_value(120.0) == "expected an integer"
    zero = _field(bounds={**BOUNDS, "lower": -1})
    assert zero.check_value(-0.0) == "negative zero is not allowed"
    open_upper = _field(bounds={"lower": 0.1, "source": BOUNDS["source"]})
    assert open_upper.check_value(1e6) is None
    assert open_upper.check_value(0.0) == "outside the physiological bounds [0.1, open]"
    flag = _field(code="hx.cough", section="hx", type="bool", unit=None, decimals=None, bounds=None)
    assert flag.check_value(True) is None
    assert flag.check_value(1) == "expected true or false"


def test_catalog_and_vocabulary_uniqueness():
    field = _field()
    catalog = Catalog(fields=(field,))
    assert catalog.get("vital.temp_c") is field
    assert catalog.get("vital.sbp") is None
    assert catalog.codes() == ("vital.temp_c",)
    with pytest.raises(ValidationError, match="duplicate field codes"):
        Catalog(fields=(field, field))
    term = {"code": "ddx.x", "labels": {"zh": "甲", "en": "x", "de": "x"}}
    vocabulary = Vocabulary.model_validate({"ddx": [term]})
    assert vocabulary.codes("ddx") == {"ddx.x"}
    assert vocabulary.codes("red_flag") == frozenset()
    with pytest.raises(ValidationError, match="not an rf code"):
        Vocabulary.model_validate({"red_flags": [term]})
    with pytest.raises(ValidationError, match="not a ddx code"):
        Vocabulary.model_validate({"ddx": [{**term, "code": "rf.x"}]})
    with pytest.raises(ValidationError, match="duplicate codes"):
        Vocabulary.model_validate({"ddx": [term, term]})


def test_pack_configuration():
    settings = {
        "case_prefix": "FEV",
        "complaint": "fever",
        "complaint_labels": {"zh": "发热", "en": "Fever", "de": "Fieber"},
        "uses": ["labs"],
        "activate": {"labs": ["LAB-DDX-001"]},
    }
    assert PackConfig.model_validate({"pack": "fever", "kind": "domain", "domain": settings}).domain is not None
    with pytest.raises(ValidationError, match="domain packs need domain settings"):
        PackConfig.model_validate({"pack": "fever", "kind": "domain"})
    with pytest.raises(ValidationError, match="domain packs need domain settings"):
        PackConfig.model_validate({"pack": "labs", "kind": "library", "domain": settings})
    with pytest.raises(ValidationError, match="exactly one entry per used pack"):
        DomainSettings.model_validate({**settings, "activate": {}})
    with pytest.raises(ValidationError, match="twice"):
        DomainSettings.model_validate({**settings, "uses": ["labs", "labs"]})
    with pytest.raises(ValidationError, match="lists a rule twice"):
        DomainSettings.model_validate({**settings, "activate": {"labs": ["LAB-DDX-001", "LAB-DDX-001"]}})
    with pytest.raises(ValidationError, match="case_prefix"):
        DomainSettings.model_validate({**settings, "case_prefix": "FEVER"})
    assert DomainSettings.model_validate({**settings, "activate": {"labs": "all"}}).activate["labs"] == "all"
    without_labels = {key: value for key, value in settings.items() if key != "complaint_labels"}
    with pytest.raises(ValidationError, match="complaint_labels"):
        DomainSettings.model_validate(without_labels)


# --- Lists of the variants (MR4, MR7; KONZEPT 4.1) -------------------------------------------------------------------

LINE = {
    "zh": {"name": "备注", "value": "无发热"},
    "en": {"name": "Note", "value": "afebrile"},
    "de": {"name": "Anmerkung", "value": "afebril"},
}
IRRELEVANT = {"code": "hx.visual_aid", "when": {}, "labels": LINE}
TEMPLATE = {
    "id": "FEV-MR7-001",
    "field": "vital.temp_c",
    "section": "exam",
    "when": {"field": "vital.temp_c", "op": "gt", "value": 38.0},
    "labels": LINE,
}


def test_patient_conditions():
    assert PatientCondition().fits("f", 18)
    older_women = PatientCondition(sex=("f",), min_age=30, max_age=80)
    assert older_women.fits("f", 30) and older_women.fits("f", 80)
    assert not older_women.fits("m", 40) and not older_women.fits("f", 29) and not older_women.fits("f", 81)
    with pytest.raises(ValidationError, match="sexes must be distinct"):
        PatientCondition(sex=("f", "f"))
    with pytest.raises(ValidationError, match="min_age must not exceed max_age"):
        PatientCondition(min_age=50, max_age=40)
    with pytest.raises(ValidationError, match="Input should be 'f' or 'm'"):
        PatientCondition(sex=("x",))


def test_irrelevant_facts_and_contradiction_templates():
    fact = IrrelevantFact.model_validate(IRRELEVANT)
    assert fact.section == "hx" and fact.when == PatientCondition()
    with pytest.raises(ValidationError, match="Field required"):
        IrrelevantFact.model_validate({key: value for key, value in IRRELEVANT.items() if key != "when"})
    with pytest.raises(ValidationError, match="must not start or end with whitespace"):
        IrrelevantFact.model_validate(
            {**IRRELEVANT, "labels": {**LINE, "de": {"name": "Sehhilfe", "value": " Brille"}}}
        )
    template = ContradictionTemplate.model_validate(TEMPLATE)
    assert template.sources == ()
    with pytest.raises(ValidationError, match=r"must compare vital.temp_c and nothing else"):
        ContradictionTemplate.model_validate(
            {**TEMPLATE, "when": {"all": [TEMPLATE["when"], {"field": "hx.cough", "op": "eq", "value": False}]}}
        )


def test_catalog_lists_are_unique_and_apart_from_the_fields():
    temperature = _field()
    catalog = Catalog(fields=(temperature,), irrelevant=(IRRELEVANT,), contradictions=(TEMPLATE,))
    assert catalog.irrelevant_fact("hx.visual_aid").code == "hx.visual_aid"
    assert catalog.contradiction("FEV-MR7-001").field == "vital.temp_c"
    with pytest.raises(ValidationError, match=r"duplicate irrelevant facts: hx.visual_aid"):
        Catalog(irrelevant=(IRRELEVANT, IRRELEVANT))
    with pytest.raises(ValidationError, match=r"irrelevant facts must not be catalog fields: vital.temp_c"):
        Catalog(fields=(temperature,), irrelevant=({**IRRELEVANT, "code": "vital.temp_c"},))
    with pytest.raises(ValidationError, match="duplicate contradiction ids: FEV-MR7-001"):
        Catalog(contradictions=(TEMPLATE, TEMPLATE))
