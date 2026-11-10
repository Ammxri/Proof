"""Variants MR2, MR4, MR6 and MR7 (PR-F06, PR-MR2, PR-MR4, PR-MR6, PR-MR7, A-15, A-39, A-85 to A-89, KONZEPT U10)."""

from __future__ import annotations

import dataclasses
import json
import re
import shutil
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import jsonschema
import pytest

from proof.cases import collection
from proof.cases.model import Case
from proof.core import canonical
from proof.core.i18n import LANGUAGES
from proof.render import units
from proof.render.case_text import RenderError, render_case
from proof.variants import generator, sets
from proof.variants.model import (
    DECISION_AND_DDX,
    UNCHANGED,
    AbsoluteExpectation,
    AddFacts,
    ChangeNotation,
    InsertContradiction,
    InvariantExpectation,
    RemoveField,
    Variant,
    variant_json_schema,
)
from proof.variants.notation import flipped_rules, read_back
from proof.variants.render import render_variant
from proof_rules import loader
from proof_rules.engine import infer, outcome
from proof_rules.logic import Truth, evaluate
from proof_rules.model import Catalog, Domain, fields_of

ROOT = Path(__file__).resolve().parents[2]
FEVER_100 = ROOT / "data" / "collections" / "fever-100"


@pytest.fixture(scope="module")
def fever() -> Domain:
    return loader.load_domain("fever")


@pytest.fixture(scope="module")
def cases() -> dict[str, Case]:
    data = (FEVER_100 / collection.CASES_FILE).read_bytes()
    return {case.case_id: case for case in (Case.model_validate(item) for item in canonical.loads_lines(data))}


@pytest.fixture(scope="module")
def full(cases, fever) -> generator.Generated:
    """All relations on Fever-100 with variant seed 1, as U12 will build them for Fever-500."""
    return generator.generate(cases.values(), fever, 1)


def _of(full: generator.Generated, mr: str) -> list[Variant]:
    return [variant for variant in full.variants if variant.mr == mr]


def _with_alt(domain: Domain, code: str, **changes) -> Domain:
    """``domain`` with the alternative units of ``code`` changed, e.g. coarser rounding."""
    fields = tuple(
        field.model_copy(update={"alt_units": tuple(alt.model_copy(update=changes) for alt in field.alt_units)})
        if field.code == code
        else field
        for field in domain.catalog.fields
    )
    catalog = Catalog(fields=fields, irrelevant=domain.catalog.irrelevant, contradictions=domain.catalog.contradictions)
    return dataclasses.replace(domain, catalog=catalog)


# --- All relations on Fever-100 --------------------------------------------------------------------------------------


def test_every_relation_is_built_and_every_variant_follows_from_its_case(full, cases, fever):
    """PR-F06: MR1 to MR7 with a machine-readable expectation; every variant passes the schema and the set checks."""
    assert Counter(variant.mr for variant in full.variants) == {
        "MR1": 100,
        "MR2": 100,
        "MR3": 100,
        "MR4": 100,
        "MR5": 300,
        "MR6": 100,
        "MR7": 98,
    }
    assert dict(full.missing) == {"MR1": 0, "MR2": 0, "MR3": 0, "MR4": 0, "MR6": 0, "MR7": 2}
    assert dict(full.discarded) == {"MR1": 0, "MR2": 0, "MR3": 0, "MR4": 0, "MR6": 0, "MR7": 0}
    validator = jsonschema.Draft202012Validator(variant_json_schema())
    for variant in full.variants:
        validator.validate(json.loads(canonical.dumps_bytes(variant.to_json())))
        assert Variant.model_validate(variant.to_json()) == variant
        assert sets.check_variant(variant, cases[variant.case_id], fever) == []
    assert {"MR1", "MR2", "MR3", "MR4", "MR6", "MR7"} == generator.REQUESTED_MRS


def test_same_seed_same_variants_new_seed_new_choices(cases, fever, full):
    """PR-D02, A-17: the seed decides field, fact, notation and statement."""
    again = generator.generate(cases.values(), fever, 1)
    assert again.variants == full.variants
    other = generator.generate(cases.values(), fever, 2)
    for mr, least in (("MR2", 60), ("MR4", 30), ("MR6", 60), ("MR7", 10)):
        mine = {variant.variant_id: variant.change for variant in _of(full, mr)}
        theirs = {variant.variant_id: variant.change for variant in _of(other, mr)}
        assert sum(theirs[key] != change for key, change in mine.items() if key in theirs) >= least, mr


def test_variants_render_in_every_language(full, cases, fever):
    for variant in full.variants:
        if variant.mr == "MR5":
            continue
        for lang in LANGUAGES:
            rendering = render_variant(variant, cases[variant.case_id], fever, lang)
            assert set(rendering.spans) == set(variant.facts)


# --- MR2 -------------------------------------------------------------------------------------------------------------


def test_mr2_leaves_out_a_field_whose_ablation_changes_nothing(full, cases, fever):
    """PR-MR2, KONZEPT U10: only fields that are not critical; decision and diagnoses stay."""
    removed = Counter()
    for variant in _of(full, "MR2"):
        base = cases[variant.case_id]
        assert isinstance(variant.change, RemoveField)
        field = variant.change.field
        assert field in base.facts and field not in base.key.critical_fields
        assert variant.facts == {code: value for code, value in base.facts.items() if code != field}
        assert outcome(fever, variant.facts) == outcome(fever, base.facts)
        assert (variant.key.determinability, variant.key.ddx) == (base.key.determinability, base.key.ddx)
        assert variant.key.required_questions == ()
        assert variant.expectation == InvariantExpectation(kind="invariant", compare=DECISION_AND_DDX)
        removed[field] += 1
    assert len(removed) > 5, "the seed spreads MR2 over many fields"


def test_mr2_text_misses_only_the_removed_line(full, cases, fever):
    for variant in _of(full, "MR2")[:10]:
        base = cases[variant.case_id]
        for lang in LANGUAGES:
            original = render_case(base, fever, lang)
            changed = render_variant(variant, base, fever, lang)
            missing = set(original.text.splitlines()) - set(changed.text.splitlines())
            assert missing == {
                line for line in original.text.splitlines() if original.fact_text(variant.change.field) in line
            }


def test_a_case_whose_fields_are_all_critical_gets_no_mr2(cases, fever):
    base = next(iter(cases.values()))
    critical_only = base.model_copy(update={"facts": {code: base.facts[code] for code in base.key.critical_fields}})
    critical_only = critical_only.model_copy(
        update={"key": critical_only.key.model_copy(update={"critical_fields": tuple(sorted(critical_only.facts))})}
    )
    made = generator.generate([critical_only], fever, 1, mrs=("MR2",))
    assert made.variants == () and made.missing["MR2"] == 1


# --- MR4 -------------------------------------------------------------------------------------------------------------


def test_mr4_facts_are_used_by_no_rule_and_change_nothing(full, cases, fever):
    """PR-MR4, KONZEPT U10: no active rule uses the added facts; the output stays; the expectation is invariant."""
    used = set().union(*(fields_of(rule.when) for rule in fever.rules))
    every_rule_field = set().union(
        *(fields_of(rule.when) for name in loader.domains() for rule in loader.load_domain(name).rules)
    )
    added = Counter()
    for variant in _of(full, "MR4"):
        base = cases[variant.case_id]
        assert isinstance(variant.change, AddFacts) and len(variant.change.facts) == 1
        (code,) = variant.change.facts
        fact = fever.catalog.irrelevant_fact(code)
        assert fact is not None and fact.when.fits(base.patient.sex, base.patient.age)
        assert code not in used and code not in every_rule_field and fever.catalog.get(code) is None
        assert (
            variant.facts == base.facts
            and variant.key.model_dump(exclude={"required_questions"}) == base.key.model_dump()
        )
        with_fact = {**base.facts, code: True}
        assert infer(fever, with_fact).rules == infer(fever, base.facts).rules
        assert variant.expectation == InvariantExpectation(kind="invariant", compare=UNCHANGED)
        added[code] += 1
    assert set(added) == {fact.code for fact in fever.catalog.irrelevant}


def test_mr4_adds_one_line_at_the_end_of_its_section(full, cases, fever):
    variant = _of(full, "MR4")[0]
    base = cases[variant.case_id]
    (code,) = variant.change.facts
    fact = fever.catalog.irrelevant_fact(code)
    for lang in LANGUAGES:
        original = render_case(base, fever, lang).text.splitlines()
        rendering = render_variant(variant, base, fever, lang)
        lines = rendering.text.splitlines()
        label = getattr(fact.labels, lang)
        colon = "：" if lang == "zh" else ": "
        assert rendering.extra_text(code) == f"{label.name}{colon}{label.value}"
        added = [line for line in lines if line not in original]
        assert added == [f"  • {label.name}{colon}{label.value}"]
        heading = lines.index(next(line for line in lines if line.startswith("### 1.")))
        assert heading < lines.index(added[0]) < lines.index(next(line for line in lines if line.startswith("### 2.")))


def test_mr4_respects_the_condition_of_use(cases, fever):
    """KONZEPT 4.1: the appendectomy 20 years ago fits patients from 30 years on."""
    young = next(case for case in cases.values() if case.patient.age < 30)
    old = next(case for case in cases.values() if case.patient.age >= 30)
    assert "hx.previous_surgery" not in generator.fitting_irrelevant(young, fever)
    assert "hx.previous_surgery" in generator.fitting_irrelevant(old, fever)
    variants = generator.generate([young], fever, 1, per_case=5, mrs=("MR4",))
    assert all("hx.previous_surgery" not in variant.change.facts for variant in variants.variants)
    assert variants.missing["MR4"] == 5 - len(generator.fitting_irrelevant(young, fever))


# --- MR6 -------------------------------------------------------------------------------------------------------------


def test_conversions_are_exact_and_round_half_away_from_zero(fever):
    """KONZEPT U10: conversions tested; °C to °F by definition, mg/L to mg/dL and G/L to 10^3/µL by unit prefixes."""
    fahrenheit = units.alt_unit(fever.catalog.get("vital.temp_c"), "°F")
    assert units.shown(39.2, fahrenheit) == Decimal("102.6")
    assert units.shown(38.0, fahrenheit) == Decimal("100.4")
    assert units.shown(37.25, fahrenheit) == Decimal("99.1")  # 99.05 exactly: half away from zero
    assert units.back(Decimal("102.6"), fahrenheit) == Fraction(353, 9)
    milligrams = units.alt_unit(fever.catalog.get("lab.crp_mg_l"), "mg/dL")
    assert units.shown(52.4, milligrams) == Decimal("5.24") and units.back(Decimal("5.24"), milligrams) == Fraction(
        "52.4"
    )
    count = units.alt_unit(fever.catalog.get("lab.wbc_g_l"), "10^3/µL")
    assert units.shown(9.1, count) == Decimal("9.1")
    assert units.round_half_away(Fraction(-5, 2), 0) == Decimal(-3)
    assert (
        units.round_half_away(Fraction(-1, 4), 0) == Decimal(0)
        and str(units.round_half_away(Fraction(1, 2), 2)) == "0.50"
    )
    with pytest.raises(units.UnitError, match="no alternative unit 'K'"):
        units.alt_unit(fever.catalog.get("vital.temp_c"), "K")


def test_mr6_keeps_facts_and_every_rule_value(full, cases, fever):
    """PR-MR6, A-39: the shown numbers, read back, keep the value of every rule."""
    seen_units = Counter()
    abbreviations = 0
    for variant in _of(full, "MR6"):
        base = cases[variant.case_id]
        assert isinstance(variant.change, ChangeNotation)
        assert variant.facts == base.facts
        assert flipped_rules(fever, base.facts, variant.change.units) == ()
        assert variant.expectation == InvariantExpectation(kind="invariant", compare=UNCHANGED)
        seen_units.update(variant.change.units.values())
        abbreviations += variant.change.abbreviations
    assert set(seen_units) == {"°F", "mg/dL", "10^3/µL"} and 20 < abbreviations < 80


def test_mr6_text_shows_converted_numbers_and_abbreviations(cases, fever):
    base = next(case for case in cases.values() if case.facts["vital.temp_c"] == 40.4)
    variant = generator.mr6(base, fever, 1, 30)
    notation = next(
        item
        for item in variant.variants
        if item.change.abbreviations and set(item.change.units) == {"vital.temp_c", "lab.crp_mg_l"}
    )
    text = render_variant(notation, base, fever, "de").text
    assert "T: 104,7 °F" in text and "Körpertemperatur" not in text
    assert "CRP: 5,24 mg/dl (Referenzbereich 0,00–1,00 mg/dl)" in text
    assert "AF: " in text and "Atemfrequenz" not in text
    assert "Bewusstseinslage: " in text, "a field without abbreviation keeps its name"
    english = render_variant(notation, base, fever, "en").text
    assert "T: 104.7 °F" in english and "CRP: 5.24 mg/dL (reference range 0.00–1.00 mg/dL)" in english
    chinese = render_variant(notation, base, fever, "zh").text
    assert "104.7℉" in chinese


def test_a_notation_that_changes_a_rule_value_is_discarded_and_counted(fixture_packs):
    """A-39: with whole degrees Fahrenheit 38.0 °C reads as 100 °F = 37.8 °C, and the rule temp >= 38.0 flips."""
    demo = loader.load_domain("demo", fixture_packs)
    coarse = _with_alt(demo, "vital.temp_c", decimals=0)
    facts = {"vital.temp_c": 38.0, "hx.cough": True, "lab.crp_mg_l": 7}
    read, _ = read_back(coarse, facts, {"vital.temp_c": "°F"})
    assert read["vital.temp_c"] == pytest.approx(37.7778, abs=1e-4)
    assert flipped_rules(coarse, facts, {"vital.temp_c": "°F"}) == ("DEM-DDX-001",)
    assert flipped_rules(demo, facts, {"vital.temp_c": "°F"}) == ()
    with pytest.raises(ValueError, match="not a field of domain demo"):
        read_back(demo, facts, {"lab.nothing": "°F"})


def test_rounded_reference_limits_count_as_shown(fixture_packs):
    """A-39: CRP 7 mg/L above the limit 5 mg/L; in whole mg/dL both read as 1, and the rule '> upper' flips."""
    demo = loader.load_domain("demo", fixture_packs)
    coarse = _with_alt(demo, "lab.crp_mg_l", decimals=0)
    facts = {"lab.crp_mg_l": 7}
    read, references = read_back(coarse, facts, {"lab.crp_mg_l": "mg/dL"})
    assert read["lab.crp_mg_l"] == 10 and references["lab.crp_mg_l"].upper == 10
    assert flipped_rules(coarse, facts, {"lab.crp_mg_l": "mg/dL"}) == ("LABX-DDX-001",)


def test_discarded_draws_are_counted_apart_from_missing(fixture_packs, tmp_path):
    packs = tmp_path / "packs"
    shutil.copytree(fixture_packs, packs)
    directory = tmp_path / "demo-20"
    collection.write(collection.build("demo", 20, 1, name="demo-20", root=packs), directory)
    cases = [case for _, case in collection.read_cases(directory / collection.CASES_FILE, [])]
    coarse = _with_alt(loader.load_domain("demo", packs), "vital.temp_c", decimals=0)
    coarse = _with_alt(coarse, "lab.crp_mg_l", decimals=0)
    made = generator.generate(cases, coarse, 1, per_case=40, mrs=("MR6",))
    kept = len(made.variants)
    assert made.discarded["MR6"] > 0
    options = sum(len(generator.notation_options(case, coarse)) for case in cases)
    assert kept + made.discarded["MR6"] + made.missing["MR6"] == 40 * len(cases)
    assert made.missing["MR6"] == 40 * len(cases) - options
    for variant in made.variants:
        base = next(case for case in cases if case.case_id == variant.case_id)
        assert flipped_rules(coarse, base.facts, variant.change.units) == ()
        assert sets.check_variant(variant, base, coarse) == []
    numbers = [
        int(variant.variant_id.rsplit("-", 1)[1]) for variant in made.variants if variant.case_id == cases[0].case_id
    ]
    assert numbers == list(range(1, len(numbers) + 1)), "kept variants are numbered without gaps"


def test_notation_options_leave_out_the_base_notation(cases, fever):
    base = next(iter(cases.values()))
    options = generator.notation_options(base, fever)
    convertible = [field for field in fever.catalog.fields if field.alt_units and field.code in base.facts]
    assert len(options) == 2 ** (len(convertible) + 1) - 1
    assert ({}, False) not in options and ({}, True) in options


# --- MR7 -------------------------------------------------------------------------------------------------------------


def test_mr7_only_where_the_template_fits_and_expects_the_field(full, cases, fever):
    """PR-MR7, A-15, KONZEPT U10: the statement contradicts a fact; the expectation names its field code."""
    templates = Counter()
    for variant in _of(full, "MR7"):
        base = cases[variant.case_id]
        assert isinstance(variant.change, InsertContradiction)
        template = fever.catalog.contradiction(variant.change.template)
        assert template is not None and template.field == variant.change.field
        assert evaluate(template.when, base.facts, fever.references) is Truth.TRUE
        assert variant.facts == base.facts
        assert variant.expectation == AbsoluteExpectation(kind="absolute", contradictions_include=(template.field,))
        assert variant.expectation.decision is None
        templates[template.id] += 1
    assert set(templates) == {template.id for template in fever.catalog.contradictions}
    without = {case_id for case_id in cases} - {variant.case_id for variant in _of(full, "MR7")}
    assert len(without) == 2
    for case_id in without:
        assert generator.fitting_contradictions(cases[case_id], fever) == []


def test_mr7_states_the_contradiction_in_every_language(full, cases, fever):
    variant = next(item for item in _of(full, "MR7") if item.change.template == "FEV-MR7-001")
    base = cases[variant.case_id]
    assert base.facts["vital.temp_c"] > 38.0
    expected = {"de": "Anmerkung: afebril", "en": "Note: afebrile", "zh": "备注：无发热"}
    for lang in LANGUAGES:
        rendering = render_variant(variant, base, fever, lang)
        assert rendering.extra_text("FEV-MR7-001") == expected[lang]
        exam = rendering.text.split("### 2.")[1].split("### 3.")[0]
        assert expected[lang] in exam
        assert set(rendering.spans) == set(base.facts)


def test_the_afebrile_template_needs_a_temperature_above_38(fever):
    """FEV-MR7-001 follows SRC-0001 Box 1: fever is a temperature above 38 °C; 38.0 °C is no contradiction."""
    template = fever.catalog.contradiction("FEV-MR7-001")
    assert evaluate(template.when, {"vital.temp_c": 38.0}, fever.references) is Truth.FALSE
    assert evaluate(template.when, {"vital.temp_c": 38.1}, fever.references) is Truth.TRUE
    assert [source.ref for source in template.sources] == ["SRC-0001"]


# --- Checks of a variant set -----------------------------------------------------------------------------------------


@pytest.fixture
def demo(tmp_path, fixture_packs):
    packs = tmp_path / "packs"
    shutil.copytree(fixture_packs, packs)
    directory = tmp_path / "demo-10"
    collection.write(collection.build("demo", 10, 1, name="demo-10", root=packs), directory)
    built = sets.build(directory, 3, root=packs)
    cases = {case.case_id: case for _, case in collection.read_cases(directory / collection.CASES_FILE, [])}
    return built.variants, cases, loader.load_domain("demo", packs)


def _changed(variant: Variant, **update) -> Variant:
    return Variant.model_validate({**variant.to_json(), **update})


def test_set_checks_find_wrong_mr2_mr4_mr6_mr7(demo):
    variants, cases, domain = demo

    def first(mr: str) -> Variant:
        return next(variant for variant in variants if variant.mr == mr)

    mr2 = first("MR2")
    base = cases[mr2.case_id]
    critical = base.key.critical_fields[0]
    wrong = _changed(
        mr2,
        change={"kind": "remove_field", "field": critical},
        facts={code: value for code, value in base.facts.items() if code != critical},
    )
    text = "\n".join(sets.check_variant(wrong, base, domain))
    assert "MR2 must remove a field that is not critical" in text and "changes the output" in text

    mr4 = first("MR4")
    base = cases[mr4.case_id]
    unknown = _changed(mr4, change={"kind": "add_facts", "facts": ["hx.unknown"]})
    assert "no irrelevant fact of the catalog that fits" in "\n".join(sets.check_variant(unknown, base, domain))
    male = next(case for case in cases.values() if case.patient.sex == "m")
    female_only = _changed(
        mr4,
        variant_id=f"{male.case_id}-MR4-1",
        case_id=male.case_id,
        facts=dict(male.facts),
        key={**male.key.model_dump(mode="json"), "required_questions": []},
        change={"kind": "add_facts", "facts": ["exam.fixture_detail_female"]},
    )
    assert "fits the patient" in "\n".join(sets.check_variant(female_only, male, domain))

    mr6 = first("MR6")
    base = cases[mr6.case_id]
    foreign = _changed(
        mr6, change={"kind": "change_notation", "units": {"hx.onset_days": "weeks"}, "abbreviations": False}
    )
    assert "notation is not one the catalog allows" in "\n".join(sets.check_variant(foreign, base, domain))
    coarse = _with_alt(_with_alt(domain, "vital.temp_c", decimals=0), "lab.crp_mg_l", decimals=0)
    flipping = [
        variant
        for variant in variants
        if variant.mr == "MR6" and flipped_rules(coarse, cases[variant.case_id].facts, variant.change.units)
    ]
    for variant in flipping:
        assert "(A-39)" in "\n".join(sets.check_variant(variant, cases[variant.case_id], coarse))

    mr7 = first("MR7")
    base = cases[mr7.case_id]
    other = next(t for t in domain.catalog.contradictions if t.id != mr7.change.template)
    unfitting = _changed(
        mr7,
        change={"kind": "insert_contradiction", "template": other.id, "field": other.field},
        expectation={"kind": "absolute", "contradictions_include": [other.field]},
    )
    if other.id not in generator.fitting_contradictions(base, domain):
        assert "does not hold on the base case" in "\n".join(sets.check_variant(unfitting, base, domain))
    missing = _changed(
        mr7,
        change={"kind": "insert_contradiction", "template": "DEM-MR7-999", "field": mr7.change.field},
    )
    assert "no contradiction template DEM-MR7-999" in "\n".join(sets.check_variant(missing, base, domain))


def test_rendering_refuses_lists_the_catalog_does_not_have(demo):
    variants, cases, domain = demo
    mr4 = next(variant for variant in variants if variant.mr == "MR4")
    unknown = _changed(mr4, change={"kind": "add_facts", "facts": ["hx.unknown"]})
    with pytest.raises(RenderError, match="no irrelevant fact"):
        render_variant(unknown, cases[mr4.case_id], domain, "en")
    mr7 = next(variant for variant in variants if variant.mr == "MR7")
    missing = _changed(mr7, change={**mr7.change.model_dump(), "template": "DEM-MR7-999"})
    with pytest.raises(RenderError, match="no contradiction DEM-MR7-999"):
        render_variant(missing, cases[mr7.case_id], domain, "en")
    mr6 = next(variant for variant in variants if variant.mr == "MR6")
    foreign = _changed(mr6, change={"kind": "change_notation", "units": {"vital.temp_c": "K"}, "abbreviations": False})
    with pytest.raises(RenderError, match="no alternative unit 'K'"):
        render_variant(foreign, cases[mr6.case_id], domain, "en")


def test_the_lists_are_labelled_for_the_physician_review(fever):
    """The texts MR4 and MR7 add are part of the labels a review covers (A-23, PR-A06)."""
    from proof.render import templating

    for lang in LANGUAGES:
        labels = templating.labels(fever, lang)
        assert set(labels["irrelevant"]) == {fact.code for fact in fever.catalog.irrelevant}
        assert set(labels["contradictions"]) == {template.id for template in fever.catalog.contradictions}
        assert all(re.fullmatch(r"\S.*\S", item["value"]) for item in labels["contradictions"].values())
