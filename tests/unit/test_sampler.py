"""Case sampler (PR-F03, PR-K03, PR-K04, PR-W01, PR-W04, A-66 to A-68)."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from proof.cases import constraints
from proof.cases import sampler as sampler_module
from proof.cases.constraints import Intervals
from proof.cases.profiles import status_of
from proof.cases.sampler import (
    MIN_BUCKET_PATIENTS,
    Discrete,
    Numeric,
    Sample,
    SamplerError,
    Segment,
    Target,
    load_sampler,
)
from proof.core import canonical
from proof.core.hashing import sha256_json
from proof.core.rng import Stream
from proof_rules import loader
from proof_rules.engine import Key

FIXTURE_PACKS = Path(__file__).resolve().parents[1] / "fixtures" / "packs"
FEVER_DIAGNOSES = ("ddx.bacterial_meningitis", "ddx.pneumonia", "ddx.pyelonephritis", "ddx.sepsis")


@pytest.fixture(scope="module")
def fever():
    return load_sampler("fever")


@pytest.fixture(scope="module")
def demo():
    return load_sampler("demo", FIXTURE_PACKS)


@pytest.fixture
def fever_packs(tmp_path):
    target = tmp_path / "packs"
    shutil.copytree(loader.PACKS_ROOT, target)
    return target


def _problems(name, root) -> str:
    with pytest.raises(SamplerError) as caught:
        load_sampler(name, root)
    return "\n".join(caught.value.problems)


# --- Reproducibility -------------------------------------------------------------------------------------------------


def test_same_seed_gives_the_same_case(fever):
    first = canonical.dumps_bytes(fever.sample(42).case.to_json())
    again = canonical.dumps_bytes(load_sampler("fever").sample(42).case.to_json())
    assert first == again
    assert first != canonical.dumps_bytes(fever.sample(43).case.to_json())


def test_golden_case_hashes(fever, repo_root):
    """PR-F03: identical bytes on Windows and Linux (CI); the hashes change only with the packs or the sampler."""
    golden = json.loads((repo_root / "tests/golden/cases_v1.json").read_text(encoding="utf-8"))
    assert golden["domain"] == "fever"
    for seed, digest in golden["cases"].items():
        assert sha256_json(fever.sample(int(seed)).case.to_json()) == digest, seed


def test_a_case_depends_on_its_seed_only(fever):
    """The plan entry follows from the seed, so the case of seed 123 is the same in every collection."""
    assert [fever.target(seed) for seed in range(1, 8)] == list(fever.plan)
    assert fever.target(8) == fever.plan[0]
    assert fever.target(0) == fever.plan[-1]
    assert fever.sample(123).case.case_id == "FEV-000123"


# --- Cases -----------------------------------------------------------------------------------------------------------


def test_sampled_cases_are_complete_valid_and_reach_their_target(fever):
    """PR-K03, A-07: complete base cases within the catalog; the key comes from the rule set and meets the target."""
    codes = set(fever.domain.catalog.codes())
    for seed in range(1, 141):
        sample = fever.sample(seed)
        case = sample.case
        assert set(case.facts) == codes
        assert fever.domain.fact_problems(case.facts) == []
        assert case.complaint == "fever"
        assert sample.target.ddx in case.key.ddx
        assert bool(case.key.red_flags) == (sample.target.red_flag == "present")
        assert not sample.relabeled
        assert case.key.determinability in ("answer", "refer_urgent")  # complete base cases never give ask (A-33)
        assert case.key.critical_fields, "every base case has a critical field for MR1"
        assert 18 <= case.patient.age <= 90


def test_demo_cases_reach_their_targets(demo):
    for seed in range(1, 61):
        sample = demo.sample(seed)
        assert not sample.relabeled
        assert demo.domain.fact_problems(sample.case.facts) == []


def test_relabeling_compares_the_key_with_the_target(fever):
    """PR-K04: a key that misses the target stays as computed; the sample reports it as relabeled."""
    sample = fever.sample(3)
    assert sample.target == Target("ddx.pneumonia", "absent")
    other = Sample(case=sample.case, target=Target("ddx.pyelonephritis", "absent"))
    assert other.relabeled == ("ddx.pyelonephritis" not in sample.case.key.ddx)
    flagged = Sample(case=sample.case, target=Target("ddx.pneumonia", "present"))
    assert flagged.relabeled
    key = Key(determinability="answer", red_flags=(), critical_fields=(), ddx=("ddx.pneumonia",))
    assert Target("ddx.pneumonia", "absent").met_by(key)
    assert not Target("ddx.pneumonia", "present").met_by(key)
    assert Target("ddx.pneumonia", "absent").label == "ddx.pneumonia/absent"


def test_patient_draw_uses_the_whole_range(fever):
    patients = [fever.facts(seed)[2] for seed in range(1, 401)]
    ages = [patient.age for patient in patients]
    sexes = Counter(patient.sex for patient in patients)
    assert min(ages) >= 18 and max(ages) <= 90
    assert min(ages) < 25 and max(ages) > 83
    assert set(sexes) == {"f", "m"}


def test_lab_values_come_from_the_synthehr_quantiles(fever):
    """PR-W01: within a status, values lie between the status's lowest and highest quantile; weight 0 never drawn."""
    references = fever.domain.references
    seen: dict[str, Counter] = {code: Counter() for code in fever.lab_profiles}
    for seed in range(1, 301):
        _, facts, _ = fever.facts(seed)
        for code, profile in fever.lab_profiles.items():
            value = facts[code]
            status = status_of(value, (references[code].lower, references[code].upper))
            quantiles = profile.status_quantiles(status)
            assert quantiles is not None
            assert quantiles[0] <= value <= quantiles[-1], (code, value)
            seen[code][status] += 1
    assert "low" not in seen["lab.lactate_mmol_l"], "lactate 'low' has 9 patients and weight 0 (RK-02)"
    assert set(seen["lab.creatinine_umol_l"]) == {"low", "normal", "high"}


def test_vital_values_stay_within_the_sampling_ranges(fever):
    """PR-W04: vital signs and white cells come from own ranges with source."""
    for seed in range(1, 201):
        _, facts, _ = fever.facts(seed)
        assert 35.0 <= facts["vital.temp_c"] <= 41.0
        assert 50 <= facts["vital.heart_rate"] <= 140
        assert 10 <= facts["vital.resp_rate"] <= 36
        assert 70 <= facts["vital.sbp"] <= 180
        assert 1.0 <= facts["lab.wbc_g_l"] <= 30.0
        assert 0 <= facts["hx.onset_days"] <= 20


def test_minimum_bucket_is_the_number_of_quantiles():
    assert MIN_BUCKET_PATIENTS == 21


# --- Distributions ---------------------------------------------------------------------------------------------------


def test_discrete_distribution_respects_weights_and_constraints():
    distribution = Discrete((False, True), (9, 1))
    stream = Stream("test", "discrete")
    draws = Counter(distribution.draw(stream, None) for _ in range(2000))
    assert 120 < draws[True] < 280
    assert {distribution.draw(stream, frozenset({True})) for _ in range(50)} == {True}
    assert distribution.has_mass(frozenset({True}))
    assert not Discrete((False, True), (1, 0)).has_mass(frozenset({True}))


def test_numeric_distribution_is_piecewise_uniform(fever):
    field = fever.domain.catalog.get("vital.heart_rate")
    distribution = Numeric(field, (Segment("normal", 50, 59, 1), Segment("high", 60, 69, 3), Segment("x", 0, 9, 0)))
    stream = Stream("test", "numeric")
    draws = [distribution.draw(stream, None) for _ in range(4000)]
    assert min(draws) == 50 and max(draws) == 69
    high = sum(value >= 60 for value in draws)
    assert 2800 < high < 3200
    allowed = Intervals(((55, 62),))
    limited = Counter(distribution.draw(stream, allowed) for _ in range(4000))
    assert set(limited) == set(range(55, 63))
    # Restricted, each point keeps its density: 5 points of weight 1/10 and 3 points of weight 3/10.
    low_share = sum(limited[value] for value in range(55, 60)) / 4000
    assert 0.29 < low_share < 0.42
    assert not distribution.has_mass(Intervals(((70, None),)))
    with pytest.raises(SamplerError, match="no value"):
        distribution.draw(stream, Intervals(((70, None),)))


# --- Checks of the sampler profile -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["facts"].pop("hx.cough") and None, "hx.cough has no background distribution"),
        (lambda d: d["facts"].update({"hx.headache": {"kind": "bool", "p_true": [1, 2]}}), "not a field of domain"),
        (lambda d: d["facts"].update({"hx.cough": {"kind": "enum", "weights": {"a": 1}}}), "needs kind 'bool'"),
        (lambda d: d["facts"].update({"hx.cough": {"kind": "bool", "p_true": [3, 2]}}), "must not exceed 1"),
        (
            lambda d: d["facts"].update({"vital.mental_status": {"kind": "enum", "weights": {"x": 1}}}),
            "values the field does not have",
        ),
        (
            lambda d: d["facts"]["vital.temp_c"]["sample"].update({"lower": 20.0}),
            "outside the physiological bounds",
        ),
        (lambda d: d["facts"]["vital.temp_c"]["sample"].update({"lower": 35.05}), "not on the grid"),
        (lambda d: d["facts"]["vital.temp_c"]["reference"].update({"lower": 35.0}), "lower reference limit"),
        (lambda d: d["facts"]["vital.temp_c"]["reference"].update({"upper": 41.0}), "upper reference limit"),
        (lambda d: d["facts"]["vital.temp_c"]["reference"].update({"upper": 38.05}), "not on the grid"),
        (
            lambda d: d["facts"]["vital.resp_rate"]["status_weights"].update({"low": 1}),
            "statuses the reference range does not have",
        ),
        (lambda d: d["facts"]["vital.resp_rate"].pop("status_weights") and None, "needs status_weights"),
        (
            lambda d: d["facts"]["hx.onset_days"].update({"status_weights": {"high": 1}}),
            "the only status is normal",
        ),
        (
            lambda d: d["facts"]["vital.resp_rate"]["reference"]["source"].update({"ref": "SRC-9999"}),
            "source SRC-9999 is not in the source register",
        ),
        (lambda d: d["patient"]["age"]["sources"][0].update({"ref": "SRC-9999"}), "patient.age: source SRC-9999"),
        (lambda d: d["patient"]["age"].update({"lower": 40}), "lower must not exceed upper"),
        (lambda d: d["patient"].update({"sex": {"f": 0, "m": 0}}), "at least one positive weight"),
        (lambda d: d["plan"].append({"ddx": "ddx.gamma", "red_flag": "maybe"}), "Input should be 'present'"),
        (lambda d: d["plan"].append({"ddx": "rf.qsofa_ge2", "red_flag": "absent"}), "must be a ddx code"),
        (lambda d: d["plan"].append({"ddx": "ddx.delta", "red_flag": "absent"}), "not the target of an active rule"),
        (
            lambda d: d["facts"].update({"lab.crp_mg_l": {"kind": "range", "sample": {"lower": 0, "upper": 9}}}),
            "needs kind 'profile'",
        ),
        (lambda d: d["facts"]["lab.crp_mg_l"].update({"status_weights": {"low": 1}}), "status low has 0 patients"),
        (lambda d: d["facts"]["vital.sbp"].update({"sample": {"lower": 120, "upper": 100}}), "lower must be below"),
        (
            lambda d: d["facts"]["vital.sbp"].update({"reference": {"source": {"ref": "SRC-9001", "locator": "x"}}}),
            "needs a lower or an upper limit",
        ),
        (
            lambda d: d["facts"]["vital.temp_c"]["reference"].update({"lower": 38.5}),
            "lower must not exceed upper",
        ),
    ],
)
def test_invalid_sampler_profiles_are_rejected(packs, edit_yaml, change, message):
    edit_yaml(packs / "demo/sampler.yaml", change)
    assert message in _problems("demo", packs)


def test_unreachable_targets_are_rejected(fever_packs, edit_yaml):
    """Sepsis needs qSOFA >= 2, so 'sepsis without red flag' cannot be drawn."""
    edit_yaml(
        fever_packs / "fever/sampler.yaml", lambda d: d["plan"].append({"ddx": "ddx.sepsis", "red_flag": "absent"})
    )
    assert "plan[7] ddx.sepsis/absent: no facts within the sampling ranges reach this target" in _problems(
        "fever", fever_packs
    )


def test_a_target_outside_the_sampling_ranges_is_rejected(packs, edit_yaml):
    # ddx.alpha needs a temperature of at least 38.0 °C; with sampling up to 37.9 no case can reach it.
    def change(data):
        data["facts"]["vital.temp_c"] = {"kind": "range", "sample": {"lower": 35.0, "upper": 37.9}}

    edit_yaml(packs / "demo/sampler.yaml", change)
    problems = _problems("demo", packs)
    assert "plan[0] ddx.alpha/present: no facts within the sampling ranges reach this target" in problems
    assert "plan[1] ddx.alpha/absent" in problems


def test_repeated_plan_entries_weight_the_plan(packs, edit_yaml):
    edit_yaml(packs / "demo/sampler.yaml", lambda d: d["plan"].append({"ddx": "ddx.alpha", "red_flag": "present"}))
    demo = load_sampler("demo", packs)
    assert len(demo.plan) == 4 and demo.target(4) == demo.target(1)


def test_conditions_with_too_many_alternatives_are_reported(packs, monkeypatch):
    monkeypatch.setattr(constraints, "MAX_TERMS", 1)
    assert "plan[0] ddx.alpha/present: a condition has more than 1 alternatives" in _problems("demo", packs)


def test_red_flag_present_needs_a_red_flag_rule(packs):
    (packs / "demo/rules/red_flags.yaml").write_text("[]\n", encoding="utf-8")
    assert "red flag present, but the domain has no red-flag rule" in _problems("demo", packs)


def test_thin_lab_buckets_must_have_weight_zero(fever_packs, edit_yaml):
    """RK-02: lactate 'low' has 9 patients; giving it weight is refused instead of filling it silently."""
    edit_yaml(
        fever_packs / "fever/sampler.yaml",
        lambda d: d["facts"]["lab.lactate_mmol_l"]["status_weights"].update({"low": 1}),
    )
    assert "status low has 9 patients, fewer than 21; give it weight 0" in _problems("fever", fever_packs)


def test_profiles_built_with_other_bounds_are_rejected(packs):
    path = packs / "demo/profiles/crp_mg_l.json"
    data = canonical.loads(path.read_bytes())
    data["bounds"]["upper"] = 400
    path.write_bytes(canonical.dumps_bytes(data) + b"\n")
    assert "built with other physiological bounds" in _problems("demo", packs)


def test_profile_fields_need_their_profile(packs, monkeypatch):
    monkeypatch.setattr(sampler_module, "read_lab_profiles", lambda directory: {})
    assert "no lab profile for lab.crp_mg_l" in _problems("demo", packs)


def test_broken_profile_and_profile_files(packs):
    (packs / "demo/profiles/crp_mg_l.json").write_text('{"fact_code": "lab.crp_mg_l"}', encoding="utf-8")
    with pytest.raises(loader.LoadError):
        load_sampler("demo", packs)
    assert "reference: Field required" in _problems_from_profiles(packs)


def _problems_from_profiles(packs) -> str:
    with pytest.raises(SamplerError) as caught:
        sampler_module.read_lab_profiles(packs / "demo/profiles")
    return "\n".join(caught.value.problems)


def test_missing_or_broken_sampler_file(packs):
    path = packs / "demo/sampler.yaml"
    path.write_text("patient: [\n", encoding="utf-8")
    assert "sampler.yaml" in _problems("demo", packs)
    path.write_text("plan: []\n", encoding="utf-8")
    problems = _problems("demo", packs)
    assert "patient: Field required" in problems and "plan: Tuple should have at least 1 item" in problems
    path.unlink()
    assert "file is missing" in _problems("demo", packs)


def test_fever_profile_only_uses_registered_sources(fever):
    ids = fever.domain.sources.ids()
    assert {ref.ref for ref in fever.spec.patient.age.sources} <= ids
    for background in fever.spec.facts.values():
        reference = getattr(background, "reference", None)
        if reference is not None:
            assert reference.source.ref in ids
    assert {entry.ddx for entry in fever.spec.plan} == set(FEVER_DIAGNOSES)
